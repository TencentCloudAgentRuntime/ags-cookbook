# AGS Tool - 腾讯云 AGS (Agent Sandbox) 通用工具

这是一个用于管理腾讯云 AGS (Agent Sandbox) 服务的 Python 工具库，提供了完整的沙箱工具和实例生命周期管理功能，并集成了 e2b 接口用于沙箱实例的创建和命令执行。

## 功能特性

### 🔧 沙箱工具管理
- ✅ 创建自定义沙箱工具
- ✅ 支持 envd 存储挂载
- ✅ 查询工具列表
- ✅ 删除工具
- ✅ 等待工具激活

### 🚀 沙箱实例管理
- ✅ 启动沙箱实例
- ✅ 停止沙箱实例
- ✅ 查询实例列表
- ✅ 按状态/工具过滤实例

### 🔑 访问令牌管理
- ✅ 获取实例访问令牌
- ✅ 生成实例访问 URL

### 🐍 E2B 集成
- ✅ 使用 e2b 接口创建沙箱实例
- ✅ 执行命令（前台/后台）
- ✅ 执行代码（Python, JS, TS, Java, R, Bash）
- ✅ 文件系统操作
- ✅ 流式输出支持

## 安装

```bash
# 开发模式安装（推荐）
cd ags-tool
pip install -e .

# 包含 E2B 集成
pip install -e ".[e2b]"
```

## 快速开始

### 1. 配置凭证

推荐使用环境变量配置腾讯云凭证：

```bash
export TENCENTCLOUD_SECRET_ID="your_secret_id"
export TENCENTCLOUD_SECRET_KEY="your_secret_key"
export TENCENTCLOUD_ROLE_ARN="qcs::cam::uin/YOUR_UIN:roleName/YOUR_ROLE"  # 可选
```

或者在代码中直接配置：

```python
from ags_tool import AGSRuntime

runtime = AGSRuntime(
    secret_id="your_secret_id",
    secret_key="your_secret_key",
    region="ap-guangzhou"
)
```

### 2. 基础使用

```python
from ags_tool import AGSRuntime

# 初始化
runtime = AGSRuntime(
    region="ap-guangzhou",
    domain="ap-guangzhou.tencentags.com"
)

# 创建工具
tool_id = runtime.create_tool(
    tool_name="my-python-sandbox",
    image="python:3.11",
    cpu="2",
    memory="4Gi"
)

# 启动实例
instance_id = runtime.start_instance(tool_id=tool_id)

# 获取访问令牌
token = runtime.acquire_token(instance_id)

# 获取访问 URL
url = runtime.get_instance_url(instance_id)
print(f"访问地址: {url}")

# 清理资源
runtime.stop_instance(instance_id)
runtime.delete_tool(tool_id)
```

## 高级用法

### 使用 E2B 接口创建和管理沙箱

E2B 接口提供了更便捷的沙箱实例操作方式：

注意：`execute_code_in_sandbox()` 仅适用于 `code-interpreter-v1` 类型沙箱。自定义沙箱请使用 `upload_file_to_sandbox()` + `execute_command_in_sandbox()` 的方式。

```python
from ags_tool import AGSRuntime

runtime = AGSRuntime(
    region="ap-guangzhou",
    domain="ap-guangzhou.tencentags.com"
)

# 1. 创建 e2b 沙箱实例
sandbox = runtime.create_e2b_sandbox(
    tool_name="your-tool-name",
    timeout=600  # 10分钟
)

# 2. 执行命令
runtime.execute_command_in_sandbox(
    sandbox=sandbox,
    command="uname -a",
    user="root"
)

# 3. 执行 Python 代码
code = """
import pandas as pd
print(pd.__version__)
"""
runtime.execute_code_in_sandbox(
    sandbox=sandbox,
    code=code,
    language="python"
)

# 4. 文件操作
with open("local_file.txt", "r") as f:
    sandbox.files.write("remote_file.txt", f, user="root")

content = sandbox.files.read("remote_file.txt", user="root")

# 5. 清理
sandbox.kill()
```

### 创建支持 envd 挂载的工具

envd 是一个用于构建 AI/ML 开发环境的工具，可以通过 StorageMount 挂载到沙箱中：

```python
runtime = AGSRuntime(
    region="ap-guangzhou",
    domain="ap-guangzhou.tencentags.com",
    # 配置 envd 挂载
    mount_name="envd-storage",
    mount_image="ccr.ccs.tencentyun.com/namespace/envd-tools:latest",
    mount_image_registry_type="personal",
    mount_path="/envd",
    image_subpath="/envd",
    mount_readonly=True
)

tool_id = runtime.create_tool(
    tool_name="swe-bench-with-envd",
    image="your-base-image:latest",
    env_vars=[
        {"name": "PATH", "value": "/envd/bin:/usr/local/bin:/usr/bin:/bin"}
    ],
    cpu="2",
    memory="4Gi"
)
```

### 自定义环境变量和端口

```python
tool_id = runtime.create_tool(
    tool_name="custom-sandbox",
    image="your-image:latest",
    command=["/bin/bash"],
    command_args=["-c", "python app.py"],
    env_vars=[
        {"name": "APP_ENV", "value": "production"},
        {"name": "DEBUG", "value": "false"}
    ],
    ports=[
        {"name": "http", "port": 8080, "protocol": "TCP"},
        {"name": "metrics", "port": 9090, "protocol": "TCP"}
    ],
    cpu="4",
    memory="8Gi",
    probe_path="/health",
    probe_port=8080
)
```

### 查询和过滤

```python
# 列出所有工具
tools = runtime.list_tools(limit=10)
for tool in tools.SandboxToolSet:
    print(f"{tool.ToolName}: {tool.Status}")

# 查询特定工具的运行中实例
instances = runtime.list_instances(
    tool_id="sdt-xxxxxxxx",
    status="RUNNING"
)
```

### SWE-Bench 环境配置

```python
# 创建 SWE-Bench 专用环境
tool_id = runtime.create_tool(
    tool_name="swe-bench-env",
    image="ccr.ccs.tencentyun.com/namespace/swebench:latest",
    image_registry_type="personal",
    command=["/bin/bash"],
    command_args=["-l"],
    env_vars=[
        {"name": "LANG", "value": "en_US.UTF-8"},
        {"name": "DEBIAN_FRONTEND", "value": "noninteractive"}
    ],
    cpu="2",
    memory="4Gi",
    tool_description="SWE-Bench evaluation environment"
)
```

## API 参考

### AGSConfig

配置类，支持以下参数：


注意：`region` 不会自动从 `TENCENTCLOUD_REGION` 读取，需要在创建 `AGSRuntime` 时显式传入（可自行使用 `os.getenv()`）。
| 参数 | 类型 | 默认值 | 说明 |
|-----|------|--------|------|
| `type` | str | "tencentags" | 配置类型标识 |
| `secret_id` | str | "" | 腾讯云 SecretId |
| `secret_key` | str | "" | 腾讯云 SecretKey |
| `http_endpoint` | str | "ags.tencentcloudapi.com" | API 端点 |
| `skip_ssl_verify` | bool | false | 是否跳过 SSL 校验 |
| `region` | str | "ap-guangzhou" | 服务区域 |
| `domain` | str | "ap-guangzhou.tencentags.com" | 沙箱域名 |
| `tool_id` | str | "" | 复用的 SandboxTool ID |
| `image` | str | "python:3.11" | 默认镜像 |
| `image_registry_type` | str | "enterprise" | 镜像仓库类型 |
| `timeout` | str | "1h" | 实例超时时间 |
| `port` | int | 8000 | 服务端口 |
| `startup_timeout` | float | 180.0 | 启动等待时间（秒） |
| `runtime_timeout` | float | 60.0 | 运行时请求超时（秒） |
| `cpu` | str | "1" | CPU 限制 |
| `memory` | str | "1Gi" | 内存限制 |
| `role_arn` | str | "" | 角色 ARN |
| `mount_name` | str | "" | 挂载名称 |
| `mount_image` | str | "" | 挂载镜像 |
| `mount_image_registry_type` | str | "enterprise" | 挂载镜像仓库类型 |
| `mount_path` | str | "/nix" | 挂载路径 |
| `image_subpath` | str | "/nix" | 镜像内 SubPath |
| `mount_readonly` | bool | false | 挂载是否只读 |

### AGSRuntime

主要方法：

#### 工具管理

```python
# 创建工具
create_tool(
    tool_name: str,
    image: str,
    command: List[str] = None,
    command_args: List[str] = None,
    network_mode: str = "PUBLIC",
    tool_description: str = "",
    tool_default_timeout: str = "5m",
    role_arn: str = "",
    image_registry_type: str = "enterprise",
    ports: List[Dict] = None,
    env_vars: List[Dict] = None,
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
    tags: List[Dict] = None,
    storage_mounts: List[Dict] = None,
) -> str

# 查询工具列表
list_tools(
    tool_ids: List[str] = None,
    limit: int = 20,
    offset: int = 0
) -> Response

# 删除工具
delete_tool(tool_id: str) -> Response
```

#### 实例管理

```python
# 启动实例
start_instance(
    tool_id: str = None,
    tool_name: str = None,
    timeout: str = None,
    custom_config: Dict[str, Any] = None
) -> str

# 查询实例列表
list_instances(
    instance_ids: List[str] = None,
    tool_id: str = None,
    status: str = None,
    limit: int = 20
) -> Response

# 停止实例
stop_instance(instance_id: str) -> Response
```

#### 令牌管理

```python
# 获取访问令牌
acquire_token(instance_id: str) -> str

# 获取访问 URL
get_instance_url(instance_id: str, port: int = None) -> str
```

#### E2B 集成

```python
# 创建 e2b 沙箱实例
create_e2b_sandbox(
    tool_name: str,
    timeout: int = 600,
    api_key: str = None
) -> Sandbox

# 在沙箱中执行命令
execute_command_in_sandbox(
    sandbox: Sandbox,
    command: str,
    user: str = "root",
    background: bool = False,
    timeout: int = None,
    on_stdout: callable = None,
    on_stderr: callable = None
) -> Result

# 在沙箱中执行代码（仅 code-interpreter-v1 类型支持）
execute_code_in_sandbox(
    sandbox: Sandbox,
    code: str,
    language: str = "python",
    on_stdout: callable = None,
    on_stderr: callable = None,
    timeout: int = None
) -> Result

# 上传文件到沙箱（用于自定义沙箱执行）
upload_file_to_sandbox(
    sandbox: Sandbox,
    local_path: str,
    remote_path: str,
    user: str = "root"
) -> None
```

## 示例代码

项目包含两套示例 Notebook：

### 基础示例 (swe_bench_ags_tool.ipynb)

演示 AGS API 的基本使用与工具/实例生命周期管理。

### SDK 对照示例 (swe_bench_demo.ipynb)

演示使用原生 SDK 的 SWE-Bench 相关流程，便于对比抽象层。

运行示例：

```bash
jupyter notebook
```

## 核心概念

### 沙箱工具 (Sandbox Tool)

沙箱工具是一个模板，定义了沙箱实例的配置，包括：
- 容器镜像
- 资源限制（CPU、内存）
- 网络配置
- 环境变量
- 健康检查探针

### 沙箱实例 (Sandbox Instance)

沙箱实例是基于工具创建的运行中的容器环境。每个实例有：
- 唯一的实例 ID
- 访问令牌（有时效性）
- 访问 URL
- 运行状态（RUNNING、STOPPED 等）

### 健康检查探针 (Probe)

探针用于检测实例是否就绪和健康：
- `probe_path`: 健康检查路径
- `probe_port`: 健康检查端口
- `probe_ready_timeout_ms`: 就绪超时时间
- `probe_period_ms`: 探测间隔
- `probe_failure_threshold`: 失败阈值

## 最佳实践

1. **使用环境变量管理凭证**
   ```bash
   export TENCENTCLOUD_SECRET_ID="..."
   export TENCENTCLOUD_SECRET_KEY="..."
   ```

2. **为工具命名使用描述性名称**
   ```python
   tool_name="swe-bench-python-3.11"  # 好
   tool_name="test123"  # 不好
   ```

3. **合理设置资源限制**
   - 轻量级任务：1 CPU, 2Gi 内存
   - 中等任务：2 CPU, 4Gi 内存
   - 重量级任务：4+ CPU, 8Gi+ 内存

4. **及时清理资源**
   ```python
   try:
       # 使用实例
       pass
   finally:
       runtime.stop_instance(instance_id)
       runtime.delete_tool(tool_id)
   ```

5. **使用健康检查**
   - 为应用提供健康检查端点
   - 根据应用启动时间调整超时设置

## 故障排查

### 工具创建失败

```
❌ SandboxTool creation failed: Image pull failed
```

**解决方案**：
- 检查镜像地址是否正确
- 确认 `image_registry_type` 设置正确（enterprise/personal）
- 验证 `role_arn` 有访问镜像仓库的权限

### 实例启动失败

```
❌ Failed to start sandbox instance
```

**解决方案**：
- 检查工具是否处于 ACTIVE 状态
- 确认资源配额是否充足
- 查看探针配置是否合理

### 令牌过期

```
❌ Token expired
```

**解决方案**：
- 重新调用 `acquire_token()` 获取新令牌
- 实现自动刷新机制（参考 `ags.py` 中的 TokenInfo 实现）

## 与其他组件集成

### 与 SWE-ReX 集成

参考 `ags-cookbook-for-swe/examples/swe-agent/SWE-ReX/src/swerex/deployment/ags.py` 中的实现：

```python
from swerex.deployment.ags import TencentAGSDeployment

deployment = TencentAGSDeployment(
    secret_id="...",
    secret_key="...",
    region="ap-guangzhou"
)

await deployment.start()
runtime = deployment.runtime
```

## 相关资源

- [腾讯云 AGS 文档](https://cloud.tencent.com/document/product/ags)
- [Python SDK 文档](https://github.com/TencentCloud/tencentcloud-sdk-python)
- [AGS Cookbook](../ags-cookbook-for-swe/)

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！
