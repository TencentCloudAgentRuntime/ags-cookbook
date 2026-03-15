# Browser Agent: 基于云端沙箱的浏览器自动化

本示例展示如何使用 AgentSandbox 云端沙箱运行浏览器，结合 LLM 实现智能网页自动化任务。

## 架构

```
┌─────────────┐     Tool Call     ┌─────────────┐      CDP       ┌─────────────┐
│     LLM     │ ───────────────▶  │   Browser   │ ─────────────▶ │  AgentSandbox  │
│  (GLM-4.7)  │                   │    Agent    │                │   (browser) │
└─────────────┘                   └─────────────┘                └─────────────┘
      ▲                                 │                              │
      │                                 │◀─────────────────────────────┘
      │                                 │      Page State / Result
      └─────────────────────────────────┘
              Observation
```

**核心特性**：
- 浏览器运行在云端沙箱，本地通过 CDP 协议远程控制
- 支持 VNC 实时查看浏览器画面
- LLM 通过 Function Calling 驱动浏览器操作

## 快速开始

### 1. 安装依赖

```bash
uv sync
```

### 2. 配置 API Key

运行前设置环境变量：

```bash
export E2B_API_KEY="your_ags_api_key"           # AgentSandbox API Key
export LLM_API_KEY="your_llm_api_key"           # LLM API Key
export LLM_API_URL="https://your-llm-api/v1/chat/completions"
export LLM_MODEL="glm4.7"                       # 可选，默认为 glm4.7
export E2B_DOMAIN="ap-guangzhou.tencentags.com" # 可选
```

### 3. 运行示例

```bash
uv run main.py
```

运行后会输出 VNC 链接，可在浏览器中实时观看自动化过程。

## 可用工具

| 工具 | 说明 |
|------|------|
| `navigate` | 导航到指定 URL |
| `highlight_elements` | 高亮页面可交互元素并返回编号 |
| `click_element` | 按编号点击元素 |
| `click_text` | 点击包含指定文本的元素 |
| `get_page_text` | 获取页面文本内容 |
| `scroll_down` | 向下滚动页面 |
| `screenshot` | 截取页面截图 |
| `task_complete` | 标记任务完成 |

## 工作流程

1. **创建沙箱**：启动 `browser-v1` 模板的云端沙箱
2. **连接浏览器**：通过 CDP 协议连接沙箱内的 Chromium
3. **LLM 决策**：LLM 根据页面状态选择工具调用
4. **执行操作**：Agent 执行浏览器操作并返回结果
5. **循环迭代**：直到任务完成或达到最大步数

## 依赖

- Python >= 3.12
- e2b >= 2.9.0
- playwright >= 1.57.0
- requests >= 2.32.5

## 快速开始

```bash
make run
```

