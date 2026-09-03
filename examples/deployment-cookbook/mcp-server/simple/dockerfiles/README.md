# Build the Everything MCP Server image (optional)

The [deployment tutorial](../README.md) uses this published image, so you can skip this page:

```text
ccr.ccs.tencentyun.com/ags.dev/mcp-everything:2026.8.31-ags.1
```

MCP uses port `3001`, and the readiness check uses port `3000`.

## Build and verify locally

Install Podman and [`uv`](https://docs.astral.sh/uv/), then run from this directory:

```bash
export MCP_LOCAL_IMAGE='mcp-everything:local'

podman build --platform linux/amd64 --tag "$MCP_LOCAL_IMAGE" .
podman run --detach --rm --name ags-mcp-everything-local \
  --publish 3000:3000 --publish 3001:3001 "$MCP_LOCAL_IMAGE"

curl --fail-with-body --silent --show-error http://127.0.0.1:3000/healthz
uv run --project ../client --locked python ../client/mcp_client.py smoke \
  --url http://127.0.0.1:3001/mcp --transport local

podman stop ags-mcp-everything-local
```

The health response is `ok`, and the smoke command completes `initialize`, `tools/list`, and `echo`.

## Push a private copy

Tag and push the local image to your own registry:

```bash
export MCP_REGISTRY='<your-registry-host>'
export MCP_IMAGE="${MCP_REGISTRY}/<your-namespace>/mcp-everything:2026.8.31-ags.1"

podman login "$MCP_REGISTRY"
podman tag "$MCP_LOCAL_IMAGE" "$MCP_IMAGE"
podman push "$MCP_IMAGE"
```

Replace `Image` in the deployment tutorial with this tag. Keep `ImageRegistryType` as `personal` for CCR, or use `enterprise` for TCR Enterprise. The Agent Runtime CAM role must be able to pull from your repository.
