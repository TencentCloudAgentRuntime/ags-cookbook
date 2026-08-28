# 在 AGS 上运行 Windows Agent Arena

这个示例通过一组很小的 overlay，在 AGS（Agent Sandbox）上运行公开的 [Windows Agent Arena](https://github.com/microsoft/WindowsAgentArena)。

overlay 会尽量保留 WAA 原生 runner、任务、Navi agent 和 evaluator，只增加 AGS sandbox 启动逻辑，并覆盖少量必须适配远程 AGS Windows sandbox 的 WAA 文件。

需要注意的是，AGS 上的 WAA server 是基于**腾讯云 Windows Server 2025（64 位英文版）** 制作的，sandbox 内的操作系统语言、默认字体、内置组件、PowerShell / .NET 版本、激活状态等，都与该基础镜像保持一致。另外 Windows Server 2025 属于**服务器版**，如果 agent / 任务依赖仅在 Windows 10 / Windows 11 客户端版本上才具备的特性（例如某些 UWP / Microsoft Store 应用），这些组件可能缺失或行为不同。

## 准备条件

- `git`
- `uv`
- AGS API Key
- 一个兼容 WAA 的 AGS sandbox template
- OpenAI-compatible 模型接口

## 安装

### 1. 进入当前示例目录

```bash
cd /path/to/ags-cookbook/examples/waa-ags
```

### 2. 克隆 WindowsAgentArena

```bash
git clone https://github.com/microsoft/WindowsAgentArena.git waa
```

### 3. 应用 overlay

```bash
cp -R overlay/WindowsAgentArena/. waa/
```

### 4. 配置环境变量

```bash
cp .env.example .env
```

至少填写这些变量：

```bash
E2B_API_KEY=your_api_key_here
E2B_DOMAIN=ap-guangzhou.tencentags.com
# waa tool前端页面正在发布中，tool id创建可以先参考scripts中的说明
AGS_TEMPLATE=your_waa_tool_id
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_BASE_URL=https://api.openai.com/v1
```

请保护好这个 `.env`。

### 5. 安装依赖

WAA 当前需要 Python 3.10。

```bash
make setup
```

这会创建 `waa/src/win-arena-container/client/.venv`，安装 overlay 后的 `requirements.txt`，并安装 Playwright Chromium。

## 运行

```bash
make run
```

默认会运行 `evaluation_examples_windows/test_small.json`，使用 `gpt-4o`、`som_origin=a11y`、`a11y_backend=uia`。

需要自定义参数时：

```bash
make run MODEL=gpt-4o TEST_META=evaluation_examples_windows/test_small.json MAX_STEPS=15
```

也可以直接运行 WAA：

```bash
cd waa/src/win-arena-container/client
.venv/bin/python run_ags.py \
  --model gpt-4o \
  --test_all_meta_path evaluation_examples_windows/test_small.json \
  --som_origin a11y \
  --a11y_backend uia \
  --max_steps 15
```

## Overlay 文件

新增到 WindowsAgentArena 的文件：

- `src/win-arena-container/client/run_ags.py`

会被 overlay 覆盖的上游文件：

- `src/win-arena-container/client/desktop_env/envs/desktop_env.py`
- `src/win-arena-container/client/desktop_env/controllers/setup.py`
- `src/win-arena-container/client/requirements.txt`

## 工作方式

`run_ags.py` 会：

1. 读取 `examples/waa-ags/.env`
2. 通过 AGS/E2B-compatible SDK 创建 Windows sandbox
3. 将 sandbox 内端口代理到本地：
   - `5000`：WAA Windows-side server
   - `9222`：Chrome/Edge CDP
   - `8006`：noVNC
   - `8080`：VLC HTTP
4. 设置 `WAA_AGS_REMOTE=1`
5. 启动原生 WAA：`run.py --emulator_ip 127.0.0.1 ...`
6. 退出时清理本地代理并 kill AGS sandbox

启动后，可以打开 noVNC：

```bash
http://127.0.0.1:8006
```

## 存储说明

- WAA sandbox **暂不支持** COS、CFS、CBS 等腾讯云存储的直接挂载，sandbox 内没有对应的挂载点，请勿依赖挂载方式读写这些存储。
- 如果 agent / 任务确实需要访问外部存储（例如 COS），只能在 sandbox 内部通过网络方式（COS SDK / API / 工具）自行访问。
- 关于 sandbox 访问 COS 的域名选择：
  - **同地域访问**：当 sandbox 与 COS Bucket 位于同一个地域时，直接使用 COS 的**默认域名**（形如 `<BucketName-APPID>.cos.<region>.myqcloud.com`）即可，此时请求会**自动走内网**，产生的是内网流量、不产生外网下行流量费用（请求次数费用仍会计费）。
  - **跨地域访问**：当 sandbox 与 COS Bucket 不在同一地域时，也可以通过 COS 提供的**内网全球加速域名**（形如 `<BucketName-APPID>.cos-internal.accelerate.tencentcos.cn`）走腾讯云内网访问，实现跨地域内网访问；如果使用普通的**全球加速域名**（`<BucketName-APPID>.cos.accelerate.myqcloud.com`）或跨地域的默认域名，则会走外网并产生相应的公网流量费用。
- 因此在跨地域场景下，如果对成本和网络路径敏感，优先选用**内网全球加速域名**。
- 具体的域名列表、Endpoint 规则和全球加速的开通方式，请参考腾讯云官方文档：[COS 地域和访问域名](https://cloud.tencent.com/document/product/436/6224)。

## 注意事项

- 这不是 WindowsAgentArena 上游官方发行版。
- overlay 中的相关源码派生自 WindowsAgentArena，继续遵循 MIT License。
- 上游项目：[microsoft/WindowsAgentArena](https://github.com/microsoft/WindowsAgentArena)
