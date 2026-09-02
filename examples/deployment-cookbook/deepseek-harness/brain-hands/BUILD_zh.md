# 构建 Brain 与 Hands 镜像（可选）

[English](./BUILD.md) | 中文

[部署教程](./README_zh.md)直接使用下列已发布的 `linux/amd64` 镜像，因此可以跳过本页：

```text
ccr.ccs.tencentyun.com/ags.dev/deepseek-harness:brain-v0.1.0-rc.8-ags.6
ccr.ccs.tencentyun.com/ags.dev/deepseek-harness:hands-envd-v0.6.13-ags.1
```

只有修改源码或需要发布到自己的镜像仓库时，才需要自行构建。

## 本地构建与验证

安装 Node.js 22.19 或更高版本、pnpm 11.19 和 Podman，然后在 `brain-hands` 目录运行：

```bash
make install
make typecheck
make test
make build
```

## 推送自有副本

准备自己的 CCR namespace，再给本地镜像添加 tag 并推送：

```bash
export CCR_REGISTRY='ccr.ccs.tencentyun.com/replace-me'
export BRAIN_IMAGE="$CCR_REGISTRY/deepseek-harness:brain-v0.1.0-rc.8-ags.6"
export HANDS_IMAGE="$CCR_REGISTRY/deepseek-harness:hands-envd-v0.6.13-ags.1"

podman login ccr.ccs.tencentyun.com
podman tag ags-cookbook/dsh-brain:local "$BRAIN_IMAGE"
podman tag ags-cookbook/dsh-hands:local "$HANDS_IMAGE"
podman push "$BRAIN_IMAGE"
podman push "$HANDS_IMAGE"
```

把部署教程中的两个 `Image` 值替换为这些 tag。CCR 继续使用 `ImageRegistryType: personal`；发布到其它 registry 时，使用目标 registry 要求的类型。
