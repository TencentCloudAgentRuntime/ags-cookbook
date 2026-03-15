# Shop Assistant - 购物车自动化演示

使用 Agent Sandbox 的 Browser 沙箱 + Playwright，在已登录状态下搜索 Amazon 商品并自动加入购物车，最后查看购物车列表。支持从本地上传 Cookie 实现免登录。

## 功能特性

- 免登录体验：导入本地 Cookie 后直接进行购物流程
- 自动化流程：搜索 → 进入商品页 → 加入购物车 → 查看购物车
- 远程浏览器操控：通过 Browser 沙箱运行 Playwright
- 稳健策略：多选择器兜底、超时重试、加载状态判断

## 业务场景

适用于电商场景的自动化验证与演示：
- 自动化验证「加入购物车」链路
- 在稳定登录态下回放关键路径
- 支持在云端远程观察执行过程（VNC 调试）

## 执行流程

1. 上传并导入本地 Cookie（cookie.json）
2. 打开 Amazon 首页并搜索目标关键词
3. 解析第一个商品并进入详情页
4. 点击加入购物车并校验结果
5. 打开购物车页查看商品条目

## 运行方式

```bash
# 设置环境变量
export E2B_DOMAIN='tencentags.com'
export E2B_API_KEY='your_ags_api_key'  # 由腾讯云 Agent Sandbox 产品提供

# 安装依赖
pip install -r requirements.txt

# 准备 Cookie（免登录）
# 将你的 Amazon Cookie 导出为 cookie.json 放在当前目录（参考 cookie.json.example 的结构）

# 运行演示
python automation_cart_demo.py
```

## 常见问题

- Cookie 导入失败
  - 确认 cookie.json 存在且为数组格式，包含 name、value、domain、path 等字段
  - 若 Cookie 过期，请重新登录导出
- 未设置 E2B_API_KEY
  - 请先设置环境变量：export E2B_API_KEY='your_ags_api_key'  # 由腾讯云 Agent Sandbox 产品提供
- 想查看执行过程（VNC）
  - 控制台会给出说明；在本机安全环境下可开启调试输出（避免在共享环境直接打印带令牌链接）

## 快速开始

```bash
make run
```

