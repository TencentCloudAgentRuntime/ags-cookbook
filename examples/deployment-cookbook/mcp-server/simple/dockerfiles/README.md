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

- Install Podman, `skopeo`, and [`uv`](https://docs.astral.sh/uv/).
- Prepare a CCR or TCR repository that you can push to and that the AGR CAM role can pull from.
- Replace `<your-registry-host>` with the complete registry hostname and `<your-namespace>` with your namespace. For CCR, the host is `ccr.ccs.tencentyun.com`; for TCR Enterprise, use the instance access domain shown in the TCR console.
- Keep local ports `3000` and `3001` free while running the local validation.
- Use a Podman build environment that can execute `RUN` instructions for both `linux/amd64` and `linux/arm64`. A non-native architecture requires emulation such as QEMU; see the official [Podman build documentation](https://docs.podman.io/en/stable/markdown/podman-build.1.html).

## Build and test locally

From this directory:

```bash
export MCP_REGISTRY='<your-registry-host>'
export MCP_IMAGE="${MCP_REGISTRY}/<your-namespace>/mcp-everything:2026.8.31-ags.1"

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

The health response is `ok`. The client should report protocol `2025-11-25`, find both `echo` and `trigger-long-running-operation`, and complete the `echo` call successfully.

If validation fails while the container is still present, inspect its state and logs, then remove it before retrying:

```bash
podman ps --all --filter name=ags-mcp-everything-local
podman logs ags-mcp-everything-local
podman rm --force --ignore ags-mcp-everything-local
```

The successful path already stops the container. Because it was started with `--rm`, Podman removes it after stopping; the final command above also handles a missing container.

## Push the image to your registry

Set the registry host and log in:

```bash
export MCP_REGISTRY='<your-registry-host>'
export MCP_IMAGE="${MCP_REGISTRY}/<your-namespace>/mcp-everything:2026.8.31-ags.1"

podman login "$MCP_REGISTRY"
```

Before building both platforms, verify that the Podman environment can execute the pinned Node image for each target architecture:

```bash
export MCP_NODE_IMAGE='docker.io/library/node:22.23.2-alpine@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32'

podman run --rm --platform linux/amd64 "$MCP_NODE_IMAGE" node --print process.arch
podman run --rm --platform linux/arm64 "$MCP_NODE_IMAGE" node --print process.arch
```

The commands should print `x64` and `arm64`, respectively. If either command fails with an execution-format error, configure QEMU/binfmt for the Podman host as described in the linked Podman documentation, or perform the builds on native hosts and combine them with a [Podman build farm](https://docs.podman.io/en/stable/markdown/podman-farm-build.1.html). Do not start the multi-platform build until both checks succeed.

Build both platforms into one manifest list and push it to your repository:

```bash
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

Print the full image URI:

```bash
printf '%s\n' "$MCP_IMAGE"
```

Return to the [deployment tutorial](../README.md) and paste that URI into `Image` in step 2; do not paste the literal text `$MCP_IMAGE`. Keep `ImageRegistryType` as `personal` for CCR, or change it to `enterprise` for TCR. Use a CAM role that can pull from your repository.

## Artifacts and optional cleanup

The push leaves the versioned image in your CCR or TCR repository so AGR can pull it. Keep that remote image while a Sandbox Tool uses it. When no Tool refers to it and you no longer need it, delete that image version by following the official [CCR image repository guidance](https://cloud.tencent.com/document/faq/457/6785) or [TCR repository management guide](https://cloud.tencent.com/document/product/1141/41811).

The build also leaves the single-platform test image and multi-platform manifest list in local Podman storage. Remove those local artifacts when you no longer need to rebuild or inspect them:

```bash
podman image rm --ignore "${MCP_IMAGE}-local"
podman manifest rm --ignore "$MCP_IMAGE"
```
