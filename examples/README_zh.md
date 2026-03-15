# Examples - 示例代码

本目录包含Agent Sandbox沙箱的各种使用示例，每个示例都有独立的目录结构。

## 目录结构

```
examples/
├── browser-agent/         # 浏览器自动化 Agent
├── custom-image-go-sdk/   # Go SDK 自定义镜像启动
├── data-analysis/         # 数据分析
├── html-processing/       # HTML 协作处理
├── hybrid-cookbook/        # Go SDK 混合流程
├── mini-rl/               # 强化学习沙箱
├── mobile-use/            # 移动端自动化
└── shop-assistant/        # 购物车自动化
```

每个示例目录包含各自的 `README.md`、`Makefile` 及源代码，详见各示例 README。

## 示例列表

### browser-agent - 浏览器自动化Agent

展示如何使用 AgentSandbox 云端沙箱运行浏览器，结合 LLM 实现智能网页自动化：

- **云端浏览器**：浏览器运行在沙箱，本地通过 CDP 远程控制
- **LLM 驱动**：通过 Function Calling 智能决策浏览器操作
- **VNC 可视化**：实时查看浏览器画面
- **丰富工具集**：导航、高亮元素、点击、截图等

**适用场景**：
- 自动化表单填写
- Web 端到端测试

**技术栈**：playwright

### data-analysis - 数据分析示例

展示如何使用Agent Sandbox进行复杂的数据分析工作流，包括：

- **多Context环境隔离**：3个独立Context协作完成数据处理
- **完整数据处理流程**：从数据清洗到可视化分析
- **真实业务场景**：5000产品电商数据分析和优化

**适用场景**：
- 需要多步骤数据处理的项目
- 要求环境隔离的协作场景
- 复杂的商业数据分析

**技术栈**：pandas, numpy, matplotlib, seaborn, scipy

### html-processing - HTML协作处理示例

展示Code和Browser沙箱的协作能力，包括：

- **双沙箱协作**：Code沙箱编辑 + Browser沙箱渲染
- **可视化对比**：编辑前后截图对比
- **完整工作流**：创建 → 渲染 → 编辑 → 再渲染
- **文件流转**：本地 ↔ Browser ↔ Code ↔ Browser ↔ 本地

**适用场景**：
- Web开发中的HTML编辑和预览
- 自动化页面内容修改
- 视觉回归测试
- HTML模板批量处理

**技术栈**：playwright, HTML/CSS

### mini-rl - 强化学习沙箱示例

展示如何在强化学习场景中集成 AgentSandbox 沙箱：

- **完整流程**：模型输出 ToolCall → Runtime 解析 → 沙箱执行 → 结果回填
- **RL 视角**：State/Action/Environment/Observation/Reward 完整映射
- **最小示例**：单文件演示核心概念

**适用场景**：
- VERL 等 RL 框架集成沙箱
- 数学推理任务的代码执行
- Agent 工具调用训练

**技术栈**：AgentSandbox

### custom-image-go-sdk - Go SDK 自定义镜像示例

展示如何使用 Go SDK 启动自定义镜像沙箱，包括：

- **控制面启动**：通过 AGS 控制面 API 启动实例
- **启动参数覆盖**：通过环境变量覆盖镜像/命令/端口/探针
- **数据面执行**：连接实例并执行代码

**适用场景**：
- 企业镜像启动配置验证
- 启动命令与健康探针联调
- 基于模板环境的自动化启动流程

**技术栈**：Go, 腾讯云 AGS SDK

### hybrid-cookbook - Go SDK 混合流程示例

展示最小“控制面 + 数据面”混合工作流：

- **启动沙箱**：基于工具模板创建实例
- **执行代码**：连接实例后执行代码
- **自动清理**：退出时停止实例，避免资源泄漏

**适用场景**：
- Go SDK 集成快速验证
- 新成员混合流程上手

**技术栈**：Go, 腾讯云 AGS SDK

### mobile-use - 移动端自动化示例

展示如何使用 AgentSandbox 云端沙箱运行 Android 设备，结合 Appium 实现移动端自动化：

- **云端 Android 设备**：Android 运行在沙箱，本地通过 Appium 远程控制
- **屏幕流**：通过 ws-scrcpy 实时查看屏幕
- **元素操作**：通过文本或 resource-id 查找并点击元素
- **CLI 工具**：`sandbox_connect.py` 用于连接已存在的沙箱
- **批量测试**：高并发沙箱测试（多进程 + 异步）

**适用场景**：
- 移动应用自动化测试
- 移动端 UI/UX 测试
- 高并发移动测试
- GPS 定位模拟

**技术栈**：Appium, Android, pytest

### shop-assistant - 购物车自动化示例

展示使用Browser沙箱与Playwright在登录态下完成“搜索→加购→查看购物车”的自动化演示。

- 免登录体验：本地Cookie导入
- 自动化链路：搜索、商品页、加购、购物车
- 远程调试：VNC观察执行过程（按需开启）

**适用场景**：
- 电商流程回放与验证
- 登录态关键路径演示
- 远程自动化演示

**技术栈**：playwright

## 统一命令接口

所有示例都提供统一命令：

```bash
make run
```

- `make run`：执行主流程

## 贡献新示例

欢迎贡献新的示例！请遵循以下结构：

```
examples/your-example-name/
├── README.md              # 示例说明
├── main_script.py         # 主要演示脚本
└── requirements.txt       # 额外依赖（如需要）
```

每个示例的README应包含：
- 功能描述
- 使用场景
- 运行步骤
- 预期输出
- 技术栈说明
