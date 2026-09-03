# 构建 DeepSeek Harness all-in-one 镜像（可选）

部署教程使用下列已发布镜像，因此可以跳过本页：

```text
ccr.ccs.tencentyun.com/ags.dev/deepseek-harness:v0.1.1-rc.2-ags.4
```

## 本地构建

安装 Podman，然后从本目录执行：

```bash
podman build \
  --platform linux/amd64 \
  --tag deepseek-harness:all-in-one-local \
  .
```

## 推送自有副本

准备自己的 CCR 或 TCR namespace，再给验证过的本地镜像添加 tag 并推送：

```bash
export DSH_REGISTRY='<your-registry-host>'
export DSH_IMAGE="${DSH_REGISTRY}/<your-namespace>/deepseek-harness:v0.1.1-rc.2-ags.4"

podman login "$DSH_REGISTRY"
podman tag deepseek-harness:all-in-one-local "$DSH_IMAGE"
podman push "$DSH_IMAGE"
```

把部署教程中的 `Image` 替换为该镜像引用。CCR 继续使用 `ImageRegistryType: personal`；TCR 企业版使用 `enterprise`。Agent Runtime CAM 角色必须有权拉取自己的仓库。
