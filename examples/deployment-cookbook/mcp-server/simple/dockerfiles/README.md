# Build the Everything MCP Server image in your registry (optional)

The deployment tutorial uses the published example image below, so you can skip this page. If your account requires images in your own registry, follow these steps to build and push the same server there.

```text
ccr.ccs.tencentyun.com/ags.dev/mcp-everything:2026.8.31-ags.1
```

Published OCI index digest:

```text
sha256:3e708366c19c13516b508ac8c58580b060df7cfba4197005070cc433b98c07d3
```

To reduce build-input drift, the build pins:

- official package `@modelcontextprotocol/server-everything@2026.8.31`;
- Node OCI index `node:22.23.2-alpine@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32`;
- the complete npm graph in `package-lock.json`.

The upstream package serves its native `streamableHttp` transport at `/mcp` on port `3001`. This image only adds `entrypoint.mjs`, which starts the upstream server, waits for its TCP listener, serves `GET /healthz` on port `3000`, and forwards termination signals. It does not process MCP messages or register additional tools.

The image also includes the upstream license text as `LICENSE-modelcontextprotocol-servers`.

## Prerequisites

- Install Podman and `skopeo`.
- Prepare a CCR/TCR repository that you can push to and that the AGR CAM role can pull from.
- Replace `<your-namespace>` in the commands below with your registry namespace.

## Build and test locally

From this directory:

```bash
export MCP_IMAGE='ccr.ccs.tencentyun.com/<your-namespace>/mcp-everything:2026.8.31-ags.1'

podman build \
  --platform linux/amd64 \
  --tag "${MCP_IMAGE}-local" \
  .

podman run --detach --rm \
  --name ags-mcp-everything-local \
  --publish 3000:3000 \
  --publish 3001:3001 \
  "${MCP_IMAGE}-local"

curl --fail-with-body --silent --show-error http://127.0.0.1:3000/healthz

uv run --project ../client --locked python ../client/mcp_client.py smoke \
  --url http://127.0.0.1:3001/mcp \
  --transport local

podman stop ags-mcp-everything-local
```

The health response is `ok`. The client should report protocol `2025-11-25`, both required tools, and a successful `echo` call.

## Push the image to your registry

Log in to CCR first:

```bash
podman login ccr.ccs.tencentyun.com
```

Build both platforms into one manifest list and push it to your repository:

```bash
export MCP_IMAGE='ccr.ccs.tencentyun.com/<your-namespace>/mcp-everything:2026.8.31-ags.1'

podman build \
  --platform linux/amd64,linux/arm64 \
  --manifest "$MCP_IMAGE" \
  .

podman manifest push --all \
  "$MCP_IMAGE" \
  "docker://$MCP_IMAGE"

skopeo inspect --raw "docker://$MCP_IMAGE"
```

Check that the remote index contains both `linux/amd64` and `linux/arm64`. Use a versioned tag instead of `latest`.

Record the digest so you can confirm which image was deployed later:

```bash
skopeo inspect --raw "docker://$MCP_IMAGE" | shasum -a 256
```

Return to the [deployment tutorial](../README.md), replace the `Image` value in step 2 with `$MCP_IMAGE`, and use a CAM role that can pull from your repository.
