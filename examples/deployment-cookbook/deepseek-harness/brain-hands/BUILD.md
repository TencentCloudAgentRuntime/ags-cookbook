# Build the Brain and Hands images (optional)

English | [中文](./BUILD_zh.md)

The [deployment tutorial](./README.md) uses these published `linux/amd64` images, so you can skip this page:

```text
ccr.ccs.tencentyun.com/ags.dev/deepseek-harness:brain-v0.1.0-rc.8-ags.1
ccr.ccs.tencentyun.com/ags.dev/deepseek-harness:hands-envd-v0.6.13-ags.1
```

Build a copy only when you change the source or need to publish to your own registry.

## Build and verify locally

Install Node.js 22.19 or later, pnpm 11.19, and Podman. Then run from the `brain-hands` directory:

```bash
make install
make typecheck
make test
make build
```

## Push a private copy

Prepare your own CCR namespace, then tag and push the local images:

```bash
export CCR_REGISTRY='ccr.ccs.tencentyun.com/replace-me'
export BRAIN_IMAGE="$CCR_REGISTRY/deepseek-harness:brain-v0.1.0-rc.8-ags.1"
export HANDS_IMAGE="$CCR_REGISTRY/deepseek-harness:hands-envd-v0.6.13-ags.1"

podman login ccr.ccs.tencentyun.com
podman tag ags-cookbook/dsh-brain:local "$BRAIN_IMAGE"
podman tag ags-cookbook/dsh-hands:local "$HANDS_IMAGE"
podman push "$BRAIN_IMAGE"
podman push "$HANDS_IMAGE"
```

Replace the two `Image` values in the deployment tutorial with these tags. Keep `ImageRegistryType` as `personal` for CCR; use the registry type required by your target registry if you publish elsewhere.
