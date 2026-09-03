# 在自己的镜像仓库中构建 go-httpbin（可选）

部署教程使用下列已发布镜像，因此可以跳过本页：

```text
ccr.ccs.tencentyun.com/ags.dev/go-httpbin:v2.25.0
```

Dockerfile 直接使用上游镜像 `ghcr.io/mccutchen/go-httpbin:2.25.0`。

## 构建并推送自有副本

安装带 Buildx 的 Docker，准备自己有权推送的 registry namespace，然后从本目录执行：

```bash
export HTTPBIN_REGISTRY='<your-registry-host>'
export HTTPBIN_IMAGE="${HTTPBIN_REGISTRY}/<your-namespace>/go-httpbin:v2.25.0"

docker login "$HTTPBIN_REGISTRY"
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --tag "$HTTPBIN_IMAGE" \
  --push \
  .

docker buildx imagetools inspect "$HTTPBIN_IMAGE"
```

把教程 Tool 定义中的 `Image` 替换为输出的镜像引用。CCR 继续使用 `ImageRegistryType: personal`；TCR 企业版使用 `enterprise`。Agent Runtime CAM 角色必须有权拉取自己的仓库。
