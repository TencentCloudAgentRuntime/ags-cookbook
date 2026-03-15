# HTML协作处理演示

**Code + Browser沙箱协作** - 展示HTML创建、编辑、渲染的完整流程

## 功能特性

- **双沙箱协作**：Code沙箱编辑 + Browser沙箱渲染
- **可视化对比**：编辑前后截图对比
- **完整工作流**：创建 → 渲染 → 编辑 → 再渲染
- **文件流转**：本地 ↔ Browser ↔ Code ↔ Browser ↔ 本地

## 业务场景

模拟Web开发中的常见协作场景：
- 设计师创建HTML模板
- 开发者程序化修改内容
- 实时预览修改效果
- 生成前后对比截图

## 执行流程

### 1. 本地HTML创建
- 创建带有渐变背景的响应式HTML页面
- 包含时间戳和样式设计
- 保存为 `demo.html`

### 2. Browser沙箱首次渲染
- 上传HTML到Browser沙箱
- 使用Playwright进行页面渲染
- 生成 `screenshot_before.png`

### 3. Code沙箱HTML编辑
- 将HTML文件传输到Code沙箱
- 执行Python代码进行内容编辑
- 添加"Edit by Code Interpreter Sandbox"标识
- 生成 `demo_edited.html`

### 4. Browser沙箱再次渲染
- 上传编辑后的HTML到Browser沙箱
- 再次渲染并截图
- 生成 `screenshot_after.png`

### 5. 结果对比
- 下载所有文件到本地
- 生成前后对比截图
- 直观展示编辑效果

## 输出文件

运行后生成4个文件：
- `demo.html` - **原始HTML文件**
- `demo_edited.html` - **Code沙箱编辑后的HTML**
- `screenshot_before.png` - **编辑前页面截图**
- `screenshot_after.png` - **编辑后页面截图**

## 运行方式

```bash
# 设置环境变量
export E2B_DOMAIN='tencentags.com'
export E2B_API_KEY='your_ags_api_key'  # 由腾讯云 Agent Sandbox 产品提供

# 安装依赖
pip install -r requirements.txt

# 运行演示
python html_collaboration_demo.py

# 查看结果
ls html_collaboration_output/
```

## 协作流程图

```
本地创建HTML
     ↓
Browser沙箱 → 截图1 (原始效果)
     ↓
Code沙箱编辑 → 添加新内容
     ↓
Browser沙箱 → 截图2 (编辑效果)
     ↓
本地对比 → 直观看到差异
```

## 技术亮点

### 1. 双沙箱协作
- **Browser沙箱**：专注渲染和截图
- **Code沙箱**：专注代码编辑和处理
- **文件系统**：作为沙箱间的通信桥梁

### 2. 实时编辑验证
- 程序化修改HTML内容
- 动态添加时间戳和标识
- 保持原有样式和结构

### 3. 可视化对比
- 像素级截图对比
- 直观展示编辑效果
- 支持复杂页面布局

### 4. 完整工作流
- 端到端的处理流程
- 自动化文件管理
- 错误处理和资源清理

## 扩展应用

基于此示例可以扩展：
- **多轮编辑**：连续多次编辑和渲染
- **样式优化**：CSS自动优化和美化
- **内容生成**：AI生成HTML内容
- **A/B测试**：多版本页面对比
- **响应式测试**：不同屏幕尺寸截图

## 实际应用场景

- **Web开发调试**：快速验证HTML修改效果
- **自动化测试**：页面变更的视觉回归测试
- **内容管理**：批量处理HTML模板
- **设计验证**：设计稿与实际效果对比
- **文档生成**：动态生成HTML报告

## 快速开始

```bash
make run
```

