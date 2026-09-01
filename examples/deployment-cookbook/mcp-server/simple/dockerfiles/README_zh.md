# 将 Everything MCP Server 镜像构建到自己的镜像仓库（可选）

部署教程直接使用下面已发布的示例镜像，因此可以跳过本页。如果账号策略要求使用自有镜像仓库，可以按下面的步骤构建并推送同一个服务。

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

上游 package 使用原生 `streamableHttp` 传输，在端口 `3001` 的 `/mcp` 提供服务。本镜像只增加 `entrypoint.mjs`：它启动上游服务、等待 TCP 监听端口、在端口 `3000` 提供 `GET /healthz`，并转发终止信号。它不处理 MCP 消息，也不注册额外工具。

镜像中还包含上游许可证文本 `LICENSE-modelcontextprotocol-servers`。

## 前置条件

- 已安装 Podman、`skopeo` 和 [`uv`](https://docs.astral.sh/uv/)。
- 已准备可推送的 CCR 或 TCR 镜像仓库，且 AGR 使用的 CAM 角色有权从该仓库拉取镜像。
- 执行命令前，将 `<your-registry-host>` 替换为完整的镜像仓库域名，将 `<your-namespace>` 替换为自己的命名空间。CCR 的域名为 `ccr.ccs.tencentyun.com`；TCR 企业版请使用 TCR 控制台显示的实例访问域名。
- 本地验证期间，请确保端口 `3000` 和 `3001` 未被占用。
- 使用能够为 `linux/amd64` 和 `linux/arm64` 执行 `RUN` 指令的 Podman 构建环境。非本机架构需要 QEMU 等模拟能力，具体说明见 [Podman 官方构建文档](https://docs.podman.io/en/stable/markdown/podman-build.1.html)。

## 本地构建和测试

从本目录执行：

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

Health 响应为 `ok`。客户端应报告协议 `2025-11-25`，找到 `echo` 和 `trigger-long-running-operation`，并成功完成 `echo` 调用。

如果验证失败且容器仍然存在，请先查看状态和日志，再删除容器后重试：

```bash
podman ps --all --filter name=ags-mcp-everything-local
podman logs ags-mcp-everything-local
podman rm --force --ignore ags-mcp-everything-local
```

成功流程已经停止容器。容器使用 `--rm` 启动，停止后会由 Podman 删除；上面的最后一条命令也允许容器已经不存在。

## 推送镜像到自己的仓库

设置镜像仓库域名并登录：

```bash
export MCP_REGISTRY='<your-registry-host>'
export MCP_IMAGE="${MCP_REGISTRY}/<your-namespace>/mcp-everything:2026.8.31-ags.1"

podman login "$MCP_REGISTRY"
```

构建两个平台前，先确认 Podman 环境能执行每个目标架构的固定 Node 镜像：

```bash
export MCP_NODE_IMAGE='docker.io/library/node:22.23.2-alpine@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32'

podman run --rm --platform linux/amd64 "$MCP_NODE_IMAGE" node --print process.arch
podman run --rm --platform linux/arm64 "$MCP_NODE_IMAGE" node --print process.arch
```

两条命令应分别输出 `x64` 和 `arm64`。如果任一命令因执行格式错误而失败，请按上述 Podman 文档为 Podman 主机配置 QEMU/binfmt，或在对应架构的原生主机上构建，再通过 [Podman build farm](https://docs.podman.io/en/stable/markdown/podman-farm-build.1.html)合并。两项检查均成功后再开始多平台构建。

把两个平台构建为同一个 manifest list，并推送到自己的仓库：

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

确认远端 index 同时包含 `linux/amd64` 和 `linux/arm64`。请使用带版本的 tag，不要使用 `latest`。

记录 digest，便于之后核对实际部署的镜像：

```bash
skopeo inspect --raw "docker://$MCP_IMAGE" | shasum -a 256
```

输出完整镜像地址：

```bash
printf '%s\n' "$MCP_IMAGE"
```

返回[部署教程](../README_zh.md)，在第 2 步将该地址粘贴到 `Image`，不要粘贴字面量 `$MCP_IMAGE`。CCR 使用 `personal`；TCR 企业版请将 `ImageRegistryType` 改为 `enterprise`。同时使用有权从该仓库拉取镜像的 CAM 角色。

## 构建制品和可选清理

推送后，带版本的镜像会保留在自己的 CCR 或 TCR 仓库中，以供 AGR 拉取。只要还有 Sandbox Tool 使用该镜像，就应保留远端镜像。当没有 Tool 引用且不再需要该镜像时，请按官方 [CCR 镜像仓库说明](https://cloud.tencent.com/document/faq/457/6785)或 [TCR 镜像仓库管理指南](https://cloud.tencent.com/document/product/1141/41811)删除对应镜像版本。

构建还会在本地 Podman 存储中保留单平台测试镜像和多平台 manifest list。不再需要重新构建或检查时，可以删除这些本地制品：

```bash
podman image rm --ignore "${MCP_IMAGE}-local"
podman manifest rm --ignore "$MCP_IMAGE"
```
