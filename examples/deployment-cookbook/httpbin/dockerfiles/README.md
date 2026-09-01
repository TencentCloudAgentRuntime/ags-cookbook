# go-httpbin Image

The Deployment examples use this pinned public image:

```text
ccr.ccs.tencentyun.com/ags.dev/go-httpbin:v2.25.0
```

The Dockerfile uses the upstream image `ghcr.io/mccutchen/go-httpbin:2.25.0`, which corresponds to go-httpbin release `v2.25.0`. It does not override the entrypoint, preserving the upstream non-root runtime, default port `8080`, and httpbin behavior. The CCR image consistently uses the version tag `v2.25.0`.

## Build and publish

Log in to CCR first:

```bash
docker login ccr.ccs.tencentyun.com
```

Run a multi-platform build from this directory and push it directly:

```bash
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --tag ccr.ccs.tencentyun.com/ags.dev/go-httpbin:v2.25.0 \
  --push \
  .
```

Verify the remote manifest:

```bash
docker buildx imagetools inspect \
  ccr.ccs.tencentyun.com/ags.dev/go-httpbin:v2.25.0
```

When upgrading the image, update the upstream version in the Dockerfile, the CCR tag, and every Markdown tutorial image reference together, then rerun all four examples.
