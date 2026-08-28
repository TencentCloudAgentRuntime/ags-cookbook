"""Tencent AGS (Agent Sandbox) Deployment for SWE-ReX.

This deployment manages SWE sandbox instances via Tencent Cloud AGS service.
SWE sandbox has built-in swerex runtime, so no manual server installation is needed.

Usage flow:
    1. User creates a SWE sandbox tool on the AGS console (ToolType="swebench"), obtains a tool_id.
    2. Provide tool_id + API credentials to create sandbox instances.
    3. Each instance can use a different SWE-bench image.

Requirements:
    pip install tencentcloud-sdk-python-common tencentcloud-sdk-python-ags
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from typing_extensions import Self

from swerex.deployment.abstract import AbstractDeployment
from swerex.deployment.config import TencentAGSDeploymentConfig
from swerex.deployment.hooks.abstract import CombinedDeploymentHook, DeploymentHook
from swerex.exceptions import DeploymentNotStartedError
from swerex.runtime.abstract import IsAliveResponse
from swerex.runtime.ags import AGSRuntime
from swerex.utils.log import get_logger
from swerex.utils.wait import _wait_until_alive

if TYPE_CHECKING:
    from tencentcloud.ags.v20250920 import ags_client

__all__ = ["TencentAGSDeployment"]

# Refresh token when it has less than this many seconds until expiration.
TOKEN_REFRESH_THRESHOLD_SECONDS = 60


@dataclass
class TokenInfo:
    """Token information with expiration tracking."""

    token: str
    expires_at: datetime
    instance_id: str

    def is_expired(self, threshold_seconds: int = TOKEN_REFRESH_THRESHOLD_SECONDS) -> bool:
        """Check if token is expired or about to expire."""
        now = datetime.now(timezone.utc)
        return (self.expires_at - now).total_seconds() < threshold_seconds


class TencentAGSDeployment(AbstractDeployment):
    """Deployment for Tencent Cloud AGS SWE Sandbox.

    Creates and manages SWE sandbox instances that have a built-in swerex
    runtime. The deployment lifecycle:

    1. Verify the user-provided SWE sandbox tool (tool_id) exists and is ACTIVE.
    2. Start a sandbox instance, optionally overriding the image.
    3. Acquire an access token for the instance.
    4. Connect an ``AGSRuntime`` to the instance endpoint.
    5. Wait for the runtime to become alive.
    """

    def __init__(
        self,
        *,
        logger: logging.Logger | None = None,
        **kwargs: Any,
    ):
        """Initialize Tencent AGS Deployment.

        Args:
            logger: Logger instance.
            **kwargs: Keyword arguments (see ``TencentAGSDeploymentConfig``).
        """
        self._config = TencentAGSDeploymentConfig(**kwargs)
        self._runtime: AGSRuntime | None = None
        self._instance_id: str | None = None
        self._token_info: TokenInfo | None = None
        self.logger = logger or get_logger("rex-deploy")
        self._hooks = CombinedDeploymentHook()

    def add_hook(self, hook: DeploymentHook) -> None:
        self._hooks.add_hook(hook)

    @classmethod
    def from_config(cls, config: TencentAGSDeploymentConfig) -> Self:
        return cls(**config.model_dump())

    # ==================== SDK Client ====================

    def _get_client(self) -> "ags_client.AgsClient":
        """Create a synchronous AGS client instance."""
        from tencentcloud.ags.v20250920 import ags_client
        from tencentcloud.common import credential
        from tencentcloud.common.profile.client_profile import ClientProfile
        from tencentcloud.common.profile.http_profile import HttpProfile

        cred = credential.Credential(self._config.secret_id, self._config.secret_key)

        http_profile = HttpProfile()
        http_profile.endpoint = self._config.http_endpoint

        client_profile = ClientProfile()
        client_profile.httpProfile = http_profile
        if self._config.skip_ssl_verify:
            client_profile.unsafeSkipVerify = True

        return ags_client.AgsClient(cred, self._config.region, client_profile)

    # ==================== Token Management ====================

    def _acquire_ags_token(self, instance_id: str) -> TokenInfo:
        """Acquire a new token for the given instance (synchronous SDK call)."""
        from tencentcloud.ags.v20250920 import models

        client = self._get_client()
        token_req = models.AcquireSandboxInstanceTokenRequest()
        token_req.InstanceId = instance_id
        token_resp = client.AcquireSandboxInstanceToken(token_req)

        expires_at = self._parse_timestamp(token_resp.ExpiresAt)
        return TokenInfo(token=token_resp.Token, expires_at=expires_at, instance_id=instance_id)

    def _parse_timestamp(self, timestamp_str: str) -> datetime:
        """Parse timestamp string to datetime, with multiple format fallbacks."""
        # ISO 8601 format
        try:
            if timestamp_str.endswith("Z"):
                timestamp_str = timestamp_str[:-1] + "+00:00"
            dt = datetime.fromisoformat(timestamp_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            pass

        # Unix timestamp
        try:
            return datetime.fromtimestamp(float(timestamp_str), tz=timezone.utc)
        except ValueError:
            pass

        # Fallback: assume 1 hour from now
        self.logger.warning("Could not parse timestamp %s, assuming 1 hour expiration", timestamp_str)
        return datetime.now(timezone.utc) + timedelta(hours=1)

    async def _ensure_valid_token(self) -> str:
        """Ensure token is valid, refresh if needed. Returns the valid token."""
        if self._token_info is None:
            raise DeploymentNotStartedError()

        if not self._token_info.is_expired():
            return self._token_info.token

        self.logger.info("Token expired or about to expire, refreshing...")
        self._token_info = await asyncio.to_thread(self._acquire_ags_token, self._token_info.instance_id)
        return self._token_info.token

    # ==================== Tool Verification ====================

    def _verify_tool_exists(self, tool_id: str) -> None:
        """Verify that a SandboxTool exists and is ACTIVE.

        Raises:
            RuntimeError: If the tool does not exist or is not ACTIVE.
        """
        from tencentcloud.ags.v20250920 import models

        client = self._get_client()
        describe_req = models.DescribeSandboxToolListRequest()
        describe_req.ToolIds = [tool_id]
        describe_resp = client.DescribeSandboxToolList(describe_req)

        if not describe_resp.SandboxToolSet:
            raise RuntimeError(f"SandboxTool {tool_id} not found")

        status = describe_resp.SandboxToolSet[0].Status
        if status != "ACTIVE":
            raise RuntimeError(f"SandboxTool {tool_id} is not ACTIVE (status: {status})")

        tool_type = describe_resp.SandboxToolSet[0].ToolType
        if tool_type != "swebench":
            self.logger.warning(f"SandboxTool {tool_id} is type '{tool_type}', expected 'swebench'")

        self.logger.info(f"Verified SWE SandboxTool {tool_id} exists and is ACTIVE")

    # ==================== Lifecycle ====================

    async def is_alive(self, *, timeout: float | None = None) -> IsAliveResponse:
        """Check if the runtime is alive."""
        if self._runtime is None or self._instance_id is None:
            raise DeploymentNotStartedError()

        await self._ensure_valid_token()

        # Verify instance is still running
        from tencentcloud.ags.v20250920 import models

        client = self._get_client()
        describe_req = models.DescribeSandboxInstanceListRequest()
        describe_req.InstanceIds = [self._instance_id]
        describe_resp = await asyncio.to_thread(client.DescribeSandboxInstanceList, describe_req)

        if not describe_resp.InstanceSet:
            raise RuntimeError(f"SandboxInstance {self._instance_id} not found")

        instance_status = describe_resp.InstanceSet[0].Status
        if instance_status != "RUNNING":
            raise RuntimeError(f"SandboxInstance is not running: {instance_status}")

        return await self._runtime.is_alive(timeout=timeout)

    async def _wait_until_alive(self, timeout: float) -> None:
        """Wait until the runtime is alive."""
        return await _wait_until_alive(self.is_alive, timeout=timeout, function_timeout=self._config.runtime_timeout)

    async def start(self) -> None:
        """Start a SWE sandbox instance and connect the runtime.

        Steps:
            1. Verify the SWE sandbox tool exists.
            2. Start a sandbox instance (with optional image override).
            3. Acquire an access token.
            4. Create AGSRuntime connected to the instance.
            5. Wait for the runtime to become alive.
        """
        if self._runtime is not None and self._instance_id is not None:
            self.logger.warning("Deployment is already started. Ignoring duplicate start() call.")
            return

        if not self._config.tool_id:
            raise ValueError(
                "tool_id is required. Please create a SWE sandbox tool on the AGS console first "
                "and provide its ID."
            )

        self.logger.info("Starting Tencent AGS SWE sandbox...")
        self._hooks.on_custom_step("Creating SWE sandbox")

        # Step 1: Verify tool exists
        t0 = time.time()
        await asyncio.to_thread(self._verify_tool_exists, self._config.tool_id)
        self.logger.info(f"Using SWE tool ID: {self._config.tool_id}")

        # Step 2: Start sandbox instance
        from tencentcloud.ags.v20250920 import models

        client = self._get_client()
        req = models.StartSandboxInstanceRequest()
        req.ToolId = self._config.tool_id
        req.ClientToken = str(uuid.uuid4())

        if self._config.timeout:
            req.Timeout = self._config.timeout

        # Override image at instance creation time
        if self._config.image:
            req.CustomConfiguration = models.CustomConfiguration()
            req.CustomConfiguration.Image = self._config.image
            req.CustomConfiguration.ImageRegistryType = "system"
            self.logger.info(f"Using SWE image: {self._config.image}")

        self.logger.debug(f"StartSandboxInstance request: ToolId={req.ToolId}")
        resp = await asyncio.to_thread(client.StartSandboxInstance, req)
        self._instance_id = resp.Instance.InstanceId

        if not self._instance_id:
            raise RuntimeError(f"Failed to get instance ID from response: {resp}")

        elapsed_creation = time.time() - t0
        self.logger.info(f"SWE sandbox instance {self._instance_id} is RUNNING in {elapsed_creation:.2f}s")

        # Step 3: Acquire token
        self._token_info = await asyncio.to_thread(self._acquire_ags_token, self._instance_id)

        # Step 4: Build endpoint URL and create runtime
        # Use HTTPS with the configured data-gateway port encoded in the hostname.
        # The Host header ({port}-{instanceId}.{domain}) routes traffic via data-gateway.
        endpoint = f"https://{self._config.port}-{self._instance_id}.{self._config.domain}"
        self.logger.info(f"SWE sandbox endpoint: {endpoint}")
        self.logger.debug(
            f"AGS token acquired, expires_at: {self._token_info.expires_at}"
        )

        self._hooks.on_custom_step("Connecting to runtime")
        self._runtime = AGSRuntime(
            host=endpoint,
            port=None,
            ags_token=self._token_info.token,
            auth_token="",  # SWE sandbox doesn't require swerex auth token
            timeout=self._config.runtime_timeout,
            skip_ssl_verify=self._config.skip_ssl_verify,
            logger=self.logger,
            token_refresher=self._ensure_valid_token,
        )

        # Step 5: Wait for runtime to be ready
        remaining_timeout = max(0, self._config.startup_timeout - elapsed_creation)
        t1 = time.time()
        await self._wait_until_alive(timeout=remaining_timeout)
        self.logger.info(f"Runtime connected in {time.time() - t1:.2f}s")

    async def stop(self) -> None:
        """Stop the runtime and the AGS sandbox instance."""
        if self._runtime is not None:
            try:
                await self._runtime.close()
            except Exception:
                pass
            self._runtime = None

        if self._instance_id is not None:
            try:
                from tencentcloud.ags.v20250920 import models

                client = self._get_client()
                stop_req = models.StopSandboxInstanceRequest()
                stop_req.InstanceId = self._instance_id
                await asyncio.to_thread(client.StopSandboxInstance, stop_req)
            except Exception:
                pass

        self._instance_id = None
        self._token_info = None

    @property
    def runtime(self) -> AGSRuntime:
        """Returns the runtime if running.

        Raises:
            DeploymentNotStartedError: If the deployment was not started.
        """
        if self._runtime is None:
            raise DeploymentNotStartedError()
        return self._runtime

    @property
    def instance_id(self) -> str | None:
        """Returns the AGS sandbox instance ID."""
        return self._instance_id
