# 构建 Everything MCP Server 镜像（可选）

[部署教程](../README_zh.md)使用下列已发布镜像，因此可以跳过本页：

```text
ccr.ccs.tencentyun.com/ags.dev/mcp-everything:2026.8.31-ags.1
```

MCP 使用端口 `3001`，就绪检查使用端口 `3000`。

## 本地构建与验证

安装 Podman 和 [`uv`](https://docs.astral.sh/uv/)，然后从本目录运行：

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

Health 响应应为 `ok`，smoke 命令会完成 `initialize`、`tools/list` 和 `echo`。

## 推送自有副本

给本地镜像添加 tag，再推送到自己的镜像仓库：

```bash
export MCP_REGISTRY='<your-registry-host>'
export MCP_IMAGE="${MCP_REGISTRY}/<your-namespace>/mcp-everything:2026.8.31-ags.1"

podman login "$MCP_REGISTRY"
podman tag "$MCP_LOCAL_IMAGE" "$MCP_IMAGE"
podman push "$MCP_IMAGE"
```

把部署教程中的 `Image` 替换为这个 tag。CCR 使用 `personal`；TCR 企业版使用 `enterprise`。Agent Runtime CAM 角色必须有权从自己的仓库拉取镜像。
