# Shop Assistant：购物车自动化示例

本示例使用 AGS 浏览器沙箱与 Playwright，在 Amazon 上完成搜索商品、进入详情页、尝试加购并查看购物车的流程。

## 前置条件

- Python >= 3.12
- `uv`
- `E2B_API_KEY`
- 必填 `E2B_DOMAIN`
- 如果你想测试登录态流程，可选提供 `cookie.json`

## 必要环境变量

```bash
export E2B_API_KEY="your_ags_api_key"
export E2B_DOMAIN="ap-guangzhou.tencentags.com"
export KEEPALIVE_SECONDS="0"  # 可选，避免执行结束后长时间停留
```

## 本地命令

```bash
make setup
make run
```

## 预期结果

成功运行后，示例会：

- 在远程浏览器沙箱中打开 Amazon
- 搜索配置的商品关键词
- 进入某个商品详情页
- 尝试执行加购
- 打开购物车页面

当 `cookie.json` 不存在时，也支持 guest 模式，因此 Cookie 不再是硬阻塞条件。

## 常见失败提示

- 如果 Amazon 触发反爬或登录验证，尝试更换 Cookie，或接受 guest 模式下的限制
- 如果沙箱启动失败，检查 `E2B_API_KEY` 和 `E2B_DOMAIN`

## 说明

- 控制台输出会包含用于观察浏览器过程的 VNC / 调试提示
- 不要提交真实 Cookie 或账号数据
