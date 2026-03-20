# 在 AGS 上运行 OSWorld

这个示例让你通过 cookbook 中提供的 overlay，在 AGS（Agent Sandbox）上运行公开的 [OSWorld](https://github.com/xlang-ai/OSWorld)。

它的做法是把一组很小的 overlay 复制到你本地的 OSWorld 仓库里。这个 overlay 会新增 `ags` provider，并覆盖少量必须为 AGS 调整的上游文件。

## 你会得到什么

- OSWorld 中可直接使用 `provider_name=ags`
- 面向 AGS 的本地 HTTP/WebSocket 代理
- 用于远程桌面观察的 noVNC 支持

## 开始前需要准备

你需要：

- `uv`（用于管理隔离的 Python 3.10 环境）
- `git`
- AGS API Key
- 一个兼容 OSWorld 的 AGS sandbox template
- 你打算运行的模型对应的 LLM API Key

## 安装步骤

### 1. 进入当前示例目录

```bash
cd /path/to/ags-cookbook/examples/osworld-ags
```

### 2. 克隆 OSWorld 到 `./osworld`

```bash
git clone https://github.com/xlang-ai/OSWorld.git osworld
```

### 3. 应用 overlay

```bash
cp -R overlay/OSWorld/. osworld/
```

### 4. 配置环境变量

```bash
cp .env.example osworld/.env
```

至少填写这些变量：

```bash
E2B_API_KEY=your_api_key_here
E2B_DOMAIN=ap-singapore.tencentags.com
AGS_TEMPLATE=your_osworld_template_id
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_BASE_URL=https://api.openai.com/v1
```

### 5. 在隔离的 uv 环境中安装依赖
请注意：当前只支持 Python 3.10
```bash
make setup
```

这会用 `uv` 创建 `osworld/.venv`，按需安装 Python 3.10，并把 overlay 后的 `requirements.txt` 安装到该虚拟环境中。overlay 会把 AGS 依赖写入 `requirements.txt`，包括 `e2b-code-interpreter` 和 `aiohttp`。

## 运行

### 快速检查

```bash
make run
```

如果这一步能成功，说明 AGS provider 已经安装正确。

### 运行多环境模式

```bash
cd osworld
uv run --python .venv/bin/python run_multienv.py --provider_name ags --model gpt-4o --num_envs 2
```

## Overlay 会改哪些文件

新增到 OSWorld 的文件：

- `desktop_env/providers/ags/__init__.py`
- `desktop_env/providers/ags/config.py`
- `desktop_env/providers/ags/manager.py`
- `desktop_env/providers/ags/provider.py`

会被 overlay 覆盖的上游文件：

- `desktop_env/desktop_env.py`
- `desktop_env/providers/__init__.py`
- `desktop_env/controllers/python.py`
- `run_multienv.py`
- `requirements.txt`

## 访问 VNC

启动后，AGS provider 会在日志中打印本地代理端口。找到 VNC 对应端口后，在浏览器打开：

```bash
http://localhost:<vnc_port>/vnc.html
```

## 说明

- 这不是 OSWorld 上游官方发行版。
- AGS provider 以 cookbook overlay 的形式在这里分发。
- overlay 中的相关源码派生自 OSWorld，继续遵循 Apache-2.0。
- 上游项目：[xlang-ai/OSWorld](https://github.com/xlang-ai/OSWorld)
