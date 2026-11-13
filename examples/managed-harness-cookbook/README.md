# Managed Harness Cookbook

This directory introduces managed harnesses with `agr` through independently runnable examples. The platform provides the agent runtime image (the Harness Engine); you choose the engine, models, system prompt, and Skills, Plugins, and MCP servers from the tool market or a private Registry. The first publish creates a Sandbox Tool and a Deployment for you, and the harness is served over [ACP](https://agentclientprotocol.com).

Compared with the [Deployment Cookbook](../deployment-cookbook/README.md): the Deployment Cookbook builds its own images and creates the Tool and Deployment itself. This directory builds no images; the harness manages the underlying Tool and Deployment.

## Core concepts

| Resource | Description | Command |
| --- | --- | --- |
| Model provider | One model service source (TokenHub or an OpenAI-compatible service) and its registered models. Every change creates an immutable revision | `agr model-provider` (alias `agr mp`) |
| Harness | The editable **draft**: engine and version, models, system prompt, Skills, Plugins, MCP, session space | `agr harness` |
| Harness revision | An **immutable snapshot** of the draft that also pins the current revision of each model provider. Revisions are what you publish | `agr harness revision` |
| Sandbox Tool / Deployment | Runtime resources the platform creates on the first publish and reuses afterwards | IDs shown by `agr harness get` |

A configuration change always follows **edit the draft (`update`) → freeze a revision (`revision create`) → publish (`publish`)**. Publishing affects only instances created afterwards; it does not restart existing instances or interrupt existing sessions.

**A new session can still reach an old instance after publishing.** To verify a new revision, delete the old instances as shown in [revisions](./revisions/README.md#3-freeze-and-publish-revision-2), then send a prompt. A new SessionId alone does not ensure the new revision is used.

## Prerequisites

- `agr` from the **preview channel**, with credentials initialized, including the managed harness commands from [CLI PR #171](https://github.com/TencentCloudAgentRuntime/ags-cli/pull/171). Older preview builds may not include them. Download a release containing these commands with a `-preview` suffix from [GitHub Releases](https://github.com/TencentCloudAgentRuntime/ags-cli/releases), or install from source:

  ```bash
  go install -tags=preview 'github.com/TencentCloudAgentRuntime/ags-cli/cmd/agr@<preview-tag>'
  agr version   # channel: preview
  agr harness --help
  agr harness web --help
  agr model-provider --help
  agr status
  agr doctor
  ```

  Replace `<preview-tag>` with the desired preview release tag. `go install` must include `-tags=preview`; otherwise it installs the stable build without these commands.

  If no release contains these commands yet, use Go 1.25 or newer to build the CLI PR in a separate directory, then use that binary for every example:

  ```bash
  git clone https://github.com/TencentCloudAgentRuntime/ags-cli.git
  git -C ags-cli fetch origin pull/171/head
  git -C ags-cli switch --detach FETCH_HEAD
  (cd ags-cli && go build -tags preview -o ./build/agr ./cmd/agr)
  export PATH="$PWD/ags-cli/build:$PATH"
  agr version   # channel: preview
  agr harness --help
  agr harness web --help
  agr model-provider --help
  ```

- Create an Agent Runtime CAM role by following the official [custom sandbox role and permission guide](https://cloud.tencent.com/document/product/1814/129691), and grant the CLI identity `cam:PassRole` on that role. The platform uses this role to create the Sandbox Tool and to read Agent Registry and TokenHub in the background.
- The CLI identity can read and write harnesses and model providers, and can create, describe, and delete the underlying Sandbox Tools and Deployments and call `AcquireDeploymentToken`. Later publishes and deletes still manage the underlying resources with the identity of the harness creator.
- A **VPC subnet and security group** in the target region. Managed harnesses support VPC networking only. Instances need outbound access to model services, Registry, and MCP servers, so make sure the VPC has a NAT gateway or another public egress.
- The **ApiKeyId of a TokenHub API key** (for example `ak-...`). A model provider stores only the ApiKeyId; Harness, ModelProvider, and their revisions do not contain the key value. At publish time, the platform reads the key and writes it as a literal in the underlying Sandbox Tool's `NetworkPolicy` header-injection rules. Anyone with permission to describe that Tool can read the key, so treat Tool read access as access to the key.

Every example runs in `ap-chongqing` and passes the region explicitly. Sample output masks account numbers, resource IDs, timestamps, and request IDs.

Each example creates its own resources. Creation commands use `scripts/resources.py` to call `agr`, capture the returned IDs and save them with the region and control-plane endpoint in `.state/<scenario>.json`. Other steps use `agr` directly. Run the cleanup section when finished.

Run `make run` in this directory to list the scenarios. It only prints navigation and creates no cloud resources.

## Configuration

Install Python 3 and Bash for the helper scripts. Prepare the shared configuration once from this directory:

```bash
make setup
```

Edit `.env` using [.env.example](./.env.example): set the region, role ARN, subnet, security group, TokenHub ApiKeyId and a unique name suffix. All scenarios load this file.

For a custom control-plane endpoint, set `AGR_CLOUD_ENDPOINT` in `.env` or use your existing `agr` configuration. Keep that configuration consistent throughout the tutorial. The helper reads the effective endpoint from `agr config show`, including the CLI default, and records it as `CloudEndpoint` before creating resources. It rejects per-create `--cloud-endpoint` and `--config` overrides and refuses to mix endpoints within an unfinished scenario.

Then check the scenario you want to run:

```bash
make preflight SCENARIO=simple
```

Preflight checks required values, the preview CLI commands and `agr doctor`. `connect` also checks that the CLI includes `harness web` and requires `curl`. Missing `npx` or Node.js 22.13 or newer produces a warning: only the optional acpx example needs them, so you can continue with the other connection methods. Preflight creates no cloud resources. If it fails, fix the reported problem before continuing.

The creation helper returns the ID to the shell and records it for later steps. If a wait fails after the service returns an ID, the ID is kept for cleanup. To recover a variable in a new terminal with the same preview CLI on `PATH`:

```bash
set -a
source .env
set +a
HARNESS_ID=$(python3 scripts/resources.py get simple HarnessId) && export HARNESS_ID
```

You can clean up independently of the tutorial, using the recorded region, endpoint and IDs:

```bash
python3 scripts/resources.py cleanup simple --dry-run
make cleanup SCENARIO=simple
```

`make cleanup` loads `.env` if it exists. Both cleanup entry points pass the recorded endpoint explicitly, even in a fresh terminal or after the CLI configuration changes. Cleanup waits for deletion and checks that the recorded resources are absent. It can be repeated.

Older state files without `CloudEndpoint` stop with an error before querying or deleting resources. Confirm the original creation endpoint and add that value to the state file before continuing; do not assume the current CLI endpoint is the original one. Remove an old state file only after verifying that its resources are absent at the original endpoint.

If a network interruption leaves a create result unknown, check the resource name recorded under `Pending` with `agr list/get` at the recorded endpoint and finish that cleanup manually before removing the state file. Do not retry an unknown create blindly.

## Examples

| Example | Description |
| --- | --- |
| [simple](./simple/README.md) | Register a TokenHub model, create a harness and wait for the first revision, check the ACP endpoint, send one prompt, and clean up every resource. |
| [revisions](./revisions/README.md) | Edit the draft, compare differences, publish a new revision, roll back; pick up a model provider update through a new revision, and confirm that a failed publish leaves the live revision untouched. |
| [connect](./connect/README.md) | Five ways to connect to a DSH harness: multi-turn `prompt`, `acp` for editors, `proxy` for local debugging, `endpoint` for the real ACP address, and `web` for the native browser console. Includes a `curl` walkthrough of ACP Streamable HTTP. |
| [tool-market](./tool-market/README.md) | Browse and add official MCP servers, Skills, and Plugins from the tool market: an MCP server without credentials, one with a managed credential, fixed versions and upgrades, and every restriction that applies to tool market references. |
| [scaling-session](./scaling-session/README.md) | Set instance size, on-demand start, and idle policy through the initialization configuration; keep sessions across instances with a session space; and learn which underlying settings you can adjust directly with Deployment commands. |

In each scenario directory, `README.md` is English and `README_zh.md` is Chinese.

## Conventions for agents and scripts

- Commands that support `-o json` use one envelope: `Status`, `Data`, and `Failure{Code,Kind,Message,Hint,Fix,Details}`. Use `Failure.Kind` for categories such as `not_found`, and `Failure.Code` for specific errors; do not match `Message`. `harness acp` carries raw ACP over stdio instead; launch it with `-o text`, including when your configured default is JSON.
- `agr harness status <harness-id> -o json --jq '.Data.Next'` returns the suggested next command, or an empty string when nothing is pending.
- `agr schema harness.create -o json` lists flags, side effects, and failure codes; `--dry-run` prints the final request without sending it.
- Without a TTY, `harness delete` and `model-provider delete` fail immediately with `CONFIRMATION_REQUIRED` unless `--yes` is set; they never wait for input.
- `harness create` and `model-provider create` are not idempotent, and the CLI never retries them. After a timeout, check with `agr harness list --name <name>` before creating again.
- With a session space, all sessions of one harness use its Harness ID as UserId. Your application must track session ownership and authorize access; this does not automatically isolate your application's users.
- An MCP credential reference fixes a provider, UserId and scope in the harness configuration. All sessions using that MCP share that credential; changing SessionId does not select a different user's credential. See [tool-market](./tool-market/README.md#4-add-an-mcp-server-that-needs-an-api-key).
- Serialize requests for each SessionId in your application. Session persistence does not coordinate concurrent writers; do not send turns from two instances to the same session at once.
