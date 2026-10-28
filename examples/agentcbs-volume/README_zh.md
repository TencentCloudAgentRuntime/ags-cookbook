# AgentCBS 存储模板：启动挂载持久化磁盘的沙箱

本示例启动一个 `custom` 类型的 AGS 沙箱，并把一块 **AgentCBS** 块存储 Volume 挂载到 `/workspace`。沙箱销毁后，这块盘上的数据依然保留。

- **不用构建镜像**：直接使用公开的代码解释器镜像 `ccr.ccs.tencentyun.com/ags-image/sandbox-code:latest`。
- **不用手动管理 Volume**：Tool 引用一个**存储模板（VolumeTemplate）**。启动沙箱时传入 `reuse_key`，同一个 `reuse_key` 第一次启动时由 AGS 自动创建一块盘，之后每次启动都挂载这同一块盘。

```text
VolumeTemplate（AgentCbs，10Gi，ReadWriteOnce，Retain）
        │  被引用
SandboxTool（custom，sandbox-code 镜像）
  StorageMounts: workspace → /workspace，ReuseKey=${metadata.reuse_key}
        │  Sandbox.create(metadata={"reuse_key": "session-s001", ...})
派生 Volume <模板名>-ws-session-s001（首次启动时创建，之后复用）
```

## 快速开始

```bash
cp .env.example .env    # 填写 4 个必填项，见下文
make setup              # 可选：提前安装依赖（make run 也会自动安装）
make run                # 运行示例
make cleanup            # 删除 Tool、Volume（含数据）和存储模板
```

`make run` 会依次完成：

1. 首次运行时创建存储模板和 SandboxTool，等两者都变为 `ACTIVE`。资源 ID 保存在 `.state/` 中，之后的运行直接复用。
2. 以 `reuse_key=session-s001` 启动沙箱，AGS 把这个 key 对应的 Volume 挂载到 `/workspace`。
3. 用 `run_code` 向 `/workspace/notes.txt` 追加一行并打印文件内容，然后销毁沙箱。

再执行一次 `make run`，`notes.txt` 会多一行，因为挂载的还是同一块盘。

如果不使用 `uv`，也可以在任意 Python 3.11+ 环境中直接运行：

```bash
pip install "e2b>=2.55.1" "e2b-code-interpreter>=2.11.5" "tencentcloud-sdk-python-common>=3.1.32"
python scripts/run.py
python scripts/cleanup.py
```

## 前置条件

- 已安装 [`uv`](https://docs.astral.sh/uv/)；或者按上面的方式，用 pip 和 Python 3.11+ 运行。
- AGS 账号，所在地域已开放 AgentCBS。本示例在 `ap-guangzhou` 验证通过。
- 在 `.env` 中填写以下必填项：

| 变量 | 获取方式 |
|---|---|
| `TENCENTCLOUD_SECRET_ID` / `TENCENTCLOUD_SECRET_KEY` | [访问管理 API 密钥](https://console.cloud.tencent.com/cam/capi)。该身份需要有以下 AGS 接口权限：`make run` 需要 `CreateVolumeTemplate`、`DescribeVolumeTemplateList`、`CreateSandboxTool`、`DescribeSandboxToolList`、`DescribeVolumeList`；`make cleanup` 需要 `DeleteSandboxTool`、`DeleteVolume`、`DeleteVolumeTemplate` |
| `TENCENTCLOUD_REGION` | AGS 地域，默认 `ap-guangzhou` |
| `E2B_API_KEY` | Agent Runtime 控制台中的 API Key，以 `ark_` 开头，不是 SecretId/SecretKey |
| `ROLE_ARN` | AGS 拉取镜像时扮演的 CAM 角色。按[创建自定义沙箱](https://cloud.tencent.com/document/product/1814/129691)第二、三步创建：以 Agent Runtime 为载体、有 CCR 拉取权限的角色，并给调用方授予该角色的 `cam:PassRole` 权限 |

`.env` 中的可选项：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `E2B_DOMAIN` | `<TENCENTCLOUD_REGION>.tencentags.com` | E2B 接入域名 |
| `SESSION_ID` | `session-s001` | 复用键，相同的键挂载同一块盘。只能包含小写字母、数字、`-`、`_`，最长 128 个字符 |
| `VOLUME_CAPACITY` | `10Gi` | 磁盘容量，创建存储模板时使用 |
| `SANDBOX_IMAGE_REF` | `ccr.ccs.tencentyun.com/ags-image/sandbox-code:latest` | 基于代码解释器镜像（`FROM`）自行构建的镜像 |
| `SANDBOX_IMAGE_REGISTRY_TYPE` | `personal` | `personal`（CCR 个人版）或 `enterprise`（TCR 企业版） |

## 预期输出

```text
Created VolumeTemplate agentcbs-ws-1028135535 (10Gi): volt-pjospoun
volume template status: ACTIVE
Created SandboxTool agentcbs-code-1028135536: sdt-m1lyuepb
tool status: CREATING
tool status: ACTIVE

== Start a sandbox with reuse_key=session-s001 ==
Sandbox started: ermyibaxia4ppyqt7ebotpf5uhzqms6qvyc42ed3 (14.0s)
Mount:
/dev/vda /workspace ext4 rw,relatime 0 0
/dev/vda        9.8G   24K  9.3G   1% /workspace
Volume: vol-01a18114-1d4f-8001-b361-e78a5ff909a6 (agentcbs-ws-1028135535-ws-session-s001, 10Gi, mounted_by=ermyibaxia4ppyqt7ebotpf5uhzqms6qvyc42ed3)
/workspace/notes.txt:
2026-10-28 05:55:56 written by ermyibaxia4ppyqt7ebotpf5uhzqms6qvyc42ed3
Sandbox killed: ermyibaxia4ppyqt7ebotpf5uhzqms6qvyc42ed3 (the Volume is retained)
AGENTCBS_VOLUME_OK
```

挂载 AgentCBS 的沙箱每次都是冷启动，不使用预创建的沙箱。本示例的镜像约 1.8 GB，启动约 10～17 秒。

## 实现原理

### 1. 存储模板（`CreateVolumeTemplate`）

```json
{
  "VolumeTemplateName": "agentcbs-ws",
  "StorageType": "AgentCbs",
  "StorageSpec": {"AgentCbs": {"Capacity": "10Gi"}},
  "VolumeNamePattern": "ws-${reuse_key}",
  "AccessMode": "ReadWriteOnce",
  "ReclaimPolicy": "Retain"
}
```

AgentCBS 存储模板只支持 `ReadWriteOnce` + `ReclaimPolicy=Retain`。`VolumeNamePattern` 必须包含 `${reuse_key}`。AGS 会自动加上模板名作为前缀，所以派生出的 Volume 名为 `<模板名>-ws-<reuse_key>`。

### 2. 沙箱工具（`CreateSandboxTool`）

镜像相关配置参考[创建自定义沙箱](https://cloud.tencent.com/document/product/1814/129691)，`StorageMounts` 引用上面的存储模板：

```json
{
  "ToolName": "agentcbs-code",
  "ToolType": "custom",
  "NetworkConfiguration": {"NetworkMode": "PUBLIC"},
  "RoleArn": "qcs::cam::uin/<uin>:roleName/<role>",
  "CustomConfiguration": {
    "Image": "ccr.ccs.tencentyun.com/ags-image/sandbox-code:latest",
    "ImageRegistryType": "personal",
    "Command": ["/init"],
    "Args": ["sleep", "infinity"],
    "Ports": [
      {"Name": "run-code", "Port": 49999, "Protocol": "TCP"},
      {"Name": "envd", "Port": 49983, "Protocol": "TCP"}
    ],
    "Resources": {"CPU": "2", "Memory": "1Gi"},
    "Probe": {
      "HttpGet": {"Path": "/health", "Port": 49999, "Scheme": "HTTP"},
      "ReadyTimeoutMs": 30000, "ProbeTimeoutMs": 1000, "ProbePeriodMs": 1000,
      "SuccessThreshold": 1, "FailureThreshold": 30
    }
  },
  "StorageMounts": [{
    "Name": "workspace",
    "VolumeTemplate": {"VolumeTemplateName": "agentcbs-ws", "ReuseKey": "${metadata.reuse_key}"},
    "MountPath": "/workspace",
    "ReadOnly": false
  }]
}
```

- 接口要求必须填写 `Command` 和 `Probe.HttpGet.Scheme`。
- 探针检查的是 `run-code` 的 `49999` 端口。如果改成检查 `envd` 的 `49983`，沙箱可能在代码解释器服务启动前就被判定为就绪，导致第一次 `run_code()` 失败。

### 3. 启动沙箱（E2B SDK）

```python
from e2b_code_interpreter import Sandbox

sandbox = Sandbox.create(
    template="<Tool ID 或名称>",
    metadata={
        "reuse_key": "session-s001",             # 填充 ${metadata.reuse_key}
        "x-ags-agent-cbs-system-disk": "true",   # 使用 AgentCBS 时必填，值为小写 "true"
    },
)
sandbox.run_code("open('/workspace/notes.txt', 'a').write('hello\\n')")
sandbox.kill()   # 沙箱销毁后 Volume 保留
```

E2B SDK 不负责管理存储模板、Volume 和 Tool。`scripts/run.py` 通过 `tencentcloud-sdk-python-common` 的 `CommonClient` 调用腾讯云 API 3.0 来创建这些资源。

## 清理

```bash
make cleanup
```

这条命令会删除 Tool、该模板派生出的所有 Volume 以及模板本身。**删除 Volume 会同时删除盘上的数据。** `DeleteVolume` 在请求受理后立即返回，底层磁盘由后台异步释放。

## 常见问题

| 现象 | 原因 / 处理 |
|---|---|
| `... is not set; fill it in .env` | 把 `.env.example` 复制为 `.env`，并填写必填项 |
| `Invalid API key format: expected "e2b_"...` | 本地 `e2b` 版本在 2.25～2.45 之间，这些版本不接受 AGS 的 Key（`ark_` 开头）。执行 `pip install -U "e2b>=2.55.1" "e2b-code-interpreter>=2.11.5"` 升级 |
| `AuthFailure...` / `UnauthorizedOperation` | 检查 SecretId/SecretKey 是否正确，以及是否有 AGS 相关接口权限 |
| `MissingParameter.RoleArn`，或者 Tool 拉取镜像失败 | 检查 `ROLE_ARN` 是否填写、该角色是否有 CCR 拉取权限、调用方是否有该角色的 `cam:PassRole` 权限，修正后重新执行 `make run`。处于 `FAILED` 状态的 Tool 会被自动替换，存储模板和 Volume 保持不变 |
| 启动时报 `ResourceInUse` | Volume 是 `ReadWriteOnce`，仍被另一个使用相同 `reuse_key` 的运行中沙箱占用。先销毁那个沙箱，或者换一个 `SESSION_ID` |
| `UnsupportedOperation.SandboxInstance: AgentCBS Volume requires metadata x-ags-agent-cbs-system-disk=true` | 启动沙箱时在 metadata 中加上该项 |
| 使用 `code-interpreter-v1` 等内置模板时报 `FailedOperation.ImagePrepare` | 内置模板无法挂载 AgentCBS，请像本示例一样使用 `custom` Tool |
| `InvalidParameter: Storage.AgentCbs.Capacity must be a positive integer with the Gi suffix` | 容量请写成 `10Gi` 这样的格式 |

## AgentCBS 使用限制

- 只支持 `ReadWriteOnce`：同一时刻只能被一个运行中的沙箱挂载；不支持只读挂载、`SubPath`，也不能挂载到 `/`。
- 一个沙箱最多挂载一块 AgentCBS Volume，但可以同时挂载 COS 或 CFS。
- `StartSandboxInstance.StorageMounts` 和 E2B 的 `x-storage` 都不能引用存储模板，模板挂载必须声明在 Tool 上。
- 挂载 AgentCBS 的沙箱只支持 `DISK` 模式的 Pause/Resume。
- Volume 与沙箱必须位于同一地域。

## 文件说明

| 文件 | 作用 |
|---|---|
| `scripts/run.py` | 创建或复用存储模板和 Tool，启动沙箱并读写 Volume |
| `scripts/cleanup.py` | 删除 `run.py` 创建的全部资源 |
| `scripts/common.py` | 读取 `.env`、创建腾讯云 API 客户端、把资源 ID 保存在 `.state/` |
| `.env.example` | 配置模板 |
