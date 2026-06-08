---
name: ags
description: >-
  Reference Agent Skill example for Tencent Cloud AGS / Agent Runtime workflows
  using the agr CLI. Covers AGS sandbox tools and instances, code or shell
  execution in AGS, file transfer, browser/mobile sandboxes, storage mounts,
  API keys, image pre-cache, debug instances, tool fork, and raw AGS Cloud API
  workflows.
  Do not use for generic local shell, Docker, Kubernetes, or non-Tencent Cloud
  sandbox tasks.
when_to_use: >-
  Trigger on AGS, Agent Runtime, agr, Tencent Cloud sandbox, 腾讯云沙箱, AGS 沙箱,
  code execution, shell execution, file transfer, browser sandbox, mobile
  sandbox, CFS/COS/Image storage mounts, API keys, image pre-cache, debug
  instance, tool fork, or AGS Cloud API requests.
---

# AGS With `agr`

Use `agr` for all AGS work.

## Start Here

First check the local CLI and credentials:

```bash
command -v agr
agr version -o json
agr status -o json
```

If `agr` is missing or outdated, install or upgrade it before running AGS workflows.

## Requirements

- **agr CLI (latest)** — run `agr version -o json` to check. Always use the latest release; see Install below if missing or outdated.
- **Tencent Cloud SecretId/SecretKey** — from [CAM Console](https://console.cloud.tencent.com/cam/capi). Temporary STS credentials also supported via `TENCENTCLOUD_TOKEN`.
- **Config**: `~/.agr/config.toml` by default, or `--config /path/to/config.toml`.

## Install

If `agr` is missing or outdated, install or upgrade to the latest release:

```bash
# One-line install / upgrade (macOS / Linux)
curl -fsSL https://github.com/TencentCloudAgentRuntime/ags-cli/releases/latest/download/install.sh | sh

# Or via go install (note: commit/built fields show "n/a")
go install github.com/TencentCloudAgentRuntime/ags-cli/cmd/agr@latest
```

Verify: `agr version`. If the installed version is not the latest, re-run the install command above.

## Configure Credentials

```bash
export TENCENTCLOUD_SECRET_ID="..."
export TENCENTCLOUD_SECRET_KEY="..."
agr init --secret-id "$TENCENTCLOUD_SECRET_ID" --secret-key "$TENCENTCLOUD_SECRET_KEY" --overwrite -o json
agr status -o json
agr doctor -o json
```

Temporary STS credentials:

```bash
export TENCENTCLOUD_SECRET_ID="tmp-id"
export TENCENTCLOUD_SECRET_KEY="tmp-key"
export TENCENTCLOUD_TOKEN="tmp-session-token"
```

Or pass `--token` on any command, or `agr config set token=<token>`.

Config priority: `--flag` > env vars > `~/.agr/config.toml` > defaults. Use `agr status` to inspect resolved values.

## Safety Rules

- If the user explicitly asks to create, fork, run, or debug an AGS resource, proceed with temporary, clearly named resources.
- Confirm before deleting resources, creating long-lived resources, using unclear billing/permission settings, or changing non-temporary production resources.
- Use explicit `--timeout` for temporary instances.
- Clean up temporary Instances and Tools with `instance delete` and `tool delete`.
- Do not print or commit `SecretId`, `SecretKey`, API keys, tokens, or RoleArn values.
- Prefer `--tool-id` in scripts. Use `--tool-name` only for known-unique temporary resources.
- Use `-o json` for automation. Use `--stream -o ndjson` only for streaming `code run` / `exec`.

## Choose The Right Reference

Keep this file as the core workflow. Load extra files only when the task needs them:

| Need | Read |
| --- | --- |
| COS/CFS/Image mount JSON and path rules | [references/mount-templates.md](references/mount-templates.md) |
| VPC networking, private subnets, security groups, private service access | [references/vpc-networking.md](references/vpc-networking.md) |
| Custom-image services, ports, probes, resources, env, registry access | [references/custom-images.md](references/custom-images.md) |
| Browser, mobile, API keys, raw API, image pre-cache, interactive login/proxy | [references/advanced-workflows.md](references/advanced-workflows.md) |
| Statuses, errors, CLI drift, cleanup problems | [references/troubleshooting.md](references/troubleshooting.md) |

## Common Task Patterns

- Run code once: check `agr status`, create or reuse a `code-interpreter` Tool, create an Instance with `--timeout`, wait for `RUNNING`, run `instance code run`, then delete temporary resources.
- Work with files: create or reuse an Instance, upload local files, run code or shell, download artifacts, then delete temporary resources.
- Fork an existing Tool: inspect the source Tool with `tool get`, choose a unique new `--tool-name`, pass only the intended overrides to `tool fork`, verify the fork with `tool get`.
- Add storage while creating or forking a Tool: read [references/mount-templates.md](references/mount-templates.md), include `--storage-mounts` or a full `--request`, ensure `RoleArn` is present when the mount requires it, then create a test Instance.
- Create a custom-image service: read [references/custom-images.md](references/custom-images.md), use a full request JSON with image, command, ports, resources, and probe, then create an Instance and verify the service with `instance proxy` or `exec`.
- Use VPC networking: read [references/vpc-networking.md](references/vpc-networking.md), collect subnet/security group IDs and the private target to test, then create or fork a new Tool with `NetworkMode: "VPC"`. Do not update an existing Tool into VPC mode.
- Debug a Tool: verify the source Tool has `RoleArn`, run `instance debug`, wait for `RUNNING`, and use `login` or `proxy` only when the user asks for an interactive session.

## Mental Model

| Object | Meaning |
| --- | --- |
| Tool | Reusable sandbox template: type, network, timeout, storage, image/custom config. |
| Instance | Running sandbox created from a Tool. Code, shell, files, ports, browser/mobile happen here. |
| API Key | Credential for E2B SDK / MCP paths, not Cloud API management. |
| Sandbox Token | Short-lived access credential for one Instance. |

CLI / Cloud API management uses Tencent Cloud `SecretId` / `SecretKey` (plus optional STS `Token`) with CAM permissions.

## Output Rules

JSON responses use an `agr.v1` envelope with `Status`, `Data`, `Failure`, `Warnings`, and `Meta`.

```bash
agr tool list --limit 20 -o json
agr tool list --limit 20 -o json --jq '.Data'
```

Rules:

- `--jq` requires `-o json`.
- `--stream` is incompatible with `-o json`; use text or `-o ndjson`.
- `agr instance login` and `agr instance proxy` are interactive and do not return JSON.
- On failure, inspect `.Failure.Code` / `.Failure.Hint`, then run `agr explain <CODE> -o json`.
- Server-side errors now include `RequestId` alongside `Code` and `Message`.

Exit codes: `0` success, `1` error, `2` usage, `4` auth, `255` remote_execution_failed. See `agr schema -o json --jq '.Data.ExitCodes'` for full list.

## Create A Tool

Use CLI short type names: `browser`, `code-interpreter`, `mobile`, `osworld`, `custom`. Do not pass Cloud API enum values.

```bash
tool_name="code-$(date +%s)-$$"
tool_id=$(agr tool create \
  --tool-name "$tool_name" \
  --tool-type code-interpreter \
  --network-configuration '{"NetworkMode":"SANDBOX"}' \
  -o json --jq '.Data.ToolId')

# Verify tool is ready
agr tool get "$tool_id" -o json
```

**Key flags for `tool create`:**

| Flag | Type | Notes |
| --- | --- | --- |
| `--tool-name` | string | **Required.** Must be unique within your AppId. Use a timestamp+PID suffix to avoid collisions. |
| `--tool-type` | string | **Required.** One of: `browser`, `code-interpreter`, `mobile`, `osworld`, `custom`. |
| `--network-configuration` | JSON | `{"NetworkMode":"SANDBOX\|PUBLIC\|VPC"}`. VPC mode also needs `VpcConfig.SubnetIds` and `VpcConfig.SecurityGroupIds`. |
| `--default-timeout` | duration | Default instance timeout, e.g. `30m`, `1h`, `2h30m`. Instances inherit this unless overridden on `instance create`. |
| `--storage-mounts` | JSON / `@file` | Array of mount objects. See [references/mount-templates.md](references/mount-templates.md) for COS/CFS/Image examples. Requires `--role-arn` when the storage source needs cloud access. |
| `--role-arn` | string | CAM role ARN required for COS/CFS mounts, private image registries, and debug instances. Format: `qcs::cam::uin/<uin>:roleName/<name>`. |
| `--tags` | JSON / `@file` | Array of `{"Key":"...","Value":"..."}` objects for resource tagging. |
| `--generate-skeleton` | — | Print a full JSON skeleton for `--request`. Use this first for complex configurations. |
| `--request` | JSON / `@file` / `-` | Supply the full request body as JSON when many nested fields are needed. |

Network modes:

| Mode | Use |
| --- | --- |
| `SANDBOX` | No Internet/VPC outbound; local code or mounted data. |
| `PUBLIC` | Internet access for packages, APIs, public web. |
| `VPC` | Private subnet/security group access. |

For custom images, VPC configs, tags, storage mounts, or many nested fields, start from the skeleton:

```bash
agr tool create --generate-skeleton > tool.json
# Edit tool.json, then:
agr tool create --request @tool.json -o json
```

**`tool create` behavior notes:**
- Tool name must be unique in your AppId; the create call fails immediately with a name conflict error if it already exists.
- `--storage-mounts` and `--role-arn` are independent flags; both can be supplied alongside `--request`.
- `--network-configuration` in `--request` overrides the `--network-configuration` flag if both are passed. Prefer one or the other.

**`tool list` filters:**

```bash
agr tool list --tool-type code-interpreter -o json
agr tool list --limit 20 -o json --jq '.Data.Items[].ToolId'
```

## Fork A Tool

Copy an existing Tool's settings into a new Tool with optional overrides:

```bash
agr tool get "$source_tool_id" -o json

forked_id=$(agr tool fork "$source_tool_id" \
  --tool-name "forked-$(date +%s)-$$" \
  --network-configuration '{"NetworkMode":"PUBLIC"}' \
  -o json --jq '.Data.ToolId')

agr tool get "$forked_id" -o json
```

`agr tool fork` copies all creatable settings from the source. Pass any `tool create` flags to override specific fields. For CFS/COS/Image mounts while forking, read [references/mount-templates.md](references/mount-templates.md).

## Update A Tool

```bash
agr tool update "$tool_id" --description "Updated description" -o json
agr tool list -o json
agr tool get "$tool_id" -o json
```

Tool names cannot be updated. Use `tool update` only for supported mutable fields such as description, tags, network configuration, and custom configuration. Do not update an existing Tool into VPC mode; create or fork a new Tool with VPC networking instead.

`agr tool update` does not expose a direct `--storage-mounts` flag. If the user wants to add or replace storage mounts on an existing Tool, prefer forking it into a new Tool with the intended `--storage-mounts`; see [references/mount-templates.md](references/mount-templates.md).

## Create And Manage An Instance

```bash
instance_id=$(agr instance create \
  --tool-id "$tool_id" \
  --timeout 30m \
  -o json --jq '.Data.InstanceId')

# Poll until RUNNING before sending work
agr instance get "$instance_id" -o json
```

**Key flags for `instance create`:**

| Flag | Type | Notes |
| --- | --- | --- |
| `--tool-id` | string | **Required** (or `--tool-name`). Specifies the Tool template to instantiate. |
| `--tool-name` | string | Alternative to `--tool-id`. Use only for known-unique tool names. |
| `--timeout` | duration | Override the Tool's default timeout, e.g. `30m`, `1h`, `2h30m`. Always set this for temporary instances. |
| `--mount-options` | JSON / `@file` / `-` | Per-instance mount overrides. Can only reference mount names already defined in the Tool's `StorageMounts`. Supports `MountPath`, `SubPath`, `ReadOnly` overrides. |
| `--metadata` | JSON / `@file` / `-` | Arbitrary key-value metadata attached to the instance. |
| `--auth-mode` | string | `DEFAULT` (inherited from Tool), `TOKEN` (sandbox token required), `NONE` (no auth), `PUBLIC` (no auth, public access). |

`--mount-options` lets you re-use one Tool mount under multiple paths in a single instance run:

```bash
agr instance create \
  --tool-id "$tool_id" \
  --timeout 30m \
  --mount-options '[
    {"Name":"cos-assets","MountPath":"/workspace/input","SubPath":"run-001","ReadOnly":true},
    {"Name":"cos-assets","MountPath":"/workspace/output","SubPath":"run-002","ReadOnly":false}
  ]' \
  -o json --jq '.Data.InstanceId'
```

**Instance status values:**

Instance responses may include these status values:

```text
STARTING, RUNNING, FAILED, STOPPING, STOPPED,
STARTING_FAILED, STOPPING_FAILED,
PAUSED, PAUSE_FAILED, RESUME_FAILED
```

Some command help text may list only a subset of status filter values. If status filtering is needed, prefer `agr instance list --help` / `agr schema -o json` for the installed CLI's accepted filter values.

Only `RUNNING` is safe for code, shell, file, browser/mobile, or port operations. `STARTING` is not ready — poll `instance get` before proceeding.

**Useful `instance list` filters:**

```bash
agr instance list --tool-id "$tool_id" -o json
agr instance list --filters '[{"Name":"Status","Values":["RUNNING"]}]' -o json
```

Lifecycle:

```bash
agr instance update "$instance_id" --timeout 1h -o json
agr instance pause "$instance_id" -o json
agr instance resume "$instance_id" -o json
agr instance delete "$instance_id" --ignore-not-found -o json
```

**Common pitfalls:**

| Problem | Cause | Fix |
| --- | --- | --- |
| Code/exec fails with "instance not ready" | Called before status is RUNNING | Always check status == RUNNING before sending work |
| `--mount-options` name not found | Name not in Tool's StorageMounts | Check `tool get` to see defined mount names |
| `--role-arn` missing for storage mount | Tool lacks CAM role | Add `--role-arn` when creating or forking the Tool |

## Debug An Instance

Creates a temporary debug Tool (start command switched to `/envd`, envd image mounted), then starts an Instance from it. The source Tool **must** have `RoleArn` configured.

```bash
debug_id=$(agr instance debug \
  --tool-id "$tool_id" \
  --timeout 30m \
  -o json --jq '.Data.InstanceId')
```

| Flag | Notes |
| --- | --- |
| `--tool-id` / `--tool-name` | Identify the source Tool. |
| `--timeout` | Debug instance lifetime (default `1h`). |
| `--mount-options` | JSON / `@file` / `-` — per-instance mount overrides. |
| `--metadata` | JSON / `@file` / `-` — arbitrary metadata. |
| `--custom-configuration` | JSON / `@file` / `-` — custom start config overrides. |

## Run Code Or Shell

```bash
agr instance code run "$instance_id" -l python -c "print('hello')" -o json
agr instance code run "$instance_id" -l bash -c "echo hello" -o json
agr instance exec "$instance_id" -o json -- pwd
agr instance exec "$instance_id" -o json --cwd /workspace --env APP_ENV=prod -- python app.py
```

Streaming:

```bash
agr instance code run "$instance_id" --stream -o ndjson -c "import time; [print(i) or time.sleep(1) for i in range(3)]"
agr instance exec "$instance_id" --stream -o ndjson -- tail -f /var/log/app.log
```

Temporary one-shot:

```bash
agr instance code run --create-temp-instance --tool-id "$tool_id" -c "print(42)" -o json
```

`--cleanup` options: `always` (default), `success`, `never`. JSON output includes `Data.ExecutionContext.SandboxInstanceId` and `Data.ExecutionContext.Cleanup`.

Supported `code run` languages: `python`, `javascript`, `typescript`, `r`, `java`, `bash`.

## Transfer Files

```bash
agr instance file upload "$instance_id" ./local.csv /workspace/local.csv -o json
agr instance file download "$instance_id" /workspace/result.json ./result.json -o json
```

Both commands support `--user`.

## Manage Config

```bash
agr config show          # show resolved config + sources
agr config set region=ap-beijing
agr config set token=<sts-session-token>
agr config path          # show config file location
```

Use `agr status` to verify resolved values including credentials.

## Clean Up

```bash
agr instance delete "$instance_id" --ignore-not-found -o json
agr tool delete "$tool_id" -o json || true
```

Deleting an Instance or Tool does not delete COS objects, CFS data, or registry images.

## Troubleshoot First

```bash
agr status -o json
agr doctor -o json
agr schema -o json
agr explain AUTH_FAILED -o json
# Per-flag help
agr instance create --network-configuration --help
# Debug output to stderr
agr instance list -o json --debug
```

Useful global flags: `--debug` (verbose stderr), `--non-interactive` (suppress prompts in scripts), `--no-color`, `--region`, `--domain`, `--cloud-endpoint`.

If public docs and the installed CLI disagree, trust `agr --help` / `agr schema -o json` for command syntax and product docs for concept meaning.
