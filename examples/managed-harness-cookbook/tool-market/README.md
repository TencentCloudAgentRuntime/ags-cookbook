# Add official MCP servers, Skills, and Plugins from the tool market

The tool market provides official MCP servers, Skills, and Plugins published by the platform. This tutorial creates its own harness, browses the tool market, adds an MCP server that needs no credential and one that needs your own API key, and then explains how Skills and Plugins are referenced and which restrictions apply.

Complete the shared [prerequisites](../README.md#prerequisites) and [configuration](../README.md#configuration) before starting. Sample output masks real values.

## What the tool market is

The tool market is not a separate resource. It is the set of official Registries in Agent Registry. Queries use the fixed virtual Registry ID `MARKETPLACE`, which the service maps to the official Registries of the current region. Different regions may offer different tools.

| Market type | `--type` | Harness field | Reference flag |
| --- | --- | --- | --- |
| `MCP` | `mcp` | `MCPServers` | `--mcp <name>=MARKETPLACE/<record-id>/<version-id>` |
| `AGENT_SKILLS` | `skill` | `Skills` | `--skill MARKETPLACE/<record-id>/<version-id>` |
| `PLUGIN` | `plugin` | `Plugins` | `--plugin MARKETPLACE/<record-id>/<version-id>` |

Other types, such as A2A, cannot be referenced by a harness.

## Restrictions when referencing the tool market

| Restriction | Details |
| --- | --- |
| Fixed version | A reference must name a `VersionId`; the `latest` and `stable` labels are not accepted. A harness does not upgrade when a tool publishes a new version; change the reference to the new version, then create and publish a new revision. |
| Version state | Only approved (`APPROVED`) versions whose content is ready (`READY`) can be used. `agr harness tool list` shows only the `stable` version of each tool. |
| Access identity | When saving and publishing, the platform reads Registry with the initialization role of the harness (`--role-arn`), not with the caller. |
| Plugin compatibility | A Plugin version must declare **exactly** the engine and version of the harness (for example `pi` + `1.3.0`). This is checked when the draft is saved, and every selected Plugin is checked again when the engine or engine version changes. |
| Skill check timing | Skills are not checked when saving; they are downloaded at publish. An unreadable version, or two Skills whose `SKILL.md` names are the same, makes the revision `PUBLISH_FAILED`. Skills work with every engine. |
| MCP transport | Only the first `streamable-http` remote of the MCP declaration is used; an MCP server with only `sse`, stdio, or a local package cannot be used. MCP servers work with every engine. |
| MCP headers | When the market declares a required header without a default (usually an API key), you must supply it with `--mcp-header`, or the save is rejected. Header names are case-insensitive, and your value overrides the market default. |
| MCP credentials | A managed credential replaces only the `${credential}` you write in `--mcp-header`; it is never filled into headers declared by the market. Each MCP server takes one credential. |
| MCP names | pi and dsh accept only 1-32 letters, digits, `_`, or `-`. The CLI checks this locally; with raw `--mcp-servers` JSON an invalid name fails only when an instance starts. |
| Takedown | After a referenced version is taken down, new publishes fail; running instances are unaffected. Skill and Plugin download links can no longer be refreshed, so new instances may fail to start once the links expire. |

## 1. Set environment variables and create the harness

```bash
set -a
source ../.env
set +a
bash ../scripts/preflight.sh tool-market &&

export MODEL_PROVIDER_NAME="harness-market-$HARNESS_NAME_SUFFIX" &&
export HARNESS_NAME="harness-market-$HARNESS_NAME_SUFFIX" &&

MODEL_PROVIDER_ID=$(python3 ../scripts/resources.py create tool-market model-provider \
  --name "$MODEL_PROVIDER_NAME" \
  --tokenhub-api-key-id "$TOKENHUB_API_KEY_ID" \
  --model hy3) && export MODEL_PROVIDER_ID
```

Create the harness with the saved model provider ID:

```bash
HARNESS_ID=$(python3 ../scripts/resources.py create tool-market harness \
  --name "$HARNESS_NAME" \
  --engine pi \
  --engine-version 1.3.0 \
  --model "$MODEL_PROVIDER_ID:hy3" \
  --role-arn "$AGR_ROLE_ARN" \
  --subnet-id "$HARNESS_SUBNET_ID" \
  --security-group-id "$HARNESS_SECURITY_GROUP_ID" \
  --wait) && export HARNESS_ID
```

After revision 1 is published, read the saved Tool ID:

```bash
HARNESS_TOOL_ID=$(python3 ../scripts/resources.py get tool-market ToolId) && export HARNESS_TOOL_ID
```

## 2. Browse the tool market

```bash
agr harness tool list --region "$AGR_REGION" --type mcp
```

Expected output format; the actual tools depend on the region:

```text
TYPE  NAME             REFERENCE                             VERSION     AUTH      ENGINES
mcp   GitHub           MARKETPLACE/rec-********/rv-********  <version>   required  all
mcp   DeepWiki         MARKETPLACE/rec-********/rv-********  <version>   none      all
mcp   Microsoft Learn  MARKETPLACE/rec-********/rv-********  <version>   none      all
...
```

- `REFERENCE` is the fixed-version reference to pass to the harness.
- `AUTH` `required` means you need your own API key or token.
- `ENGINES` matters only for Plugins; MCP servers and Skills show `all`.

Search by keyword, or list only the Plugins the current harness can use:

```bash
agr harness tool list --region "$AGR_REGION" --search github
agr harness tool list --region "$AGR_REGION" --type plugin --compatible-with "$HARNESS_ID"
```

`--compatible-with` reads the engine and version of the harness draft. With `--type plugin`, the service returns only Plugins that declare that engine version; without `--type`, every tool is returned and a `USABLE` column shows whether the harness can use it.

## 3. Add an MCP server that needs no credential

Show the details of DeepWiki. Replace `rec-replace-me` with the DeepWiki Record ID from the previous list:

```bash
export DEEPWIKI_RECORD_ID='rec-replace-me'

agr harness tool get "$DEEPWIKI_RECORD_ID" --region "$AGR_REGION"
```

```text
Name:         DeepWiki
Type:         mcp
Reference:    MARKETPLACE/rec-********/rv-********
Version:      <version>
Publisher:    Cognition
Description:  <description>
Endpoint:     https://mcp.deepwiki.com/mcp
Credentials:  not required

Add to a harness (on update the list replaces the current one; repeat the items to keep):
  agr harness update <harness-id> --mcp deepwiki=MARKETPLACE/rec-********/rv-********
```

Copy `Reference`, add it to the harness, and publish:

```bash
export DEEPWIKI_REF='MARKETPLACE/rec-replace-me/rv-replace-me'

agr harness update "$HARNESS_ID" --region "$AGR_REGION" --mcp "deepwiki=$DEEPWIKI_REF"
agr harness revision create "$HARNESS_ID" --region "$AGR_REGION" --publish --wait
```

When saving, the service reads this MCP version and checks its type, state, remote, and required headers, and rejects the request if any check fails. After publishing, delete the old instances before trying the new tool (publishing affects only instances created afterwards):

```bash
agr instance list --tool-id "$HARNESS_TOOL_ID" --region "$AGR_REGION"
export HARNESS_INSTANCE_ID='replace-with-instance-id'
agr instance delete "$HARNESS_INSTANCE_ID" --region "$AGR_REGION" --yes --wait

agr harness prompt "$HARNESS_ID" --region "$AGR_REGION" \
  'Use the deepwiki tool to summarize the architecture of the facebook/react repository in three bullets.'
```

Tool-call progress lines starting with `⋯` appear while the reply streams.

To verify the MCP server was actually called, use `-o json` and inspect `Data.ToolCalls` for a `completed` call named `mcp__deepwiki__...`. With `-o ndjson`, the tool's result is also available in the `tool_call_update` events.

## 4. Add an MCP server that needs an API key

Many official MCP servers need your own API key. Take GitHub as an example:

```bash
export GITHUB_RECORD_ID='rec-replace-me'

agr harness tool get "$GITHUB_RECORD_ID" --region "$AGR_REGION"
```

```text
Name:         GitHub
Type:         mcp
Reference:    MARKETPLACE/rec-********/rv-********
Version:      <version>
Publisher:    GitHub
Description:  <description>
Endpoint:     https://api.githubcopilot.com/mcp/
Credentials:  required (get one at https://github.com/settings/personal-access-tokens)
Header:       Authorization: Bearer {access_token}  (you must set it)

Add to a harness (on update the list replaces the current one; repeat the items to keep):
  agr harness update <harness-id> --mcp github=MARKETPLACE/rec-********/rv-******** --mcp-credential github=<credential-provider-id>/<user-id>/<scope> --mcp-header 'github:Authorization=Bearer ${credential}'
Store the secret first: 'agr credential provider create --type SecretMultiUser', then 'agr credential secret set'.
```

The market declares the header as `Bearer {access_token}`, and the variable has no default, so you must supply it. Storing the token as a managed credential is recommended: the harness then keeps only a reference to it.

**Step 1: create a credential provider and store the token.**

```bash
GITHUB_CREDENTIAL_PROVIDER_ID=$(python3 ../scripts/resources.py create tool-market credential-provider --name "harness-market-github-$HARNESS_NAME_SUFFIX" --type SecretMultiUser) && export GITHUB_CREDENTIAL_PROVIDER_ID
```

The Provider ID is saved in `GITHUB_CREDENTIAL_PROVIDER_ID`. Store the token next. User IDs and scopes are application-defined; this example uses `harness-market` and `github` in both the harness reference and the cleanup helper. Keep these two values unchanged while following the tutorial. If you customize them, update the secret commands, `--mcp-credential` and the credential cleanup in `scripts/resources.py` together:

```bash
agr credential secret set --region "$AGR_REGION" \
  --credential-provider-id "$GITHUB_CREDENTIAL_PROVIDER_ID" \
  --user-id harness-market --scope github \
  --secret 'github_pat_replace-me'
```

**Step 2: add the MCP server.** `--mcp` replaces every MCP server, so also include DeepWiki from step 3:

```bash
export GITHUB_REF='MARKETPLACE/rec-replace-me/rv-replace-me'

agr harness update "$HARNESS_ID" --region "$AGR_REGION" \
  --mcp "deepwiki=$DEEPWIKI_REF" \
  --mcp "github=$GITHUB_REF" \
  --mcp-credential "github=$GITHUB_CREDENTIAL_PROVIDER_ID/harness-market/github" \
  --mcp-header 'github:Authorization=Bearer ${credential}'

agr harness revision diff "$HARNESS_ID" live draft --region "$AGR_REGION"
agr harness revision create "$HARNESS_ID" --region "$AGR_REGION" --publish --wait
```

Keep `${credential}` inside single quotes so the shell does not expand it. When an instance calls the MCP server, the platform reads the secret and replaces `${credential}`; the secret is never written to the harness or its revisions.

The UserId and scope in `--mcp-credential` are fixed in the harness configuration. All sessions using this GitHub MCP server share that token; the application user's identity does not change the credential. If users need separate credentials, design separate harness configurations and authorize access in your application.

More about headers and credentials:

- With only `--mcp github=...` and no `Authorization`, the save fails with `Registry MCP header "Authorization" is required and has no value or default`.
- With `--mcp-credential` but no `--mcp-header` using `${credential}`, the credential would never be read, so the CLI rejects it (`UNUSED_MCP_CREDENTIAL`).
- Some MCP servers need several secret headers (for example both a SecretId and a SecretKey). One MCP server takes one credential, so the other headers can only be passed as plain-text `--mcp-header` values, **which are stored in the harness configuration** and visible to anyone who can read the harness. Use least-privilege sub-account keys for such tools.

The current CLI masks MCP header values in `agr harness revision diff` (text and JSON) and `agr harness status -o json`. This does not change how the backend stores those headers or who can read the harness configuration.

## 5. Add Skills and Plugins

Skills and Plugins are referenced the same way and fill different fields:

```bash
agr harness tool list --region "$AGR_REGION" --type skill
agr harness tool list --region "$AGR_REGION" --type plugin --compatible-with "$HARNESS_ID"
```

If the tool market of the current region has no Skills or Plugins yet, the commands print `No tools found`. When tools are available, copy `REFERENCE` and add them:

```bash
agr harness update "$HARNESS_ID" --region "$AGR_REGION" \
  --skill MARKETPLACE/rec-replace-me/rv-replace-me \
  --plugin MARKETPLACE/rec-replace-me/rv-replace-me
agr harness revision create "$HARNESS_ID" --region "$AGR_REGION" --publish --wait
```

They are checked at different times:

- **Plugins** are checked by `harness update`. An incompatible engine returns `InvalidParameter` with the message `Plugin must reference a version that declares the selected Harness Engine version`. Changing `--engine` or `--engine-version` later checks every selected Plugin again.
- **Skills** are not checked by `harness update`; they are downloaded at publish. On failure the revision becomes `PUBLISH_FAILED`; read the reason with `agr harness revision get <harness-id> <revision>`. The live revision is unaffected. See [revisions](../revisions/README.md#6-a-failed-publish-leaves-the-live-revision-untouched) for how to recover.

`--skill` and `--plugin` also replace the whole list, so include the items you want to keep when updating.

## 6. Upgrade to a new tool version

A reference is pinned to one `VersionId`. When a tool publishes a new version, check its `stable` version and switch the reference:

```bash
agr harness tool get "$GITHUB_RECORD_ID" --region "$AGR_REGION" -o json --jq '.Data.Tool.Reference'
```

If the output differs from the current `GITHUB_REF`, repeat the `harness update` from step 4 with the new reference and publish a new revision. Use `agr harness tool get <record-id>/<version-id>` to inspect a specific version.

## 7. Clean up

Delete the resources saved for this scenario. The helper reads the IDs, region and endpoint from `.state/`, waits for deletion, and verifies the result. You can run it again after an interrupted cleanup. If you completed step 4, it also deletes the managed secret, disables the credential provider and then deletes it.

```bash
python3 ../scripts/resources.py cleanup tool-market --yes
```

## Common issues

| Symptom | Cause and fix |
| --- | --- |
| `harness tool list` returns `ResourceUnavailable` | The tool market is not open in this region yet. Use another region, or a private Registry |
| Save fails with `Registry MCP header "X" is required and has no value or default` | The MCP server needs header X from you. Add `--mcp-header` and `--mcp-credential` as in step 4 |
| Save fails with `Registry MCP descriptors have no supported streamable-http remote` | The MCP server has no streamable-http remote and cannot be used by a harness |
| Save fails with `Registry source type does not match the selected use` | The reference is in the wrong flag, for example a Skill passed to `--mcp`. Choose the flag by the `Type` shown in `harness tool get` |
| Save fails with `Plugin must reference a version that declares the selected Harness Engine version` | The Plugin does not support the harness engine version, or the version is unavailable. Choose a compatible version with `--compatible-with` |
| Save fails with `... is not readable with InitializeConfiguration.SandboxTool.RoleArn` | The initialization role cannot read Registry. Check the role permissions |
| Publish fails with `Skill preparation failed` | The Skill version is unreadable or has the same name as another Skill. Edit the draft and create a new revision |
| An instance rejects an MCP name at startup | A name with `.` or similar characters was written through `--mcp-servers`. Use `--mcp`, with only letters, digits, `_`, and `-` |
| The MCP server returns 401 | The token is invalid, or the user-id/scope of `--mcp-credential` differ from those used with `credential secret set` |
