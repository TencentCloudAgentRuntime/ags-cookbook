# 使用 OSWorld 基础镜像

你可以直接用基础镜像启动一个 OSWorld 桌面，也可以在上面安装自己的软件，
构建新镜像后交给 AGS 运行。首次体验和 Claude Code 定制示例见 [README](../README_zh.md)。

## 选择镜像

| 镜像 | 用途 |
| --- | --- |
| OSWorld1 | 运行 OSWorld 桌面任务和现有 Benchmark 示例 |
| OSWorld2 | 运行 OSWorld2 任务，包括需要 Docker 的任务 |

本示例已配置 OSWorld1。两套基础镜像均可公开拉取，无需登录镜像仓库。

OSWorld1：

```text
ccr.ccs.tencentyun.com/ags-image/osworld1-base:upstream-091f5ef1-server-0919a09-ags.1@sha256:120782c9f4b928654a950b3d8bb334f20c0ef7422d27a1a84e7b0ff8079c956a
```

OSWorld2：

```text
ccr.ccs.tencentyun.com/ags-image/osworld2-base:2026.06.24-ags.1-oci.3@sha256:81965719d54852fc367a0ebc9bc37ccfb45bc61c0cf17a4e19cca1cc83d5f9c8
```

要体验 OSWorld2，将 `.env` 中的 `OSWORLD_BASE_IMAGE` 替换为上面的对应地址即可。

请固定基础镜像的版本，避免使用 `latest`。更新自己的镜像时也使用新 tag，
例如从 `v1` 更新为 `v2`，这样方便复现结果和回退。

## 安装自己的软件

定制方式与普通 Docker 镜像相同。例如，下面的 Dockerfile 安装了 `jq`：

```dockerfile
ARG OSWORLD_BASE_IMAGE
FROM ${OSWORLD_BASE_IMAGE}

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends jq \
    && rm -rf /var/lib/apt/lists/*
```

构建时传入基础镜像地址，再推送到自己的 CCR 或 TCR 仓库：

```bash
docker build --build-arg OSWORLD_BASE_IMAGE="基础镜像地址" -t "你的镜像地址:v1" .
docker push "你的镜像地址:v1"
```

将 `.env` 中的 `CUSTOM_IMAGE` 改为新镜像地址，然后运行 `make custom`。

安装软件、复制文件或添加后台服务都可以。为了让桌面和评测任务正常工作，
请保留 `/sbin/init` 启动命令、`user` 桌面用户，以及 OSWorld API、桌面和 VNC 服务。
云凭证和模型 API Key 不要写进 Dockerfile，应在沙箱启动后再配置。

安装过程中产生的下载缓存，尽量在同一条 `RUN` 中清理。这样可以减少新镜像的体积。

## 启动和快照

运行 `make quickstart` 或 `make custom` 后，脚本会创建沙箱工具并启动实例，
最后输出 noVNC 链接。用浏览器打开链接，就能操作桌面。

示例会在工具名称中加入 `auto-snapshot`，自动制作快照。已有相同镜像和配置的
快照时可以直接复用；快照还没准备好时，实例也可以冷启动，不必手动等待。
首次使用新镜像通常比后续启动慢。更换镜像或运行配置后，可能需要重新制作快照。

```bash
make snapshot  # 查看快照状态
make smoke     # 可选：检查桌面截图和 noVNC 是否正常
```

本示例使用 8 核 CPU、16 GiB 内存和 20 GiB 可写磁盘。`/dev/shm` 至少为 4 GiB，
避免 Chrome 因共享内存不足而崩溃。可以在沙箱内运行 `df -h /dev/shm` 检查。

## 可用接口

| 端口 | 用途 |
| --- | --- |
| 5000 | OSWorld API，用于截图、执行命令、上传和下载文件 |
| 5910 | noVNC，用浏览器访问桌面 |
| 8080 | VLC HTTP 接口，由任务按需启用 |
| 9222 | Chrome 调试接口，由任务按需启用 |

noVNC 链接默认带有访问 token，拿到链接的人可以访问对应桌面，请勿公开分享。
如何手动拼接链接，以及如何选择 `AUTH_MODE=none`，见 [noVNC 与鉴权](../README_zh.md#novnc-与鉴权)。

## 在 OSWorld2 中使用 Docker

OSWorld2 基础镜像已经配置好 Docker 所需的数据目录。需要 Docker 的任务，
可以在沙箱启动后安装 Docker，无需自己挂载磁盘。

Docker 镜像、构建缓存和 volume 会占用沙箱的可写磁盘。本示例提供 20 GiB，
运行较大的构建任务前，请先检查剩余空间：

```bash
df -h /var/lib/docker /var/lib/containerd
```

基础镜像不预装 Docker，请按任务要求安装并启动。

## 配置凭证与结束使用

以 Claude Code 为例，在本地 `.env` 填写 `ANTHROPIC_API_KEY`，再运行 `make claude`。
脚本会通过 OSWorld API 将凭证传入已经启动的沙箱，并在桌面终端打开 Claude Code。
凭证不会写进基础镜像。配置了凭证的运行环境，不要再保存为供他人使用的快照。

体验结束后运行 `make clean`，停止实例并删除本示例创建的沙箱工具。
