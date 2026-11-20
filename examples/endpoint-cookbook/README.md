# Invoke a Registry MCP tool through an Agent Runtime Endpoint

[中文](README_zh.md)

Create an Endpoint, attach an existing Agent Registry MCP version, then use an
Endpoint token to list and call its tools over MCP Streamable HTTP.

## Prerequisites

- A preview build of [`agr`](https://github.com/TencentCloudAgentRuntime/ags-cli)
  that includes `agr endpoint`. The Endpoint commands are in
  [CLI PR #178](https://github.com/TencentCloudAgentRuntime/ags-cli/pull/178).
- A region and control-plane API host where Endpoint is enabled. Use the host
  supplied for your environment. Configure `agr` with a CAM identity that can
  manage Endpoints and access the Registry version.
- An existing Registry MCP version compatible with Endpoint. Choose a read-only
  tool for the test invocation.
- Bash, `jq`, Python 3.12 or newer, and [`uv`](https://docs.astral.sh/uv/).

To build the preview from source, use Git and Go 1.25 or newer in a separate
`ags-cli` checkout:

```bash
git fetch https://github.com/TencentCloudAgentRuntime/ags-cli.git refs/pull/178/head
git switch --detach FETCH_HEAD
mkdir -p build
go build -tags=preview -o build/agr ./cmd/agr
export PATH="$PWD/build:$PATH"
agr version
agr endpoint --help
```

## 1. Configure the environment

Run the remaining commands from `examples/endpoint-cookbook` in the same shell.
Copy `.env.example` to `.env` and fill in `AGR_REGION` and
`AGR_CLOUD_ENDPOINT`. The latter is the **control-plane host**. The MCP client
uses the separate HTTPS URL returned by Endpoint.

```bash
cp .env.example .env
# Edit .env before continuing.
set -a
. ./.env
set +a
agr status
agr endpoint --help
make setup
```

## 2. Create an Endpoint and attach a Target

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

Copy the three IDs from the **same** row. The Target pins that version.

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

Confirm that the Target reports `ENABLED` and `READY` before invoking it.

## 3. Issue a token and verify MCP access

Use a short-lived token and keep it in the current shell. Token creation returns
the bearer credential once.

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

The client initializes an MCP session and prints a JSON object with the discovered
tool names and their input schemas. It uses `Authorization: Bearer` and closes
the session on exit. Keep the token out of `.env` and terminal output.

To verify a call as well, copy the **exact tool name** from the output and supply
arguments matching its schema:

```bash
MCP_TOOL_NAME='<name-from-tools-list>' MCP_TOOL_ARGS='{}' make run
```

For DeepWiki, look for `read_wiki_structure` in
`_meta["com.tencentags/endpoint"].upstreamToolName`. Use that row’s `name`
with `{"repoName":"facebook/react"}` as the arguments. Replace `{}` for any tool that requires input.
The client prints a second JSON object with the MCP call result and exits
nonzero if the tool reports an error.

## 4. Clean up

After the client exits, revoke the token, detach the Target, and delete the
Endpoint created in this example. Read the current revision before each delete.

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

After deletion, `agr endpoint get --endpoint-id "$endpoint_id"` should return
`ResourceNotFound`. If setup stopped early, clean up the resources whose IDs were returned. The
source Registry Record and version can be reused.

## Troubleshooting

- **`agr endpoint` is unknown.** Check `agr version`, the installed preview
  build, and the executable selected by `PATH`.
- **No READY MCP candidate appears.** Check Registry access and use a compatible
  MCP version visible to the current identity.
- **MCP authentication fails.** Check that the token is active and belongs to the
  Endpoint that returned the MCP URL.
- **Delete reports a revision conflict.** Fetch the resource again and retry
  with its current `Revision`.
