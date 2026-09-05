# 在 AGS 上自定义 OSWorld 镜像

本示例先直接启动 OSWorld1 base OCI，输出可打开的 noVNC 链接；再演示用
Dockerfile 安装 Claude Code、推送到自己的 CCR/TCR，并创建自定义沙箱。
完整的镜像约定与使用说明见[中文指南](docs/image-guide.zh-CN.md)。

## 准备

- Python 3.11+、uv、具有 AGS 权限的腾讯云凭证。
- 定制镜像时需要 Docker 和自己的 CCR/TCR 仓库。
- `.env.example` 暂使用个人 CCR 验证候选；`ags-image` 正式发布尚待批准。

```bash
cd examples/osworld-custom-image
make setup
# 编辑 .env，填写腾讯云凭证与 OSWORLD_BASE_IMAGE
make quickstart
```

无需构建镜像。脚本创建名称含 `auto-snapshot` 的 custom Tool，等 Tool ACTIVE
后立即启动实例，不等待快照制作。已有匹配快照就复用，否则允许冷启动并由平台
后台继续制作。首次镜像准备与冷启动可能较慢。

启动成功后输出 Tool ID、Instance ID 和 noVNC URL，不强制执行额外校验。交互实例保留
最多一小时，体验后执行 `make clean`。参数固定为 8 CPU、16 GiB 内存、公开
custom Tool 支持的 `Storage=20Gi`；镜像保证 shm 至少 4 GiB。它不代表所有
OSWorld2 heavy task 都能使用该容量。

启动命令为 `/sbin/init`，探针为 `5000/platform`。可选的 `make smoke` 另行检查真实
1920×1080 桌面；server 返回 200 不等同于桌面就绪，冷启动时 noVNC 桌面可能
稍后才出现。也不要求任务启动前
Chrome/CDP 常驻。对外端口为 `5000/5910/8080/9222`。

## 安装 Claude Code 的派生镜像

将 `.env` 中 `CUSTOM_IMAGE` 填成自己仓库的不可变版本地址，并执行
`docker login <你的仓库>`。私有 TCR 拉取需要时填写授权角色 `ROLE_ARN`。

```bash
make build
make push
make custom
```

Dockerfile 继承 base 的 systemd/桌面服务，仅添加固定的 Claude Code 2.1.153
原生二进制，从官方 npm 包下载并校验 SHA256，无需 Node.js。
派生镜像与直接启动 base 分别保存本地状态。
OCI layer 可以复用，但新镜像的加速制品和自动快照可能仍需重新准备。

在本地 `.env` 设置 `ANTHROPIC_API_KEY`，可选 `ANTHROPIC_BASE_URL`，随后：

```bash
make claude
```

凭证在实例启动后通过鉴权的 `5000/setup/upload` 写入用户私有临时目录，
文件权限为 0600；随后在桌面终端启动 Claude Code。不会自动发送模型请求。
凭证不进入 OCI 或预制快照；注入后另行保存运行时快照可能保留凭证。

## noVNC 与鉴权

默认 TOKEN 鉴权，脚本通过 `AcquireSandboxInstanceToken` 获取 token，
同时在网页 URL 与 WebSocket path 中携带，并正确做 URL 编码。输出链接本身
就是访问凭证，不要公开分享；token 或实例失效后链接失效。再次执行
`make quickstart` 可为仍在运行的实例获取新链接。

自己拼接链接时，网页使用 `access_token`，WebSocket 使用嵌入 `path` 的
`token`，需要两层编码。下面使用占位符演示，真实 token 从上述 AGS API 获取：

```python
from urllib.parse import urlencode

host = "5910-INSTANCE_ID.ap-guangzhou.tencentags.com"
token = "INSTANCE_TOKEN"
path = "websockify?" + urlencode({"token": token})
url = "https://" + host + "/vnc.html?" + urlencode({
    "autoconnect": "true", "resize": "scale",
    "access_token": token, "path": path,
})
```

临时受控测试可在创建新实例前设 `AUTH_MODE=none`，此时桌面和命令 API 不再
受 AGS token 保护。改 `.env` 不会改变现有实例鉴权模式。

## Benchmark、状态与清理

按[现有 OSWorld AGS cookbook](../osworld-ags/README_zh.md) 固定上游 checkout、
安装依赖。将 `AGS_TEMPLATE` 指向新 Tool ID、`E2B_DOMAIN` 指向对应地域，
由现有 Benchmark agent 执行任务。OSWorld1 使用 `AGS_SUDO_PASSWORD=password`。
`OSWORLD_MOCK_LLM_DONE=1` 只验证初始化，不算真实 agent 完成任务。

```bash
make snapshot  # 查看快照状态，不等待制作
make smoke     # 独立验证实例，验证后自动停止；保留 Tool
make clean     # 停止交互实例，删除本示例创建的 Tool
make check     # 可选的脚本检查
```

`.state/` 保存资源归属、截图和报告，不保存 token 或模型凭证。平台不强制执行
本示例检查。创建失败时保留归属信息便于重试和清理。本示例直接创建 Tool，
不依赖独立镜像预热接口；平台仍会执行创建 Tool 所需的镜像准备。
使用 `tag@sha256` 时，脚本在启动实例前核对 Tool 保存的 manifest digest。
