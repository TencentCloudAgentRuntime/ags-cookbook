# Everything MCP Server image

This directory reproducibly builds the image used by the MCP Deployment example:

```text
ccr.ccs.tencentyun.com/ags.dev/mcp-everything:2026.8.31-ags.1
```

Published OCI index digest:

```text
sha256:3e708366c19c13516b508ac8c58580b060df7cfba4197005070cc433b98c07d3
```

The image pins:

- official package `@modelcontextprotocol/server-everything@2026.8.31`;
- Node OCI index `node:22.23.2-alpine@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32`;
- the complete npm graph in `package-lock.json`;
- upstream revision `a40bc270fb5ece62673f8a1196f57116d885c5eb` in OCI metadata.

The package runs its native `streamableHttp` transport on `/mcp` at port `3001`. `entrypoint.mjs` is operational glue only: it starts the unmodified upstream entry point, waits for its TCP listener, serves `GET /healthz` on port `3000`, and forwards termination signals. It does not parse MCP or add tools.

The pinned upstream repository describes an Apache-2.0/MIT transition, while the server README identifies MIT and the npm tarball omits a license file. This directory therefore carries the pinned repository root license as `LICENSE-modelcontextprotocol-servers` and records `Apache-2.0 AND MIT` in image metadata. Recheck upstream licensing before upgrading.

## Local build and protocol validation

From this directory:

```bash
export MCP_IMAGE='ccr.ccs.tencentyun.com/ags.dev/mcp-everything:2026.8.31-ags.1'

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

The health response is `ok`. The client must report protocol `2025-11-25`, both required tools, and a successful `echo` call.

## Build and publish the multi-platform manifest

Log in to CCR first:

```bash
podman login ccr.ccs.tencentyun.com
```

Build both supported platforms into one manifest list and push it:

```bash
export MCP_IMAGE='ccr.ccs.tencentyun.com/ags.dev/mcp-everything:2026.8.31-ags.1'

podman build \
  --platform linux/amd64,linux/arm64 \
  --manifest "$MCP_IMAGE" \
  .

podman manifest push --all \
  "$MCP_IMAGE" \
  "docker://$MCP_IMAGE"

skopeo inspect --raw "docker://$MCP_IMAGE"
```

Verify that the remote index contains both `linux/amd64` and `linux/arm64`. Never publish `latest`.

The published tag is intended to be immutable. Compare the raw remote index with the recorded digest before using or republishing it:

```bash
skopeo inspect --raw "docker://$MCP_IMAGE" | shasum -a 256
```

When upgrading, update the package version, lockfile, base-image digest, OCI labels, image tag, READMEs, and Tool image reference together. Repeat the local native-client check, inspect both remote manifests, and rerun the full Shanghai Deployment acceptance flow.
