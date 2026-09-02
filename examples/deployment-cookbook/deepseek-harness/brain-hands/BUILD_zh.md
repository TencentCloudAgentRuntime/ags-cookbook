# 构建 Brain 与 Hands 镜像（可选）

[English](./BUILD.md) | 中文

[部署教程](./README_zh.md)已经提供以下 `linux/amd64` 镜像，可以直接使用：

```text
ccr.ccs.tencentyun.com/ags.dev/deepseek-harness-brain:v0.1.1-rc.2-ags.4
ccr.ccs.tencentyun.com/ags.dev/deepseek-harness-hands-ubuntu:v0.6.13
ccr.ccs.tencentyun.com/ags.dev/deepseek-harness-hands-alpine:v0.6.13
```

只有修改源码或发布到自己的镜像仓库时才需要执行本页。

## 本地验证与构建

安装 Node.js 24、pnpm 11.19 和 Podman，然后在 `brain-hands` 目录运行：

```bash
make install
make typecheck
make test
make build
```

三个镜像的本地 tag 为：

```text
ags-cookbook/dsh-brain:local
ags-cookbook/dsh-hands:ubuntu-local
ags-cookbook/dsh-hands:alpine-local
```

## 发布到自己的仓库

为三个本地镜像分别添加目标 tag，然后使用 Podman 推送：

```bash
podman login ccr.ccs.tencentyun.com
podman tag ags-cookbook/dsh-brain:local ccr.ccs.tencentyun.com/replace-me/deepseek-harness-brain:v0.1.1-rc.2-ags.4
podman tag ags-cookbook/dsh-hands:ubuntu-local ccr.ccs.tencentyun.com/replace-me/deepseek-harness-hands-ubuntu:v0.6.13
podman tag ags-cookbook/dsh-hands:alpine-local ccr.ccs.tencentyun.com/replace-me/deepseek-harness-hands-alpine:v0.6.13
```

```bash
podman push ccr.ccs.tencentyun.com/replace-me/deepseek-harness-brain:v0.1.1-rc.2-ags.4
podman push ccr.ccs.tencentyun.com/replace-me/deepseek-harness-hands-ubuntu:v0.6.13
podman push ccr.ccs.tencentyun.com/replace-me/deepseek-harness-hands-alpine:v0.6.13
```

在部署教程中把三个 `Image` 值替换为自己的 tag。
