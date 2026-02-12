"""通用的 Tencent AGS (Agent Sandbox) 工具类

这个模块提供了对腾讯云 AGS 服务的完整封装，包括：
- 沙箱工具管理（创建、查询、删除）
- 沙箱实例管理（启动、停止、查询）
- 访问令牌管理

使用示例：
    runtime = AGSRuntime(
        secret_id="your_secret_id",
        secret_key="your_secret_key",
        region="ap-guangzhou"
    )

    # 创建工具
    tool_id = runtime.create_tool(
        tool_name="my-sandbox",
        image="python:3.11"
    )

    # 启动实例
    instance_id = runtime.start_instance(tool_id=tool_id)

    # 获取访问令牌
    token = runtime.acquire_token(instance_id)
"""

from typing import Any, Literal, Optional, List, Dict
from pydantic import BaseModel, ConfigDict, Field, model_validator
from tencentcloud.ags.v20250920 import ags_client, models
from tencentcloud.common import credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
import json
import time
import uuid
import os


class AGSConfig(BaseModel):
    """Configuration for Tencent Cloud AGS (Agent Sandbox Server) deployment."""

    type: Literal["tencentags"] = "tencentags"
    """Discriminator for (de)serialization/CLI. Do not change."""

    secret_id: str = Field(default="", description="Tencent Cloud SecretId (or use TENCENTCLOUD_SECRET_ID env var)")
    secret_key: str = Field(default="", description="Tencent Cloud SecretKey (or use TENCENTCLOUD_SECRET_KEY env var)")
    http_endpoint: str = Field(default="ags.tencentcloudapi.com", description="Tencent Cloud HTTP endpoint")
    skip_ssl_verify: bool = Field(default=False, description="Skip SSL certificate verification (for internal/pre-release endpoints)")
    region: str = Field(default="ap-guangzhou", description="Region for AGS service")
    domain: str = Field(default="ap-guangzhou.tencentags.com", description="Domain for sandbox endpoint")

    # Tool configuration (optional)
    tool_id: str = Field(default="", description="Existing SandboxTool ID to use (if empty, creates a new tool)")

    image: str = Field(default="python:3.11", description="Container image for the sandbox")
    image_registry_type: str = Field(default="enterprise", description="Image registry type (enterprise, personal, etc.)")
    timeout: str = Field(default="1h", description="Sandbox instance timeout (e.g., '5m', '300s', '1h')")
    port: int = Field(default=8000, description="Port for sandbox endpoint")
    startup_timeout: float = Field(default=180.0, description="Time to wait for runtime to start")
    runtime_timeout: float = Field(default=60.0, description="Timeout for runtime requests")
    cpu: str = Field(default="1", description="CPU resource limit")
    memory: str = Field(default="1Gi", description="Memory resource limit")

    # Role configuration (optional)
    role_arn: str = Field(default="", description="Role ARN for accessing container registry")

    # Storage mount configuration (optional)
    mount_name: str = Field(default="", description="Name of the mount")
    mount_image: str = Field(default="", description="Image to mount as storage")
    mount_image_registry_type: str = Field(default="enterprise", description="Registry type for mount image")
    mount_path: str = Field(default="/nix", description="Path to mount the storage")
    image_subpath: str = Field(default="/nix", description="SubPath within the image mount")
    mount_readonly: bool = Field(default=False, description="Whether the mount is read-only")

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    def validate_credentials(cls, data: dict) -> dict:
        if not isinstance(data, dict):
            return data

        # Allow credentials from environment variables
        if not data.get("secret_id"):
            data["secret_id"] = os.environ.get("TENCENTCLOUD_SECRET_ID", "")
        if not data.get("secret_key"):
            data["secret_key"] = os.environ.get("TENCENTCLOUD_SECRET_KEY", "")
        if not data.get("role_arn"):
            data["role_arn"] = os.environ.get("TENCENTCLOUD_ROLE_ARN", "")

        # Auto-set domain based on region if not explicitly provided
        if "region" in data and "domain" not in data:
            region = data["region"]
            data["domain"] = f"{region}.tencentags.com"

        return data


class AGSRuntime:
    """通用的 AGS 运行时管理类

    提供对腾讯云 AGS 服务的完整封装，包括工具和实例的生命周期管理。
    """

    def __init__(self, **kwargs: Any):
        """初始化 AGS Runtime

        Args:
            **kwargs: 配置参数，参见 AGSConfig
        """
        self._config = AGSConfig(**kwargs)
        self._client: Optional[ags_client.AgsClient] = None

    # ==================== SDK Client ====================

    def _get_client(self) -> ags_client.AgsClient:
        """获取 AGS 客户端实例（单例）"""
        if self._client is not None:
            return self._client

        cred = credential.Credential(self._config.secret_id, self._config.secret_key)

        http_profile = HttpProfile()
        http_profile.endpoint = self._config.http_endpoint

        client_profile = ClientProfile()
        client_profile.httpProfile = http_profile
        if self._config.skip_ssl_verify:
            client_profile.unsafeSkipVerify = True

        self._client = ags_client.AgsClient(cred, self._config.region, client_profile)
        print("✅ AGS 客户端创建成功")
        return self._client

    # ==================== Tool Management ====================

    def create_tool(
        self,
        tool_name: str,
        image: str,
        command: Optional[List[str]] = None,
        command_args: Optional[List[str]] = None,
        network_mode: str = "PUBLIC",
        tool_description: str = "",
        tool_default_timeout: str = "5m",
        role_arn: str = "",
        image_registry_type: str = "enterprise",
        ports: Optional[List[Dict[str, Any]]] = None,
        env_vars: Optional[List[Dict[str, str]]] = None,
        cpu: str = "1",
        memory: str = "2Gi",
        probe_path: str = "/",
        probe_port: int = 80,
        probe_scheme: str = "HTTP",
        probe_ready_timeout_ms: int = 30000,
        probe_timeout_ms: int = 1000,
        probe_period_ms: int = 100,
        probe_success_threshold: int = 1,
        probe_failure_threshold: int = 100,
        tags: Optional[List[Dict[str, str]]] = None,
        storage_mounts: Optional[List[Dict[str, Any]]] = None,
        wait_for_active: bool = True,
    ) -> str:
        """创建自定义沙箱工具

        Args:
            tool_name: 工具名称
            image: 容器镜像
            command: 容器启动命令
            command_args: 容器启动参数
            network_mode: 网络模式 (PUBLIC, VPC, SANDBOX)
            tool_description: 工具描述
            tool_default_timeout: 默认超时时间
            role_arn: 角色 ARN
            image_registry_type: 镜像仓库类型 (enterprise, personal)
            ports: 端口配置列表
            env_vars: 环境变量列表
            cpu: CPU 资源限制
            memory: 内存资源限制
            probe_path: 探针路径
            probe_port: 探针端口
            probe_scheme: 探针协议
            probe_ready_timeout_ms: 就绪超时时间（毫秒）
            probe_timeout_ms: 单次探测超时（毫秒）
            probe_period_ms: 探测间隔（毫秒）
            probe_success_threshold: 成功阈值
            probe_failure_threshold: 失败阈值
            tags: 标签列表
            storage_mounts: 自定义存储挂载列表（覆盖配置中的挂载）
            wait_for_active: 是否等待工具变为 ACTIVE
                示例: [{
                    "name": "envd-storage",
                    "mount_path": "/mnt/envd",
                    "readonly": True,
                    "image": "ccr.ccs.tencentyun.com/archerlliu/envd:20260115_201017",
                    "image_registry_type": "personal",
                    "subpath": "/usr/bin/envd"
                }]

        Returns:
            str: 工具 ID
        """
        print(f"🔧 Creating SandboxTool for image {image}...")

        client = self._get_client()
        req = models.CreateSandboxToolRequest()

        # Basic configuration
        req.ToolName = tool_name
        req.ToolType = "custom"
        req.Description = tool_description
        req.DefaultTimeout = tool_default_timeout
        req.ClientToken = str(uuid.uuid4())

        # RoleArn configuration
        if role_arn or self._config.role_arn:
            req.RoleArn = role_arn or self._config.role_arn

        # Network configuration
        req.NetworkConfiguration = models.NetworkConfiguration()
        req.NetworkConfiguration.NetworkMode = network_mode

        # Custom configuration
        req.CustomConfiguration = models.CustomConfiguration()
        req.CustomConfiguration.Image = image
        req.CustomConfiguration.ImageRegistryType = image_registry_type
        req.CustomConfiguration.Command = command or ["/bin/sh", "-c"]
        req.CustomConfiguration.Args = command_args or ["-l"]

        # Ports configuration
        if ports:
            req.CustomConfiguration.Ports = []
            for port_config in ports:
                port_obj = models.PortConfiguration()
                port_obj.Name = port_config.get("name", "http")
                port_obj.Port = port_config.get("port", 80)
                port_obj.Protocol = port_config.get("protocol", "TCP")
                req.CustomConfiguration.Ports.append(port_obj)

        # Environment variables
        if env_vars:
            req.CustomConfiguration.Env = []
            for env_config in env_vars:
                env_var = models.EnvVar()
                env_var.Name = env_config["name"]
                env_var.Value = env_config["value"]
                req.CustomConfiguration.Env.append(env_var)

        # Resources
        req.CustomConfiguration.Resources = models.ResourceConfiguration()
        req.CustomConfiguration.Resources.CPU = cpu
        req.CustomConfiguration.Resources.Memory = memory

        # Probe configuration (健康检查 - 必须配置)
        req.CustomConfiguration.Probe = models.ProbeConfiguration()
        req.CustomConfiguration.Probe.HttpGet = models.HttpGetAction()
        req.CustomConfiguration.Probe.HttpGet.Path = probe_path
        req.CustomConfiguration.Probe.HttpGet.Port = probe_port
        req.CustomConfiguration.Probe.HttpGet.Scheme = probe_scheme
        req.CustomConfiguration.Probe.ReadyTimeoutMs = probe_ready_timeout_ms
        req.CustomConfiguration.Probe.ProbeTimeoutMs = probe_timeout_ms
        req.CustomConfiguration.Probe.ProbePeriodMs = probe_period_ms
        req.CustomConfiguration.Probe.SuccessThreshold = probe_success_threshold
        req.CustomConfiguration.Probe.FailureThreshold = probe_failure_threshold

        # Tags configuration
        if tags:
            req.Tags = []
            for tag_config in tags:
                tag = models.Tag()
                tag.Key = tag_config["key"]
                tag.Value = tag_config["value"]
                req.Tags.append(tag)

        # StorageMounts - custom mounts override config-based mounts
        if storage_mounts:
            req.StorageMounts = []
            for mount_config in storage_mounts:
                storage_mount = models.StorageMount()
                storage_mount.Name = mount_config["name"]
                storage_mount.MountPath = mount_config["mount_path"]
                storage_mount.ReadOnly = mount_config.get("readonly", False)

                storage_mount.StorageSource = models.StorageSource()
                storage_mount.StorageSource.Image = models.ImageStorageSource()
                storage_mount.StorageSource.Image.Reference = mount_config["image"]
                storage_mount.StorageSource.Image.ImageRegistryType = mount_config.get("image_registry_type", "enterprise")
                storage_mount.StorageSource.Image.SubPath = mount_config.get("subpath", "/")

                req.StorageMounts.append(storage_mount)
        elif self._config.mount_image and self._config.mount_name:
            # Fallback to config-based mount
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

        try:
            print(f"📤 CreateSandboxTool request: ToolName={req.ToolName}")
            resp = client.CreateSandboxTool(req)
            tool_id = resp.ToolId
            print(f"✅ CreateSandboxTool response: ToolId={tool_id}, RequestId={resp.RequestId}")

            if wait_for_active:
                print(f"⏳ Created SandboxTool {tool_id}, waiting for ACTIVE status...")
                self._wait_for_tool_active(tool_id)

                print(f"✅ SandboxTool {tool_id} is now ACTIVE")
            return tool_id
        except TencentCloudSDKException as err:
            print(f"❌ Failed to create SandboxTool: {err}")
            raise

    def _wait_for_tool_active(self, tool_id: str, timeout: float = 300) -> None:
        """等待工具变为 ACTIVE 状态

        Args:
            tool_id: 工具 ID
            timeout: 超时时间（秒）
        """
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

            if status == "ACTIVE":
                return
            elif status == "FAILED":
                error_msg = getattr(tool_info, 'StatusMessage', None) or getattr(tool_info, 'Message', None) or "Unknown error"
                raise RuntimeError(f"SandboxTool {tool_id} creation failed: {error_msg}")
            else:
                print(f"⏳ SandboxTool {tool_id} status: {status}, waiting... ({elapsed:.1f}s)")
                time.sleep(2)

    def list_tools(
        self,
        tool_ids: Optional[List[str]] = None,
        tool_name: Optional[str] = None,
        tag_key: Optional[str] = None,
        tag_value: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Any:
        """查询沙箱工具列表

        Args:
            tool_ids: 工具 ID 列表（可选，用于过滤）
            tool_name: 工具名称（可选，用于过滤）
            tag_key: 标签 Key（可选，用于过滤）
            tag_value: 标签 Value（可选，用于过滤）
            limit: 返回数量限制
            offset: 偏移量

        Returns:
            查询响应对象
        """
        try:
            client = self._get_client()
            req = models.DescribeSandboxToolListRequest()

            if tool_ids:
                req.ToolIds = tool_ids
            req.Limit = min(limit, 100)  # API enforces max 100
            req.Offset = offset

            filters = []
            if tool_name:
                print(f"❌ 查询工具列表失败: 暂时不支持tool_name")
                raise
                f = models.Filter()
                f.Name = "ToolName"
                f.Values = [tool_name]
                filters.append(f)
            if tag_key:
                f = models.Filter()
                f.Name = "tag-key"
                f.Values = [tag_key]
                filters.append(f)
            if tag_value:
                f = models.Filter()
                f.Name = "tag-value"
                f.Values = [tag_value]
                filters.append(f)
            if filters:
                req.Filters = filters

            resp = client.DescribeSandboxToolList(req)
            return resp
        except TencentCloudSDKException as err:
            print(f"❌ 查询工具列表失败: {err}")
            raise


    def get_tool(
        self,
        tool_id: Optional[str] = None,
        tool_name: Optional[str] = None,
        tag_key: Optional[str] = None,
        tag_value: Optional[str] = None,
        limit: int = 100,
    ) -> Optional[models.SandboxTool]:
        """Find a SandboxTool by id/name/tag. Prefer tool_id when provided."""
        if tool_id:
            resp = self.list_tools(tool_ids=[tool_id], limit=1, offset=0)
            tools = resp.SandboxToolSet or []
            return tools[0] if tools else None

        # Prefer server-side filtering by tool_name/tag when possible.
        resp = self.list_tools(
            tool_name=tool_name,
            tag_key=tag_key,
            tag_value=tag_value,
            limit=limit,
            offset=0,
        )
        tools = resp.SandboxToolSet or []
        if tools:
            return tools[0]

        # Fallback: paginate if backend ignores filters
        offset = 0
        while True:
            resp = self.list_tools(limit=limit, offset=offset)
            tools = resp.SandboxToolSet or []
            for tool in tools:
                if tool_name and getattr(tool, "ToolName", None) == tool_name:
                    return tool
                if tag_key and tag_value:
                    for tag in getattr(tool, "Tags", []) or []:
                        if getattr(tag, "Key", None) == tag_key and getattr(tag, "Value", None) == tag_value:
                            return tool
            if len(tools) < limit:
                return None
            offset += limit

    def get_tool_by_name(self, tool_name: str, tool_id: Optional[str] = None) -> Optional[models.SandboxTool]:
        return self.get_tool(tool_id=tool_id, tool_name=tool_name)

    def get_tool_by_tag(
        self,
        tag_key: str,
        tag_value: str,
        tool_id: Optional[str] = None,
        tool_name: Optional[str] = None,
    ) -> Optional[models.SandboxTool]:
        return self.get_tool(tool_id=tool_id, tool_name=tool_name, tag_key=tag_key, tag_value=tag_value)

    def delete_tool(self, tool_id: str) -> Any:
        """删除沙箱工具

        Args:
            tool_id: 工具 ID

        Returns:
            删除响应对象
        """
        try:
            client = self._get_client()
            req = models.DeleteSandboxToolRequest()
            req.ToolId = tool_id

            resp = client.DeleteSandboxTool(req)
            print(f"✅ 沙箱工具 {tool_id} 删除成功")
            return resp
        except TencentCloudSDKException as err:
            print(f"❌ 删除工具失败: {err}")
            raise

    # ==================== Instance Management ====================

    def start_instance(
        self,
        tool_id: Optional[str] = None,
        tool_name: Optional[str] = None,
        timeout: Optional[str] = None,
        custom_config: Optional[Dict[str, Any]] = None
    ) -> str:
        """启动沙箱实例

        Args:
            tool_id: 工具 ID（与 tool_name 二选一）
            tool_name: 工具名称（与 tool_id 二选一）
            timeout: 超时时间
            custom_config: 自定义配置（可选，用于覆盖工具配置）

        Returns:
            str: 实例 ID
        """
        if not tool_id and not tool_name:
            raise ValueError("tool_id 和 tool_name 至少需要提供一个")

        try:
            client = self._get_client()
            req = models.StartSandboxInstanceRequest()

            if tool_id:
                req.ToolId = tool_id
            if tool_name:
                req.ToolName = tool_name

            req.Timeout = timeout or self._config.timeout
            req.ClientToken = str(uuid.uuid4())

            # 如果提供了自定义配置，应用它
            if custom_config:
                req.CustomConfiguration = models.CustomConfiguration()
                # 这里可以根据 custom_config 字典填充配置
                # 为简化起见，暂不实现详细的配置映射
                pass

            print(f"🚀 Starting sandbox instance with tool_id={tool_id}, tool_name={tool_name}")
            resp = client.StartSandboxInstance(req)
            instance_id = resp.Instance.InstanceId
            print(f"✅ Sandbox instance {instance_id} started successfully")
            return instance_id
        except TencentCloudSDKException as err:
            print(f"❌ 启动实例失败: {err}")
            raise

    def list_instances(
        self,
        instance_ids: Optional[List[str]] = None,
        tool_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 20,
        offset: int = 0
    ) -> Any:
        """查询沙箱实例列表

        Args:
            instance_ids: 实例 ID 列表（可选）
            tool_id: 工具 ID（可选，用于过滤）
            status: 实例状态（可选，用于过滤）
            limit: 返回数量限制
            offset: 偏移量

        Returns:
            查询响应对象
        """
        try:
            client = self._get_client()
            req = models.DescribeSandboxInstanceListRequest()

            if instance_ids:
                req.InstanceIds = instance_ids
            if tool_id:
                req.ToolId = tool_id

            req.Limit = limit
            req.Offset = offset

            # 添加状态过滤器
            if status:
                req.Filters = [models.Filter()]
                req.Filters[0].Name = "Status"
                req.Filters[0].Values = [status]

            resp = client.DescribeSandboxInstanceList(req)
            print(f"📋 查询到 {resp.TotalCount} 个沙箱实例")
            return resp
        except TencentCloudSDKException as err:
            print(f"❌ 查询实例列表失败: {err}")
            raise

    def stop_instance(self, instance_id: str) -> Any:
        """停止沙箱实例

        Args:
            instance_id: 实例 ID

        Returns:
            停止响应对象
        """
        try:
            client = self._get_client()
            req = models.StopSandboxInstanceRequest()
            req.InstanceId = instance_id

            resp = client.StopSandboxInstance(req)
            print(f"✅ 沙箱实例 {instance_id} 停止成功")
            return resp
        except TencentCloudSDKException as err:
            print(f"❌ 停止实例失败: {err}")
            raise

    # ==================== Token Management ====================

    def acquire_token(self, instance_id: str) -> str:
        """获取沙箱实例访问令牌

        Args:
            instance_id: 实例 ID

        Returns:
            str: 访问令牌
        """
        try:
            client = self._get_client()
            req = models.AcquireSandboxInstanceTokenRequest()
            req.InstanceId = instance_id

            resp = client.AcquireSandboxInstanceToken(req)
            print(f"✅ 获取实例 {instance_id} 访问令牌成功")
            print(f"🔑 Token: {resp.Token[:20]}...")
            print(f"⏰ Expires at: {resp.ExpiresAt}")
            return resp.Token
        except TencentCloudSDKException as err:
            print(f"❌ 获取令牌失败: {err}")
            raise

    # ==================== Utility Methods ====================

    def get_instance_url(self, instance_id: str, port: Optional[int] = None) -> str:
        """获取实例访问 URL

        Args:
            instance_id: 实例 ID
            port: 端口号（默认使用配置中的端口）

        Returns:
            str: 实例访问 URL
        """
        port = port or self._config.port
        return f"https://{port}-{instance_id}.{self._config.domain}"

    # ==================== E2B Integration ====================

    def create_e2b_sandbox(
        self,
        tool_name: str,
        timeout: int = 600,
        api_key: Optional[str] = None
    ) -> "Sandbox":
        """使用 e2b 接口创建沙箱实例

        Args:
            tool_name: 工具名称（模板名称）
            timeout: 超时时间（秒）
            api_key: API Key（可选，默认从环境变量获取）

        Returns:
            Sandbox: e2b Sandbox 实例
        """
        try:
            from e2b_code_interpreter import Sandbox
        except ImportError:
            raise ImportError(
                "e2b_code_interpreter not installed. "
                "Please install it with: pip install e2b_code_interpreter"
            )

        # 设置环境变量 - 强制使用 runtime 配置的 domain
        # 这确保 domain 与 region 始终匹配
        os.environ["E2B_DOMAIN"] = self._config.domain

        if api_key:
            os.environ["E2B_API_KEY"] = api_key
        elif not os.getenv("E2B_API_KEY"):
            raise ValueError(
                "E2B_API_KEY not found. Please provide api_key parameter or set E2B_API_KEY environment variable."
            )

        print(f"🚀 Creating e2b sandbox with template: {tool_name}")
        print(f"⏱️  Timeout: {timeout}s")
        print(f"🌐 Domain: {os.getenv('E2B_DOMAIN')}")

        sandbox = Sandbox.create(template=tool_name, timeout=timeout)
        print(f"✅ Sandbox created: {sandbox.sandbox_id}")

        return sandbox

    def execute_command_in_sandbox(
        self,
        sandbox: "Sandbox",
        command: str,
        user: str = "root",
        background: bool = False,
        timeout: Optional[int] = None,
        on_stdout: Optional[callable] = None,
        on_stderr: Optional[callable] = None
    ) -> Any:
        """在沙箱中执行命令

        Args:
            sandbox: Sandbox 实例
            command: 要执行的命令
            user: 执行用户（默认 root）
            background: 是否后台执行
            timeout: 超时时间（秒）
            on_stdout: stdout 回调函数
            on_stderr: stderr 回调函数

        Returns:
            命令执行结果
        """
        print(f"🔧 Executing command: {command}")

        result = sandbox.commands.run(
            cmd=command,
            user=user,
            background=background,
            timeout=timeout,
            on_stdout=on_stdout,
            on_stderr=on_stderr
        )

        if not background:
            if result.stdout:
                print(f"📤 stdout:\n{result.stdout}")
            if result.stderr:
                print(f"📤 stderr:\n{result.stderr}")
            print(f"✅ Command executed, exit code: {result.exit_code}")

        return result

    def execute_code_in_sandbox(
        self,
        sandbox: "Sandbox",
        code: str,
        language: str = "python",
        on_stdout: Optional[callable] = None,
        on_stderr: Optional[callable] = None,
        timeout: Optional[int] = None
    ) -> Any:
        """在沙箱中执行代码

        注意: 只有 code-interpreter-v1 类型的沙箱支持直接执行代码。
        对于其他类型的沙箱，请使用 upload_file_to_sandbox() + execute_command_in_sandbox() 的方式。

        Args:
            sandbox: Sandbox 实例
            code: 要执行的代码
            language: 编程语言（python, js, ts, java, r, bash）
            on_stdout: stdout 回调函数
            on_stderr: stderr 回调函数
            timeout: 超时时间（秒）

        Returns:
            代码执行结果

        Raises:
            AttributeError: 如果沙箱不支持 run_code 方法（非 code-interpreter 类型）
        """
        # 检查沙箱是否支持 run_code
        if not hasattr(sandbox, 'run_code'):
            raise AttributeError(
                f"❌ 此沙箱不支持直接执行代码（sandbox.run_code 方法不可用）\n"
                f"   只有 'code-interpreter-v1' 类型的沙箱支持此功能\n"
                f"   对于自定义沙箱，请使用以下方式:\n"
                f"   1. runtime.upload_file_to_sandbox(sandbox, local_path, remote_path)\n"
                f"   2. runtime.execute_command_in_sandbox(sandbox, 'python {remote_path}')"
            )

        print(f"🐍 Executing {language} code...")

        try:
            result = sandbox.run_code(
                code,
                language=language,
                on_stdout=on_stdout,
                on_stderr=on_stderr,
                timeout=timeout
            )

            if result.logs.stdout:
                print(f"📤 stdout:\n{''.join(result.logs.stdout)}")
            if result.logs.stderr:
                print(f"📤 stderr:\n{''.join(result.logs.stderr)}")

            print(f"✅ Code executed successfully")
            return result
        except AttributeError as e:
            # 如果 sandbox 没有 run_code 方法
            if "run_code" in str(e):
                raise AttributeError(
                    f"❌ 此沙箱不支持直接执行代码\n"
                    f"   只有 'code-interpreter-v1' 类型的沙箱支持此功能\n"
                    f"   对于自定义沙箱，请使用文件上传 + 命令执行的方式"
                )
            raise

    def upload_file_to_sandbox(
        self,
        sandbox: "Sandbox",
        local_path: str,
        remote_path: str,
        user: str = "root"
    ) -> None:
        """上传本地文件到沙箱

        Args:
            sandbox: Sandbox 实例
            local_path: 本地文件路径
            remote_path: 沙箱中的远程路径
            user: 执行用户（默认 root）
        """
        print(f"📤 Uploading {local_path} to {remote_path}")

        with open(local_path, "r") as f:
            sandbox.files.write(remote_path, f, user=user)

        print(f"✅ File uploaded successfully")
