# Mini-SWE-Agent：使用 AGS SWE 沙箱运行 SWE-bench 评测

本示例演示如何使用 [mini-swe-agent](https://github.com/SWE-agent/mini-SWE-agent) 配合腾讯云 AGS SWE 沙箱运行 [SWE-bench Verified](https://huggingface.co/datasets/princeton-nlp/SWE-Bench_Verified) 评测。

本示例采用 overlay 模式：在官方上游仓库基础上叠加 AGS 适配层，无需依赖任何私有 fork。

## 工作原理

```
官方上游仓库                        AGS overlay（本 Cookbook）
┌────────────────────┐          ┌────────────────────┐
│ SWE-agent/         │          │ overlay/            │
│   mini-SWE-agent   │  ← cp ──│   mini-swe-agent/   │  (AGS 环境封装、日志修复)
│ SWE-agent/         │          │   SWE-ReX/          │  (AGS 部署 + 运行时)
│   SWE-ReX          │  ← cp ──│                     │
└────────────────────┘          └────────────────────┘
```

overlay 添加了：
- mini-swe-agent 的 AGS SWE 沙箱环境封装
- SWE-ReX 的 AGS 部署 Provider 和 Runtime
- 线程安全的日志架构，避免与 Rich Live 进度条死锁
- SWE-bench AGS 评测配置

详见 [overlay/OVERLAY.md](overlay/OVERLAY.md) 了解每个 overlay 文件的详细说明。

## 前置条件

- Python >= 3.10（推荐 3.12，`make setup` 默认使用 3.12。可通过 `make setup PYTHON_VERSION=3.10` 覆盖）
- [uv](https://github.com/astral-sh/uv) — Python 包管理工具
- 腾讯云账号，已开通 AGS 服务（获取 `SecretId` 和 `SecretKey`）
- 一个 AGS SWE 沙箱工具（参见下方第 1 步）
- LLM API Key（OpenAI、Anthropic 或任意 OpenAI 兼容端点）

## 快速开始

### 1. 创建 SWE 沙箱工具（一次性操作）

1. 登录 [腾讯云 AGS 控制台](https://console.cloud.tencent.com/ags)。
2. 进入「环境工具」>「SWE 沙箱」。
3. 点击「新建沙箱工具」，工具配置留空，网络配置选择公网，直接提交创建。
4. 记录 **工具 ID**（格式如 `sdt-xxxxxxxx`）。

工具只需创建一次，后续所有沙箱实例复用同一个工具 ID。

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 填入腾讯云凭据
```

### 3. 安装（克隆 + overlay + 安装）

```bash
make setup
```

该命令会：
- 检查 `uv` 是否已安装
- 如果需要则克隆并安装 [SWE-ReX](https://github.com/SWE-agent/SWE-ReX)，包含 AGS SDK 依赖（`tencentcloud-sdk-python-common`、`tencentcloud-sdk-python-ags`）
- 如果需要则克隆并安装 [mini-swe-agent](https://github.com/SWE-agent/mini-SWE-agent)，包含完整依赖
- 将 `overlay/` 目录下的 AGS 适配代码覆盖到对应仓库中

### 4. 创建本地配置

创建 `my_config.yaml`，填入凭据和 LLM 配置：

```yaml
environment:
  tool_id: "sdt-xxxxxxxx"                    # 第 1 步获取的工具 ID
  region: "ap-chongqing"                     # AGS 地域（默认：ap-chongqing）

model:
  model_name: "anthropic/claude-sonnet-4-5"
  model_kwargs:
    api_key: "sk-ant-xxxxx"
```

安全提示：`my_config.yaml` 只应保留在本地，能用环境变量时更建议走环境变量。

**地域配置说明**：默认地域为 `ap-chongqing`（重庆）。如果你的 AGS 工具创建在其他地域，修改 `region` 即可。请在 [AGS 控制台](https://console.cloud.tencent.com/ags/sandbox/tool) 查看你的工具所在地域。

如果使用自定义 API 端点（如自建模型或代理），`model_name` 需要符合 [litellm 的 provider/model 格式](https://docs.litellm.ai/docs/providers)。自定义模型还需要设置 `cost_tracking: "ignore_errors"`：

```yaml
model:
  model_name: "openai/your-model-name"
  cost_tracking: "ignore_errors"
  model_kwargs:
    api_base: "https://your-api-endpoint.com/v1"
    api_key: "your-key"
```

### 5. 运行

**运行单个 instance（交互模式）：**

```bash
make run
```

以交互模式运行一个 SWE-bench Verified instance，实时显示每一步的思考、动作和输出。轨迹保存在 `results/interactive.traj.json`。

**完整评测（4 并发）：**

```bash
make run-full
```

运行全部 500 个 SWE-bench Verified instance，4 个并发 worker。可用 `make run-full WORKERS=8` 覆盖。

## 运行命令

| 命令 | 说明 |
|------|------|
| `make setup` | 克隆官方仓库、应用 overlay、安装所有依赖 |
| `make run` | 以交互模式运行单个 instance（默认 `-i 0 -y`） |
| `make run-full` | 运行全部 500 个 instance（默认 `WORKERS=4`） |
| `make logs` | 跟踪调试日志（在 `make run-full` 之后运行） |
| `make tail` | 美化输出最近更新的 trajectory JSON |
| `make clean` | 删除克隆的仓库和结果目录 |

## 结果

结果保存在 `results/` 目录下：

```
results/
├── interactive.traj.json                          # `make run` 的轨迹文件
├── minisweagent.log                              # `make run-full` 的运行日志
├── preds.json                                    # 所有 instance 的预测结果
├── exit_statuses_*.yaml                          # 退出状态汇总
└── <instance_id>/
    └── <instance_id>.traj.json                   # 每个 instance 的完整轨迹
```

## 配置说明

评测使用分层配置系统，多个 `-c` 配置按顺序合并：

| 配置 | 用途 |
|------|------|
| `swebench_ags` | 内置基础配置：prompt 模板、超时参数、AGS 端点默认值 |
| `my_config.yaml` | 你的凭据、工具 ID、LLM 设置 |

基础配置中的关键参数：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `environment.tool_id` | （必填） | AGS SWE 沙箱工具 ID |
| `environment.region` | `"ap-chongqing"` | AGS 地域 |
| `environment.timeout` | `60` | 单条命令执行超时（秒） |
| `environment.startup_timeout` | `120` | 沙箱实例启动超时（秒） |
| `environment.runtime_timeout` | `60` | SWE-ReX HTTP 请求超时（秒） |
| `environment.timeout_duration` | `"1h"` | 沙箱实例总存活时间 |
| `agent.step_limit` | `250` | 每个 instance 的最大 Agent 步数 |
| `agent.cost_limit` | `3.0` | 每个 instance 的最大 LLM 费用（USD） |

**超时参数详解：**

- **`timeout`**（60s = 1 分钟）：沙箱内单条 bash 命令的最大执行时间。Agent 每一步执行的命令（如跑测试）如果超过该时限，会被终止并抛出 `CommandTimeoutError`。
- **`startup_timeout`**（120s = 2 分钟）：等待 AGS 创建沙箱实例并就绪的最大时间，包括镜像拉取和容器初始化。
- **`runtime_timeout`**（60s = 1 分钟）：SWE-ReX 每次 API 调用（如 `is_alive`、`execute`）的 HTTP 请求超时。注意这**不限制**命令执行时间，只限制网络往返。如果 AGS 网关响应较慢，可以调大此值。
- **`timeout_duration`**（"1h"）：沙箱实例在 AGS 侧的总存活时间。超过该时限后 AGS 会自动回收实例，后续 API 调用会收到 404 并抛出 `EnvironmentExpiredError`。对于步数较多的长时间任务，建议调大到 `"2h"` 或更长。

所有超时参数均可在 `my_config.yaml` 中覆盖：

```yaml
environment:
  timeout: 120           # 单条命令 2 分钟
  startup_timeout: 300   # 实例创建 5 分钟
  runtime_timeout: 120   # HTTP 超时 2 分钟
  timeout_duration: "2h" # 实例存活 2 小时
```

## AGS 系统镜像

AGS 提供了**系统镜像** —— 内置在 AGS 平台中、经过镜像预热的容器镜像。使用系统镜像创建沙箱实例时，启动速度显著更快。

在本示例中，mini-swe-agent 会自动根据每个 SWE-bench instance 推导出镜像名称，并以系统镜像方式传给 AGS：

```json
{
    "ToolId": "sdt-xxxxxxxx",
    "ClientToken": "unique-request-id",
    "Timeout": "1h",
    "CustomConfiguration": {
        "Image": "swebench/sweb.eval.x86_64.django__django-16379:latest",
        "ImageRegistryType": "system"
    }
}
```

可以在 [AGS 系统镜像管理页面](https://console.cloud.tencent.com/ags/sandbox/template) 查看所有可用的系统镜像。

> **注意**：并非全部 500 个 SWE-bench Verified 镜像都已作为系统镜像提供。请在看板中确认支持的镜像列表，并使用 `--filter` 只运行已支持的 instance。

## 常见失败原因

### `Failed to check image availability`

该 instance 对应的镜像未在 AGS 中作为系统镜像提供。在 [AGS 系统镜像管理页面](https://console.cloud.tencent.com/ags/sandbox/template) 查看可用镜像列表，并使用 `--filter` 只运行支持的 instance。

### `CommandTimeoutError: Timeout (60s) exceeded`

某一条命令执行超时。在配置中增大 `environment.timeout`。

### `404 Not Found` / `EnvironmentExpiredError`

AGS 沙箱实例已过期或被停止。SWE-ReX 会立即抛出 `EnvironmentExpiredError`。如果频繁出现，增大 `environment.timeout_duration`。

### `Error calculating cost for model`

在 model 配置中添加 `cost_tracking: "ignore_errors"`。

### `RuntimeError: SandboxTool sdt-xxx not found`

在 [AGS 控制台](https://console.cloud.tencent.com/ags) 确认工具 ID、地域和工具状态。

## 更新上游

由于 overlay 是叠加在官方上游仓库上的，更新时只需：

```bash
make clean
make setup
```

如果上游修改了 overlay 也修改的文件，可能需要更新 overlay 文件。详见 [overlay/OVERLAY.md](overlay/OVERLAY.md)。

## 说明

- 这不是官方的 mini-swe-agent 或 SWE-ReX 发布版本。
- AGS 集成作为 Cookbook overlay 分发。
- 上游项目：[SWE-agent/mini-SWE-agent](https://github.com/SWE-agent/mini-SWE-agent)、[SWE-agent/SWE-ReX](https://github.com/SWE-agent/SWE-ReX)
