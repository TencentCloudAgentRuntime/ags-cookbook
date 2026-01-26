"""Tencent AGS (Agent Sandbox) Deployment for SWE-ReX.

This deployment manages sandbox instances via Tencent Cloud AGS (Agent Sandbox Service)
for executing code in isolated cloud environments.

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

from swerex import PACKAGE_NAME, REMOTE_EXECUTABLE_NAME
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
    from tencentcloud.common.common_client import CommonClient

__all__ = ["TencentAGSDeployment"]


# Refresh token when it has less than this many seconds until expiration
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
    """Deployment for Tencent Cloud AGS (Agent Sandbox).

    This deployment creates sandbox instances via Tencent Cloud AGS service
    and manages their lifecycle with automatic token refresh.
    """

    def __init__(
        self,
        *,
        logger: logging.Logger | None = None,
        **kwargs: Any,
    ):
        """Initialize Tencent AGS Deployment.

        Args:
            logger: Logger instance
            **kwargs: Keyword arguments (see `TencentAGSDeploymentConfig` for details).
        """
        self._config = TencentAGSDeploymentConfig(**kwargs)
        self._runtime: AGSRuntime | None = None
        self._instance_id: str | None = None
        self._token_info: TokenInfo | None = None
        self._server_token: str | None = None  # Token for SWE-ReX server authentication
        self._token_lock = asyncio.Lock()
        self.logger = logger or get_logger("rex-deploy")
        self._hooks = CombinedDeploymentHook()

    def add_hook(self, hook: DeploymentHook):
        self._hooks.add_hook(hook)

    @classmethod
    def from_config(cls, config: TencentAGSDeploymentConfig) -> Self:
        return cls(**config.model_dump())

    # ==================== SDK Client ====================

    def _get_client(self) -> "ags_client.AgsClient":
        """Get synchronous AGS client instance."""
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
        """Acquire a new token for the given instance (synchronous)."""
        from tencentcloud.ags.v20250920 import models

        client = self._get_client()
        token_req = models.AcquireSandboxInstanceTokenRequest()
        token_req.InstanceId = instance_id
        token_resp = client.AcquireSandboxInstanceToken(token_req)

        # Parse expires_at timestamp
        expires_at = self._parse_timestamp(token_resp.ExpiresAt)

        return TokenInfo(token=token_resp.Token, expires_at=expires_at, instance_id=instance_id)

    def _parse_timestamp(self, timestamp_str: str) -> datetime:
        """Parse timestamp string to datetime."""
        try:
            if timestamp_str.endswith("Z"):
                timestamp_str = timestamp_str[:-1] + "+00:00"
            return datetime.fromisoformat(timestamp_str)
        except ValueError:
            pass

        try:
            return datetime.fromtimestamp(float(timestamp_str), tz=timezone.utc)
        except ValueError:
            pass

        # Fallback: assume 1 hour from now
        self.logger.warning("Could not parse timestamp %s, assuming 1 hour expiration", timestamp_str)
        return datetime.now(timezone.utc) + timedelta(hours=1)

    async def _ensure_valid_token(self) -> str:
        """Ensure token is valid, refresh if needed."""
        if self._token_info is None:
            raise DeploymentNotStartedError()

        if not self._token_info.is_expired():
            return self._token_info.token

        async with self._token_lock:
            if not self._token_info.is_expired():
                return self._token_info.token

            self.logger.info("Token expired, refreshing...")
            self._token_info = await asyncio.to_thread(self._acquire_ags_token, self._token_info.instance_id)

            if self._runtime is not None:
                self._runtime._config.ags_token = self._token_info.token

        return self._token_info.token

    # ==================== SWE-ReX Command ====================

    def _get_token(self) -> str:
        """Generate a unique authentication token for SWE-ReX server."""
        return str(uuid.uuid4())

    def _get_swerex_start_cmd(self, token: str) -> str:
        """Generate the command to start SWE-ReX server.

        Similar to ModalDeployment._start_swerex_cmd
        """
        rex_args = f"--port {self._config.port} --auth-token ''"
        # Install pipx if not available, then run swerex
        setup_cmds = "python3 -m pip install pipx && python3 -m pipx ensurepath"
        
        # If mount is configured, use swerex-remote from mount path first
        # Expected structure: {mount_path}/swerex-remote
        if self._config.mount_image and self._config.mount_path:
            mount_executable = f"{self._config.mount_path.rstrip('/')}/swerex/run-swerex"
            return f"{mount_executable} {rex_args} || {REMOTE_EXECUTABLE_NAME} {rex_args} || ({setup_cmds} && pipx run {PACKAGE_NAME} {rex_args})"
        
        return f"{REMOTE_EXECUTABLE_NAME} {rex_args} || ({setup_cmds} && pipx run {PACKAGE_NAME} {rex_args})"

    # ==================== Tool Management ====================

    def _get_or_create_tool(self, image: str, server_token: str) -> str:
        """Get existing tool or create a new SandboxTool.

        If tool_id is configured, verify it exists and return it.
        Otherwise, create a new tool with the specified image and token.
        """
        # If tool_id is specified, verify it exists and use it
        if self._config.tool_id:
            self.logger.info(f"Using existing tool ID: {self._config.tool_id}")
            self._verify_tool_exists(self._config.tool_id)
            return self._config.tool_id

        # Otherwise, create a new tool
        return self._create_tool(image, server_token)

    def _verify_tool_exists(self, tool_id: str) -> None:
        """Verify that a SandboxTool exists and is ACTIVE."""
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

        self.logger.info(f"Verified SandboxTool {tool_id} exists and is ACTIVE")

    def _create_tool(self, image: str, server_token: str) -> str:
        """Create a new SandboxTool for the given image with the specified token."""
        self.logger.info(f"Creating SandboxTool for image {image}...")
        
        from tencentcloud.ags.v20250920 import models
        
        client = self._get_client()
        req = models.CreateSandboxToolRequest()
        
        # Directly build SDK request object
        req.ToolName = f"swerex-{uuid.uuid4().hex[:8]}"
        req.ToolType = "custom"
        req.ClientToken = str(uuid.uuid4())
        
        # Network configuration
        req.NetworkConfiguration = models.NetworkConfiguration()
        req.NetworkConfiguration.NetworkMode = "PUBLIC"
        
        # Custom configuration
        req.CustomConfiguration = models.CustomConfiguration()
        req.CustomConfiguration.Image = image
        req.CustomConfiguration.ImageRegistryType = self._config.image_registry_type
        req.CustomConfiguration.Command = ["/bin/sh", "-c"]
        req.CustomConfiguration.Args = [self._get_swerex_start_cmd(server_token)]
        
        # Ports
        req.CustomConfiguration.Ports = []
        port = models.PortConfiguration()
        port.Name = "http"
        port.Port = self._config.port
        port.Protocol = "TCP"
        req.CustomConfiguration.Ports.append(port)
        
        # Resources
        req.CustomConfiguration.Resources = models.ResourceConfiguration()
        req.CustomConfiguration.Resources.CPU = self._config.cpu
        req.CustomConfiguration.Resources.Memory = self._config.memory
        
        # Probe configuration
        req.CustomConfiguration.Probe = models.ProbeConfiguration()
        req.CustomConfiguration.Probe.HttpGet = models.HttpGetAction()
        req.CustomConfiguration.Probe.HttpGet.Path = "/"
        req.CustomConfiguration.Probe.HttpGet.Port = self._config.port
        req.CustomConfiguration.Probe.HttpGet.Scheme = "HTTP"
        req.CustomConfiguration.Probe.ReadyTimeoutMs = 30000
        req.CustomConfiguration.Probe.ProbeTimeoutMs = 1000
        req.CustomConfiguration.Probe.ProbePeriodMs = 2000
        req.CustomConfiguration.Probe.SuccessThreshold = 1
        req.CustomConfiguration.Probe.FailureThreshold = 15
        
        # RoleArn if configured
        if self._config.role_arn:
            req.RoleArn = self._config.role_arn
        
        # StorageMounts if mount image is configured
        if self._config.mount_image and self._config.mount_name:
            req.StorageMounts = []
            storage_mount = models.StorageMount()
            storage_mount.Name = self._config.mount_name
            storage_mount.MountPath = self._config.mount_path
            storage_mount.ReadOnly = self._config.mount_readonly
            
            storage_mount.StorageSource = models.StorageSource()
            storage_mount.StorageSource.Image = models.ImageStorageSource()
            storage_mount.StorageSource.Image.Reference = self._config.mount_image
            storage_mount.StorageSource.Image.ImageRegistryType = self._config.mount_image_registry_type
            storage_mount.StorageSource.Image.SubPath = self._config.image_subpath
            
            req.StorageMounts.append(storage_mount)
        
        self.logger.debug(f"CreateSandboxTool SDK request: ToolName={req.ToolName}")
        resp = client.CreateSandboxTool(req)
        tool_id = resp.ToolId
        self.logger.debug(f"CreateSandboxTool SDK response: ToolId={tool_id}, RequestId={resp.RequestId}")

        self.logger.info(f"Created SandboxTool {tool_id}, waiting for ACTIVE status...")
        self._wait_for_tool_active(tool_id)

        self.logger.info(f"SandboxTool {tool_id} is now ACTIVE")
        return tool_id

    def _wait_for_tool_active(self, tool_id: str, timeout: float = 300) -> None:
        """Wait for a SandboxTool to become ACTIVE."""
        from tencentcloud.ags.v20250920 import models

        client = self._get_client()
        start_time = time.monotonic()

        while True:
            elapsed = time.monotonic() - start_time
            if elapsed > timeout:
                raise TimeoutError(f"SandboxTool {tool_id} did not become ACTIVE within {timeout}s")

            describe_req = models.DescribeSandboxToolListRequest()
            describe_req.ToolIds = [tool_id]
            describe_resp = client.DescribeSandboxToolList(describe_req)

            if not describe_resp.SandboxToolSet:
                raise RuntimeError(f"SandboxTool {tool_id} not found")

            tool_info = describe_resp.SandboxToolSet[0]
            status = tool_info.Status
            self.logger.debug(f"SandboxTool {tool_id} info: {tool_info}")
            if status == "ACTIVE":
                return
            elif status == "FAILED":
                # Try to get error message from tool info
                error_msg = getattr(tool_info, 'StatusMessage', None) or getattr(tool_info, 'Message', None) or "Unknown error"
                raise RuntimeError(f"SandboxTool {tool_id} creation failed: {error_msg}")
            else:
                self.logger.info(f"SandboxTool {tool_id} status: {status}, waiting... ({elapsed:.1f}s)")
                time.sleep(2)

    # ==================== Lifecycle ====================

    async def is_alive(self, *, timeout: float | None = None) -> IsAliveResponse:
        """Checks if the runtime is alive."""
        if self._runtime is None or self._instance_id is None:
            raise DeploymentNotStartedError()

        await self._ensure_valid_token()

        # Check instance status
        from tencentcloud.ags.v20250920 import models

        client = self._get_client()
        describe_req = models.DescribeSandboxInstanceListRequest()
        describe_req.InstanceIds = [self._instance_id]
        describe_resp = await asyncio.to_thread(client.DescribeSandboxInstanceList, describe_req)

        if not describe_resp.InstanceSet:
            raise RuntimeError(f"SandboxInstance {self._instance_id} not found")

        if describe_resp.InstanceSet[0].Status != "RUNNING":
            raise RuntimeError(f"SandboxInstance is not running: {describe_resp.InstanceSet[0].Status}")

        return await self._runtime.is_alive(timeout=timeout)

    async def _wait_until_alive(self, timeout: float):
        """Wait until the runtime is alive."""
        return await _wait_until_alive(self.is_alive, timeout=timeout, function_timeout=self._config.runtime_timeout)

    async def start(self):
        """Starts the runtime in a Tencent AGS sandbox."""
        if self._runtime is not None and self._instance_id is not None:
            self.logger.warning("Deployment is already started. Ignoring duplicate start() call.")
            return

        self.logger.info("Starting Tencent AGS sandbox...")
        self._hooks.on_custom_step("Starting AGS sandbox")

        # Generate token for SWE-ReX server authentication
        self._server_token = ""

        # Step 1: Get or create tool
        t0 = time.time()
        tool_id = await asyncio.to_thread(self._get_or_create_tool, self._config.image, self._server_token)
        self.logger.info(f"Using tool ID: {tool_id}")

        # Step 2: Start sandbox instance
        self.logger.debug(f"Starting sandbox instance with tool ID: {tool_id}")
        
        from tencentcloud.ags.v20250920 import models
        
        client = self._get_client()
        req = models.StartSandboxInstanceRequest()
        
        # Directly build SDK request object
        req.ToolId = tool_id
        req.ClientToken = str(uuid.uuid4())
        
        if self._config.timeout:
            req.Timeout = self._config.timeout

        # If using existing tool_id, override with CustomConfiguration
        if self._config.tool_id:
            req.CustomConfiguration = models.CustomConfiguration()
            req.CustomConfiguration.Image = self._config.image
            req.CustomConfiguration.ImageRegistryType = self._config.image_registry_type
            req.CustomConfiguration.Command = ["/bin/sh", "-c"]
            req.CustomConfiguration.Args = [self._get_swerex_start_cmd(self._server_token)]
            
            # Ports
            req.CustomConfiguration.Ports = []
            port = models.PortConfiguration()
            port.Name = "http"
            port.Port = self._config.port
            port.Protocol = "TCP"
            req.CustomConfiguration.Ports.append(port)
            
            # Resources
            req.CustomConfiguration.Resources = models.ResourceConfiguration()
            req.CustomConfiguration.Resources.CPU = self._config.cpu
            req.CustomConfiguration.Resources.Memory = self._config.memory
            
            self.logger.info(f"Overriding tool config with image: {self._config.image}")
        
        self.logger.debug(f"StartSandboxInstance SDK request: ToolId={req.ToolId}")
        resp = await asyncio.to_thread(client.StartSandboxInstance, req)
        self._instance_id = resp.Instance.InstanceId
        self.logger.debug(f"StartSandboxInstance SDK response: InstanceId={self._instance_id}, RequestId={resp.RequestId}")

        if not self._instance_id:
            raise RuntimeError(f"Failed to get instance ID from response: {resp}")

        elapsed_creation = time.time() - t0
        self.logger.info(f"Sandbox instance {self._instance_id} is RUNNING in {elapsed_creation:.2f}s")

        # Step 3: Acquire token
        self._token_info = await asyncio.to_thread(self._acquire_ags_token, self._instance_id)

        # Step 4: Build endpoint URL and create runtime
        endpoint = f"https://{self._config.port}-{self._instance_id}.{self._config.domain}"
        self.logger.info(f"Sandbox endpoint: {endpoint}")

        self._hooks.on_custom_step("Starting runtime")
        self._runtime = AGSRuntime(
            host=endpoint,
            port=None,
            ags_token=self._token_info.token,      # AGS gateway authentication
            auth_token=self._server_token,          # SWE-ReX server authentication
            timeout=self._config.runtime_timeout,
            logger=self.logger,
            token_refresher=self,
        )

        # Step 5: Wait for runtime to be ready
        remaining_timeout = max(0, self._config.startup_timeout - elapsed_creation)
        t1 = time.time()
        await self._wait_until_alive(timeout=remaining_timeout)
        self.logger.info(f"Runtime started in {time.time() - t1:.2f}s")

    async def stop(self):
        """Stops the runtime and the AGS sandbox instance."""
        if self._runtime is not None:
            await self._runtime.close()
            self._runtime = None

        if self._instance_id is not None:
            self.logger.info(f"Stopping sandbox instance {self._instance_id}...")
            try:
                from tencentcloud.ags.v20250920 import models

                client = self._get_client()
                stop_req = models.StopSandboxInstanceRequest()
                stop_req.InstanceId = self._instance_id
                await asyncio.to_thread(client.StopSandboxInstance, stop_req)
                self.logger.info("Sandbox instance stopped successfully")
            except Exception as e:
                self.logger.warning(f"Failed to stop sandbox instance: {e}")

        self._instance_id = None
        self._token_info = None
        self._server_token = None

    @property
    def runtime(self) -> AGSRuntime:
        """Returns the runtime if running."""
        if self._runtime is None:
            raise DeploymentNotStartedError()
        return self._runtime

    @property
    def instance_id(self) -> str | None:
        """Returns the AGS sandbox instance ID."""
        return self._instance_id
