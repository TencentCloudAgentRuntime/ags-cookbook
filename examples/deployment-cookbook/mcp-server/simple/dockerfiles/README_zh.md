# Everything MCP Server 镜像

本目录可复现地构建 MCP Deployment 示例使用的镜像：

```text
ccr.ccs.tencentyun.com/ags.dev/mcp-everything:2026.8.31-ags.1
```

已发布的 OCI index digest：

```text
sha256:3e708366c19c13516b508ac8c58580b060df7cfba4197005070cc433b98c07d3
```

镜像固定以下内容：

- 官方 package `@modelcontextprotocol/server-everything@2026.8.31`；
- Node OCI index `node:22.23.2-alpine@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32`；
- `package-lock.json` 中的完整 npm 依赖图；
- OCI metadata 中的上游 revision `a40bc270fb5ece62673f8a1196f57116d885c5eb`。

Package 使用原生 `streamableHttp` transport，在端口 `3001` 的 `/mcp` 提供服务。`entrypoint.mjs` 只负责运维胶水：启动未修改的上游入口、等待 TCP listener、在端口 `3000` 提供 `GET /healthz`，并转发终止信号。它不解析 MCP，也不添加 tool。

固定版本上游仓库描述了 Apache-2.0/MIT 许可证迁移，server README 标识 MIT，而 npm tarball 没有携带 license 文件。因此，本目录将固定 revision 的仓库根许可证保存为 `LICENSE-modelcontextprotocol-servers`，并在镜像 metadata 中记录 `Apache-2.0 AND MIT`。升级前必须重新核对上游许可证状态。

## 本地构建和协议验证

从本目录执行：

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

Health 响应为 `ok`。客户端必须报告协议 `2025-11-25`、两个必需 tool 和成功的 `echo` 调用。

## 构建并发布多平台 manifest

先登录 CCR：

```bash
podman login ccr.ccs.tencentyun.com
```

把两个支持的平台构建为同一个 manifest list 并推送：

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

确认远端 index 同时包含 `linux/amd64` 和 `linux/arm64`。绝不能发布 `latest`。

已发布 tag 应保持不可变。使用或重新发布前，请把远端原始 index 与记录的 digest 对比：

```bash
skopeo inspect --raw "docker://$MCP_IMAGE" | shasum -a 256
```

升级时必须同步更新 package 版本、lockfile、基础镜像 digest、OCI labels、镜像 tag、README 和 Tool 镜像引用。然后重新执行本地原生客户端检查、检查两个远端 manifest，并完成上海 Deployment 全链路验收。
