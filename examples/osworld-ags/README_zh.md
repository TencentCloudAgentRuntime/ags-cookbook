# 在 AGS 上运行 OSWorld

这个示例让你通过 cookbook 中提供的 overlay，在 AGS（Agent Sandbox）上运行公开的 [OSWorld](https://github.com/xlang-ai/OSWorld)。

它的做法是把一组很小的 overlay 复制到你本地的 OSWorld 仓库里。这个 overlay 会新增 `ags` provider，并覆盖少量必须为 AGS 调整的上游文件。

## 你会得到什么

- OSWorld 中可直接使用 `provider_name=ags`
- 面向 AGS 的本地 HTTP/WebSocket 代理
- 用于远程桌面观察的 noVNC 支持

## 开始前需要准备

如需先创建自己的 OSWorld Tool，参见[自定义镜像示例](../osworld-custom-image/README_zh.md)。

你需要：

- `uv`（用于管理隔离的 Python 3.12.12 环境）
- `git`
- AGS API Key
- 一个兼容 OSWorld 的 AGS sandbox template，其中包含 `/bin/bash`、
  `/usr/bin/socat`、`python3` 和 `sudo`
- 你打算运行的模型对应的 LLM API Key

## 安装步骤

### 1. 进入当前示例目录

```bash
cd /path/to/ags-cookbook/examples/osworld-ags
```

### 2. 克隆 OSWorld 到 `./osworld`

```bash
make clone
```

该命令会检出 OSWorld commit
[`84aee655c2afb6b77ecf39884432615ba345c031`](https://github.com/xlang-ai/OSWorld/commit/84aee655c2afb6b77ecf39884432615ba345c031)。
`make setup` 会在安装依赖前校验当前 checkout。

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
AGS_SUDO_PASSWORD=password
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_BASE_URL=https://api.openai.com/v1
```

`AGS_SUDO_PASSWORD` 必须与沙箱用户的 sudo 密码一致。标准 OSWorld 镜像使用
`password`。

### 5. 在隔离的 uv 环境中安装依赖

```bash
make setup
```

这会用 `uv` 创建 `osworld/.venv`，按需安装 Python 3.12.12，并安装上游
`requirements.txt` 中的 OSWorld 依赖和 `requirements-ags.lock` 中的 AGS
专用依赖。

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

如需批量验证任务初始化、但不调用 LLM API，可设置
`OSWORLD_MOCK_LLM_DONE=1`。该 mock agent 会在每个任务初始化完成后直接返回
`DONE`。

## Overlay 会改哪些文件

新增到 OSWorld 的文件：

- `desktop_env/providers/ags/__init__.py`
- `desktop_env/providers/ags/config.py`
- `desktop_env/providers/ags/cdp_proxy.py`
- `desktop_env/providers/ags/manager.py`
- `desktop_env/providers/ags/provider.py`
- `desktop_env/providers/ags/sandbox_setup.py`
- `desktop_env/providers/ags/socat_wrapper.sh`
- `requirements-ags.lock`
- `run_multienv.py`

会被 overlay 覆盖的上游文件：

- `desktop_env/desktop_env.py`
- `desktop_env/providers/__init__.py`

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
