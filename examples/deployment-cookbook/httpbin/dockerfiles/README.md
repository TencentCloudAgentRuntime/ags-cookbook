# Build a go-httpbin image in your registry (optional)

The deployment tutorials use this published image, so you can skip this page:

```text
ccr.ccs.tencentyun.com/ags.dev/go-httpbin:v2.25.0
```

The Dockerfile uses the upstream `ghcr.io/mccutchen/go-httpbin:2.25.0` image.

## Build and push a private copy

Install Docker with Buildx, prepare a registry namespace you can push to, and run these commands from this directory:

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

Replace `Image` in the tutorial's Tool definition with the printed image reference. Keep `ImageRegistryType` as `personal` for CCR, or use `enterprise` for TCR Enterprise. The Agent Runtime CAM role must be able to pull from your repository.
