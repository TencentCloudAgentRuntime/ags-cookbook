# Build the DeepSeek Harness all-in-one image (optional)

The deployment tutorial uses this published image, so you can skip this page:

```text
ccr.ccs.tencentyun.com/ags.dev/deepseek-harness:v0.1.1-rc.2-ags.4
```

## Build locally

Install Podman, then run from this directory:

```bash
podman build \
  --platform linux/amd64 \
  --tag deepseek-harness:all-in-one-local \
  .
```

## Push a private copy

Prepare your own CCR or TCR namespace, then tag and push the verified local image:

```bash
export DSH_REGISTRY='<your-registry-host>'
export DSH_IMAGE="${DSH_REGISTRY}/<your-namespace>/deepseek-harness:v0.1.1-rc.2-ags.4"

podman login "$DSH_REGISTRY"
podman tag deepseek-harness:all-in-one-local "$DSH_IMAGE"
podman push "$DSH_IMAGE"
```

Replace `Image` in the deployment tutorial with this image reference. Keep `ImageRegistryType` as `personal` for CCR, or use `enterprise` for TCR Enterprise. The Agent Runtime CAM role must be able to pull from your repository.
