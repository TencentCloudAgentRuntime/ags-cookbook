# 在 AGS 上自定义 OSWorld 镜像

这个示例带你先打开一个 OSWorld 桌面，再安装 Claude Code，构建并运行自己的镜像。
如果只想体验桌面，完成第一步即可，不需要安装 Docker。

更多镜像定制说明见[基础镜像使用指南](docs/image-guide.zh-CN.md)。

## 准备

- Python 3.11+ 和 uv。
- 具有 AGS 权限的腾讯云凭证。
- OSWorld 基础镜像地址（待补充）。`OSWORLD_BASE_IMAGE` 暂留空。
- 如果要构建自己的镜像，还需要 Docker 和自己的 CCR/TCR 仓库。

## 第一步：打开桌面

```bash
cd examples/osworld-custom-image
make setup
# 编辑 .env，填写腾讯云凭证、AGS_REGION 和 OSWORLD_BASE_IMAGE
make quickstart
```

`make run` 与 `make quickstart` 等价。启动成功后，终端会输出沙箱工具 ID、
实例 ID 和 noVNC 链接。用浏览器打开链接即可操作桌面。

示例已开启自动快照。有可用快照时会直接复用；首次使用新镜像可能需要更长时间，
快照尚未就绪也可以冷启动。桌面可能在链接输出后稍晚出现。

默认配置为 8 核 CPU、16 GiB 内存、20 GiB 可写磁盘，`/dev/shm` 至少 4 GiB。
实例最多保留一小时，不再使用时运行 `make clean`。

## 第二步：构建包含 Claude Code 的镜像

在 `.env` 中将 `CUSTOM_IMAGE` 填为自己仓库中的新镜像地址，例如使用 `:v1`
作为版本号。先用 `docker login` 登录仓库，再执行：

```bash
make build
make push
make custom
```

[Dockerfile.claude-code](Dockerfile.claude-code) 会在基础镜像上安装
Claude Code 2.1.153，并保留原有桌面。你也可以修改 Dockerfile，安装其他软件。
每次发布新内容请使用新的版本号，不要覆盖已有版本。

启动后，在本地 `.env` 中设置 `ANTHROPIC_API_KEY`；使用自定义服务地址时，
再填写 `ANTHROPIC_BASE_URL`。然后运行：

```bash
make claude
```

脚本会把凭证传入已启动的沙箱，并在桌面终端打开 Claude Code。
你可以在终端中输入任务。凭证不会写进容器镜像，请不要把配置过凭证的运行环境
再保存为供他人使用的快照。

使用私有 TCR 时，可能需要在 `ROLE_ARN` 中填写允许 AGS 拉取镜像的授权角色。

## noVNC 与鉴权

默认使用 token 鉴权，脚本输出的 noVNC 链接已经带好 token。
链接本身就是访问凭证，请勿公开分享。需要新链接时，再运行一次 `make quickstart`；
查看定制镜像的桌面则运行 `make custom`。

如果要自己生成链接，先通过 `AcquireSandboxInstanceToken` 获取实例 token，
再用下面的方式拼接。网页和 WebSocket 都需要带上 token：

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

临时测试也可以在创建实例前设置 `AUTH_MODE=none`，关闭 token 鉴权。
此时任何拿到地址的人都能访问桌面和命令接口，请谨慎使用。
修改这个配置不会改变已经运行的实例。

## 运行 Benchmark

按[OSWorld AGS 示例](../osworld-ags/README_zh.md)安装 Benchmark，
将 `AGS_TEMPLATE` 设置为本示例输出的 Tool ID，`E2B_DOMAIN` 设置为对应地域。
使用 OSWorld1 时设置 `AGS_SUDO_PASSWORD=password`。
Benchmark 使用自己的 agent，与本例中安装的 Claude Code 无关。

## 检查状态与清理

```bash
make snapshot  # 查看快照状态
make smoke     # 可选：另开实例检查桌面截图和 noVNC，检查后自动停止
make clean     # 停止实例，删除本示例创建的沙箱工具
```

日常使用不需要运行 `make smoke`。本地 `.state/` 保存工具和实例信息，
以及检查时生成的截图和报告。创建失败时保留这个目录，便于重试或清理。
