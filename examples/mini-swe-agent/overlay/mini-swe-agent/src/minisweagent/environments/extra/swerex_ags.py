"""Tencent AGS (Agent Sandbox) Environment for mini-swe-agent.

This environment uses Tencent Cloud AGS SWE sandbox for isolated code execution.
SWE sandbox has built-in swerex runtime, providing a ready-to-use environment
for SWE-bench evaluations.

Usage flow:
    1. Create a SWE sandbox tool on the AGS console, obtain a tool_id.
    2. Provide tool_id + credentials to this environment.
    3. Each instance can use a different SWE-bench image.
"""

import asyncio
import logging
from typing import Any

from pydantic import BaseModel, model_validator
from swerex.exceptions import CommandTimeoutError, EnvironmentExpiredError, EnvironmentUnavailableError
from swerex.runtime.abstract import Command as RexCommand

from minisweagent.exceptions import Submitted
from minisweagent.utils.serialize import recursive_merge

logger = logging.getLogger(__name__)


class SwerexAgsEnvironmentConfig(BaseModel):
    """Configuration for Tencent AGS SWE sandbox environment."""

    tool_id: str
    """SWE SandboxTool ID (created on AGS console). Required."""

    image: str = ""
    """SWE image name (e.g., 'swebench/sweb.eval.x86_64.django__django-16379:latest').
    If empty, uses the default SWE sandbox image."""

    cwd: str = "/"
    """Working directory in which to execute commands."""

    timeout: int = 60
    """Timeout for executing commands in the sandbox (seconds)."""

    startup_timeout: float = 120.0
    """Time to wait for the runtime to start (seconds)."""

    runtime_timeout: float = 60.0
    """Timeout for runtime HTTP requests (seconds)."""

    # Tencent Cloud credentials (can also be set via environment variables)
    secret_id: str = ""
    """Tencent Cloud SecretId (or use TENCENTCLOUD_SECRET_ID env var)."""

    secret_key: str = ""
    """Tencent Cloud SecretKey (or use TENCENTCLOUD_SECRET_KEY env var)."""

    region: str = "ap-chongqing"
    """Region for AGS service."""

    domain: str = ""
    """Domain for sandbox endpoint. Auto-derived from region if empty."""

    http_endpoint: str = "ags.tencentcloudapi.com"
    """Tencent Cloud HTTP endpoint."""

    skip_ssl_verify: bool = False
    """Skip SSL certificate verification (for internal/pre-release endpoints)."""

    timeout_duration: str = "1h"
    """Sandbox instance timeout duration (e.g., '5m', '300s', '1h')."""

    @model_validator(mode="before")
    @classmethod
    def _fill_credentials_from_env(cls, data: dict) -> dict:
        """Allow credentials from environment variables as fallback."""
        import os

        if not isinstance(data, dict):
            return data

        if not data.get("secret_id"):
            data["secret_id"] = os.environ.get("TENCENTCLOUD_SECRET_ID", "")
        if not data.get("secret_key"):
            data["secret_key"] = os.environ.get("TENCENTCLOUD_SECRET_KEY", "")

        # Auto-derive domain from region if not explicitly set
        if not data.get("domain"):
            region = data.get("region", "ap-chongqing")
            data["domain"] = f"{region}.tencentags.com"

        return data


class SwerexAgsEnvironment:
    """Environment that executes commands in Tencent AGS SWE sandbox.

    This environment uses SWE sandbox which has swerex runtime built-in.
    Each environment instance creates one sandbox instance with its own runtime.

    Usage:
        env = SwerexAgsEnvironment(
            tool_id="sdt-xxxxx",
            image="swebench/sweb.eval.x86_64.django__django-16379:latest",
        )
    """

    def __init__(self, **kwargs: Any):
        """Initialize and start the AGS SWE sandbox environment.

        Args:
            **kwargs: Configuration options (see SwerexAgsEnvironmentConfig).
        """
        self.config = SwerexAgsEnvironmentConfig(**kwargs)
        self.deployment = None
        self._started = False
        # Create a dedicated event loop for this environment instance
        # This avoids calling asyncio.run() repeatedly from threads, which can cause
        # deadlocks due to signal handler conflicts when multiple threads do this
        self._loop = asyncio.new_event_loop()
        self._start_deployment()

    def _start_deployment(self) -> None:
        """Create and start the AGS deployment."""
        try:
            from swerex.deployment.ags import TencentAGSDeployment
        except ImportError as e:
            raise ImportError(
                "AGS environment requires SWE-ReX with AGS support. "
                "Install with: pip install swe-rex[ags] or ensure the SWE-ReX package "
                "with AGS dependencies is available."
            ) from e

        deployment_kwargs: dict[str, Any] = {
            "tool_id": self.config.tool_id,
            "region": self.config.region,
            "domain": self.config.domain,
            "http_endpoint": self.config.http_endpoint,
            "skip_ssl_verify": self.config.skip_ssl_verify,
            "timeout": self.config.timeout_duration,
            "startup_timeout": self.config.startup_timeout,
            "runtime_timeout": self.config.runtime_timeout,
        }

        if self.config.image:
            deployment_kwargs["image"] = self.config.image

        if self.config.secret_id:
            deployment_kwargs["secret_id"] = self.config.secret_id

        if self.config.secret_key:
            deployment_kwargs["secret_key"] = self.config.secret_key

        self.deployment = TencentAGSDeployment(**deployment_kwargs)
        self._loop.run_until_complete(self.deployment.start())
        self._started = True

    def execute(self, action: dict, cwd: str = "", *, timeout: int | None = None) -> dict[str, Any]:
        """Execute a command in the AGS sandbox and return the raw output.

        Args:
            action: Dict with 'command' key containing the bash command to execute.
            cwd: Working directory for the command (defaults to config.cwd).
            timeout: Command timeout in seconds (defaults to config.timeout).

        Returns:
            Dict with 'output', 'returncode', and 'exception_info' keys.
        """
        if not self._started or self.deployment is None:
            return {
                "output": "",
                "returncode": -1,
                "exception_info": "Environment not started",
            }

        command = action.get("command", "")
        try:
            result = self._loop.run_until_complete(
                self.deployment.runtime.execute(
                    RexCommand(
                        command=command,
                        shell=True,
                        check=False,
                        cwd=cwd or self.config.cwd,
                        timeout=timeout if timeout is not None else self.config.timeout,
                        merge_output_streams=True,
                    )
                )
            )
            output = {"output": result.stdout, "returncode": result.exit_code, "exception_info": ""}
        except CommandTimeoutError as e:
            output = {
                "output": str(e) if str(e) else "",
                "returncode": -1,
                "exception_info": f"Command timed out: {e}",
                "extra": {"exception_type": type(e).__name__, "exception": str(e)},
            }
        except (EnvironmentExpiredError, EnvironmentUnavailableError):
            raise
        except Exception as e:
            output = {
                "output": str(e) if str(e) else "",
                "returncode": -1,
                "exception_info": f"An error occurred while executing the command: {e}",
                "extra": {"exception_type": type(e).__name__, "exception": str(e)},
            }
        self._check_finished(output)
        return output

    def _check_finished(self, output: dict) -> None:
        """Raises Submitted if the output indicates task completion."""
        lines = output.get("output", "").lstrip().splitlines(keepends=True)
        if lines and lines[0].strip() == "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT" and output["returncode"] == 0:
            submission = "".join(lines[1:])
            raise Submitted(
                {
                    "role": "exit",
                    "content": submission,
                    "extra": {"exit_status": "Submitted", "submission": submission},
                }
            )

    def get_template_vars(self, **kwargs: Any) -> dict[str, Any]:
        """Get template variables for rendering."""
        return recursive_merge(self.config.model_dump(), kwargs)

    def serialize(self) -> dict:
        """Serialize the environment configuration."""
        return {
            "info": {
                "config": {
                    "environment": self.config.model_dump(mode="json"),
                    "environment_type": f"{self.__class__.__module__}.{self.__class__.__name__}",
                }
            }
        }

    def stop(self) -> None:
        """Stop the AGS sandbox instance."""
        if self.deployment is not None:
            try:
                if self._loop is not None and not self._loop.is_running() and not self._loop.is_closed():
                    self._loop.run_until_complete(
                        asyncio.wait_for(self.deployment.stop(), timeout=10)
                    )
            except Exception:
                pass
            finally:
                self._started = False
                self.deployment = None
        # Close the event loop when done
        if self._loop is not None:
            try:
                if not self._loop.is_closed():
                    self._loop.close()
            except Exception:
                pass
            self._loop = None

    def __del__(self) -> None:
        """Cleanup when the environment is garbage collected."""
        try:
            self.stop()
        except Exception:
            pass
