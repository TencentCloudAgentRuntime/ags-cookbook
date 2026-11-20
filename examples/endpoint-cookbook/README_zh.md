# 通过 Agent Runtime Endpoint 调用 Registry MCP 工具

[English](README.md)

创建 Endpoint，绑定一个已有的 Agent Registry MCP 版本，再用 Endpoint Token
通过 MCP Streamable HTTP 列出并调用工具。

## 前置条件

- 包含 `agr endpoint` 的 [`agr`](https://github.com/TencentCloudAgentRuntime/ags-cli)
  预览构建。相关命令见 [CLI PR #178](https://github.com/TencentCloudAgentRuntime/ags-cli/pull/178)。
- 已开放 Endpoint 的地域和控制面 API 主机。使用环境提供的主机，并给 `agr`
  配置有权管理 Endpoint 和访问 Registry 版本的 CAM 身份。
- 已有一个与 Endpoint 兼容的 Registry MCP 版本。选用其中的只读工具验证调用。
- Bash、`jq`、Python 3.12 或更新版本，以及 [`uv`](https://docs.astral.sh/uv/)。

如需从源码构建预览版，在独立的 `ags-cli` checkout 中使用 Git 和 Go 1.25 或更新版本：

```bash
git fetch https://github.com/TencentCloudAgentRuntime/ags-cli.git refs/pull/178/head
git switch --detach FETCH_HEAD
mkdir -p build
go build -tags=preview -o build/agr ./cmd/agr
export PATH="$PWD/build:$PATH"
agr version
agr endpoint --help
```

## 1. 配置环境

以下命令都在 `examples/endpoint-cookbook` 目录和同一个 Shell 中执行。
复制 `.env.example` 为 `.env`，填入 `AGR_REGION` 和 `AGR_CLOUD_ENDPOINT`。
后者是**控制面 API 主机**。MCP 客户端使用 Endpoint 另行返回的 HTTPS URL。

```bash
cp .env.example .env
# 编辑 .env 后再继续。
set -a
. ./.env
set +a
agr status
agr endpoint --help
make setup
```

## 2. 创建 Endpoint 并绑定 Target

```bash
endpoint_name="endpoint-cookbook-$(date -u +%Y%m%d%H%M%S)-$$"
endpoint_json=$(agr endpoint create --name "$endpoint_name" -o json)
endpoint_id=$(jq -er '.Data.Endpoint.EndpointId' <<< "$endpoint_json")
ENDPOINT_MCP_URL=$(jq -er '.Data.Endpoint.MCPURL' <<< "$endpoint_json")
export ENDPOINT_MCP_URL

agr endpoint target candidates --endpoint-id "$endpoint_id" -o json |
  jq '.Data.CandidateSet[] | select(.Protocol == "MCP" and .Compatibility == "READY") |
      {RecordName, RegistryId, RecordId, VersionId}'
```

从**同一行**复制三个 ID。创建后，Target 固定使用所选版本。

```bash
registry_id='<RegistryId>'
record_id='<RecordId>'
version_id='<VersionId>'

target_json=$(agr endpoint target create \
  --endpoint-id "$endpoint_id" \
  --registry-id "$registry_id" --record-id "$record_id" --version-id "$version_id" \
  -o json)
target_id=$(jq -er '.Data.Target.TargetId' <<< "$target_json")

agr endpoint target get --endpoint-id "$endpoint_id" --target-id "$target_id" -o json |
  jq '.Data.Target | {TargetId, VersionId, Status, Availability}'
```

确认 Target 的状态是 `ENABLED`，可用性是 `READY`，再继续调用。

## 3. 签发 Token 并验证 MCP 访问

签发短期 Token，并将它保留在当前 Shell 中。签发时只返回一次明文。

```bash
set +x
token_json=$(agr endpoint token create \
  --endpoint-id "$endpoint_id" --name cookbook --expires-in 3600 -o json)
token_id=$(jq -er '.Data.TokenId' <<< "$token_json")
ENDPOINT_TOKEN=$(jq -er '.Data.Token' <<< "$token_json")
export ENDPOINT_TOKEN
unset token_json

make run
```

客户端会初始化 MCP 会话并输出一个 JSON 对象，包含工具名和输入结构。它使用
`Authorization: Bearer` 访问 Endpoint，并在退出时关闭会话。请勿把 Token 写入
`.env` 或打印到终端。

如需验证调用，从输出中复制**完整工具名**，并按工具的输入结构传入参数：

```bash
MCP_TOOL_NAME='<name-from-tools-list>' MCP_TOOL_ARGS='{}' make run
```

如果使用 DeepWiki，在 `_meta["com.tencentags/endpoint"].upstreamToolName`
中找到 `read_wiki_structure`，使用同一项的 `name` 调用，参数为
`{"repoName":"facebook/react"}`。如果工具要求参数，把 `{}` 替换成对应 JSON。
客户端输出第二个 JSON 对象作为调用结果。工具报告错误时，客户端返回非零退出码。

## 4. 清理

客户端退出后，撤销 Token，解绑 Target，再删除本示例创建的 Endpoint。每次删除前
读取当前修订号。

```bash
agr endpoint token revoke --endpoint-id "$endpoint_id" --token-id "$token_id"
unset ENDPOINT_TOKEN

target_revision=$(agr endpoint target get \
  --endpoint-id "$endpoint_id" --target-id "$target_id" -o json |
  jq -er '.Data.Target.Revision')
agr endpoint target delete --endpoint-id "$endpoint_id" --target-id "$target_id" \
  --expected-revision "$target_revision"

endpoint_revision=$(agr endpoint get --endpoint-id "$endpoint_id" -o json |
  jq -er '.Data.Endpoint.Revision')
agr endpoint delete --endpoint-id "$endpoint_id" --expected-revision "$endpoint_revision"
```

删除后，`agr endpoint get --endpoint-id "$endpoint_id"` 应返回
`ResourceNotFound`。如果中途失败，清理已经返回 ID 的资源。源 Registry Record 和版本可继续复用。

## 常见问题

- **找不到 `agr endpoint` 命令。** 检查 `agr version`、预览构建和 `PATH` 选中的可执行文件。
- **没有 READY 的 MCP 候选。** 检查 Registry 权限，使用当前身份可见的兼容 MCP 版本。
- **MCP 鉴权失败。** 确认 Token 仍有效，并且归属于返回该 MCP URL 的 Endpoint。
- **删除时修订冲突。** 重新查询资源，使用新的 `Revision` 重试。
