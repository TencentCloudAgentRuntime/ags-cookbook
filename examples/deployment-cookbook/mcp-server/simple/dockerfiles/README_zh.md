# 将 Everything MCP Server 镜像构建到自己的镜像仓库（可选）

部署教程直接使用下面已发布的示例镜像，因此可以跳过本页。如果账号策略要求使用自有镜像仓库，可以按下面的步骤构建并推送同一个 Server。

```text
ccr.ccs.tencentyun.com/ags.dev/mcp-everything:2026.8.31-ags.1
```

已发布的 OCI index digest：

```text
sha256:3e708366c19c13516b508ac8c58580b060df7cfba4197005070cc433b98c07d3
```

为减少构建输入漂移，构建时固定以下输入：

- 官方 package `@modelcontextprotocol/server-everything@2026.8.31`；
- Node OCI index `node:22.23.2-alpine@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32`；
- `package-lock.json` 中的完整 npm 依赖图。

上游 package 使用原生 `streamableHttp` transport，在端口 `3001` 的 `/mcp` 提供服务。本镜像只增加 `entrypoint.mjs`：它启动上游 Server、等待 TCP listener、在端口 `3000` 提供 `GET /healthz`，并转发终止信号。它不处理 MCP 消息，也不注册额外 tool。

镜像中还包含上游许可证文本 `LICENSE-modelcontextprotocol-servers`。

## 前置条件

- 已安装 Podman 和 `skopeo`。
- 已准备可推送的 CCR/TCR 镜像仓库，且 AGR 使用的 CAM 角色有权从该仓库拉取镜像。
- 执行命令前，将 `<your-namespace>` 替换为自己的镜像仓库 namespace。

## 本地构建和测试

从本目录执行：

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

Health 响应为 `ok`。客户端应报告协议 `2025-11-25`、两个必需 tool 和成功的 `echo` 调用。

## 推送镜像到自己的仓库

先登录 CCR：

```bash
podman login ccr.ccs.tencentyun.com
```

把两个平台构建为同一个 manifest list，并推送到自己的仓库：

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

确认远端 index 同时包含 `linux/amd64` 和 `linux/arm64`。请使用带版本的 tag，不要使用 `latest`。

记录 digest，便于之后核对实际部署的镜像：

```bash
skopeo inspect --raw "docker://$MCP_IMAGE" | shasum -a 256
```

返回[部署教程](../README_zh.md)，在第 2 步将 `Image` 替换为 `$MCP_IMAGE`，并使用有权从该仓库拉取镜像的 CAM 角色。
