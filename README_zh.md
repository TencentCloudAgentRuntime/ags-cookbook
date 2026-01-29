# Agent Sandbox Cookbook

Agent Sandbox沙箱使用指南和示例集合。

## 项目简介

Agent Sandbox Cookbook 是一个全面的使用指南和示例集合，展示了如何通过现有的SDK，使用Agent Sandbox沙箱构建强大的AI Agent应用。本项目包含了从基础教程到高级示例的完整学习路径。

## 项目结构

```
ags-cookbook/
├── .gitignore                              
├── LICENSE                                 
├── README.md                               # 项目主文档
├── CODE_OF_CONDUCT.md                      # 行为准则
├── CONTRIBUTING.md                         # 贡献指南
├── benchmarks/                             # 性能基准测试
│   └── k6/                                # K6 压力测试脚本
│       ├── README.md
│       ├── sandbox-stress-test.js
│       ├── sandbox-stress-test-data-plane.js
│       ├── sandbox-stress-test-e2b-api.js
│       └── sandbox-stress-test-non-exec.js
├── tutorials/                              # 教程文档
│   ├── sdk/
│   │   ├── e2b/
│   │   │   ├── e2b_base.ipynb            # E2B SDK基础教程（包含代码沙箱教程）
│   │   │   └── browser_vnc.ipynb         # 浏览器沙箱教程
│   │   └── go/
│   │       ├── README.md
│   │       └── example_test.go           # Go SDK示例
│   └── yunapi/
│       └── python/
│           └── custom.ipynb              # 自定义API教程
└── examples/                               # 示例代码
    ├── README.md                          
    ├── browser-agent/                     # 浏览器自动化代理示例
    │   ├── README.md                      
    │   ├── main.py          
    │   └── pyproject.toml               
    ├── data-analysis/                     # 数据分析示例
    │   ├── README.md                      
    │   ├── multi_context_demo.py          
    │   └── requirements.txt               
    ├── html-processing/                   # HTML协作处理示例
    │   ├── README.md                      
    │   ├── html_collaboration_demo.py     
    │   └── requirements.txt               
    ├── mini-rl/                           # 迷你强化学习示例
    │   ├── README.md                      
    │   ├── main.py          
    │   └── pyproject.toml               
    ├── mobile-use/                        # 移动端自动化示例
    │   ├── README.md                      
    │   ├── quickstart.py                  # 快速入门示例
    │   ├── batch.py                       # 批量操作脚本（多进程 + 异步）
    │   ├── sandbox_connect.py             # 单沙箱连接工具（CLI）
    │   ├── test_mobile_actions.py         # 单元测试
    │   └── requirements.txt               
    └── shop-assistant/                    # 购物车自动化示例
        ├── README.md                      
        ├── automation_cart_demo.py        
        └── requirements.txt               
```

## 主要特性

### 多沙箱协作能力
- **Code + Browser协作**：代码沙箱与浏览器沙箱无缝协作
- **多Context环境隔离**：每个Context拥有独立的变量空间
- **文件系统集成**：沙箱间通过文件系统实现数据传递

### 复杂数据处理演示
- **大规模数据集处理**：支持千级以上数据量处理
- **完整数据清洗流程**：异常值处理、特征工程、数据质量优化
- **专业分工协作**：数据预处理、分析、可视化专家协同工作

### Web开发与自动化
- **HTML动态编辑**：程序化修改网页内容
- **可视化验证**：通过截图对比验证编辑效果
- **浏览器自动化**：支持复杂的Web交互操作

### 专业数据可视化
- **数据清洗前后对比**：直观展示清洗效果
- **综合业务仪表板**：多维度数据分析图表
- **相关性热力图**：业务指标关联分析

## 快速开始

### 环境要求
- Python 3.8+

### 环境配置

```bash
export E2B_API_KEY="your-api-key-here"
export E2B_DOMAIN="tencentags.com"  # 可选，默认使用此域名
```

### 运行示例

每个示例都有独立的依赖管理，请参考具体示例目录中的说明文档。

## 使用指南

### 1. 基础教程

**代码解释器沙箱** - `tutorials/sdk/e2b/e2b_base.ipynb`
- 创建和管理沙箱环境
- 执行代码和处理结果
- 文件上传和下载
- 多Context环境隔离

**浏览器沙箱** - `tutorials/sdk/e2b/browser_vnc.ipynb`
- VNC可视化界面操作
- Playwright程序化控制
- 文件系统与浏览器集成
- Cookie和会话管理

### 2. 高级示例

**数据分析示例** - `examples/data-analysis/`
- 多Context协作处理复杂数据
- 完整的数据清洗和分析流程
- 专业数据可视化图表

**HTML协作处理示例** - `examples/html-processing/`
- Code沙箱与Browser沙箱协作
- HTML动态编辑和可视化验证
- Web开发工作流演示

**购物车自动化示例** - `examples/shop-assistant/`
- 登录态下的电商加购流程
- Cookie 导入免登录
- 远程浏览器控制与调试

## 技术架构

### 沙箱环境
- **代码解释器沙箱**：支持Python、JavaScript、R等多种语言
- **浏览器沙箱**：内置浏览器，支持VNC和Playwright控制
- **隔离执行**：每个代码块在独立环境中运行
- **持久化存储**：支持文件系统操作和数据持久化
- **沙箱协作**：不同类型沙箱间可以通过文件系统协作

### 依赖管理
- **模块化依赖**：每个示例都有独立的 `requirements.txt`
- **版本隔离**：避免不同示例间的依赖冲突
- **按需安装**：只安装当前示例所需的依赖包

## 贡献指南

欢迎提交新的示例和教程！

1. Fork 本仓库
2. 创建功能分支：`git checkout -b feature/new-example`
3. 提交更改：`git commit -am 'Add new example'`
4. 发起 Pull Request

### 示例贡献规范

新增示例请遵循以下结构：
```
examples/your-example-name/
├── README.md              # 详细说明文档
├── main_script.py         # 主要演示脚本
└── requirements.txt       # 示例专用依赖
```

每个示例应包含：
- **README.md**：功能描述、使用场景、运行步骤、预期输出
- **完整的运行指令**：从依赖安装到执行的完整步骤
- **独立的依赖管理**：使用专用的 `requirements.txt`
- **清晰的输出说明**：描述生成的文件和预期结果

## 许可证

本项目基于 Apache 2.0 许可证开源。详见 [LICENSE](LICENSE-Agent%20Sandbox%20Cookbook.txt) 文件。
