# Managed Harness Cookbook

This directory shows how to manage managed harnesses with `agr` through independent examples. With a managed harness, the platform provides the agent runtime image (the Harness Engine); you choose the engine, models, system prompt, and Skills, Plugins, and MCP servers from the tool market or a private Registry. The first publish creates a Sandbox Tool and a Deployment for you, and the harness is served over [ACP](https://agentclientprotocol.com).

Compared with the [Deployment Cookbook](../deployment-cookbook/README.md): the Deployment Cookbook builds its own images and creates the Tool and Deployment itself. This directory builds no images; the harness manages the underlying Tool and Deployment.

## Core concepts

| Resource | Description | Command |
| --- | --- | --- |
| Model provider | One model service source (TokenHub or an OpenAI-compatible service) and its registered models. Every change creates an immutable revision | `agr model-provider` (alias `agr mp`) |
| Harness | The editable **draft**: engine and version, models, system prompt, Skills, Plugins, MCP, session space | `agr harness` |
| Harness revision | An **immutable snapshot** of the draft that also pins the current revision of each model provider. Revisions are what you publish | `agr harness revision` |
| Sandbox Tool / Deployment | Runtime resources the platform creates on the first publish and reuses afterwards | IDs shown by `agr harness get` |

A configuration change always follows **edit the draft (`update`) → freeze a revision (`revision create`) → publish (`publish`)**. Publishing affects only instances created afterwards; it does not restart existing instances or interrupt existing sessions.

## Prerequisites

- `agr` from the **preview channel**, with credentials initialized. The `harness` and `model-provider` commands exist only in preview builds. Download a release with a `-preview` suffix from [GitHub Releases](https://github.com/TencentCloudAgentRuntime/ags-cli/releases), or install from source:

  ```bash
  go install -tags=preview github.com/TencentCloudAgentRuntime/ags-cli/cmd/agr@<preview-tag>
  agr version   # channel: preview
  agr status
  agr doctor
  ```

  `go install` must include `-tags=preview`; otherwise it installs the stable build without these commands.

- Create an Agent Runtime CAM role by following the official [custom sandbox role and permission guide](https://cloud.tencent.com/document/product/1814/129691), and grant the CLI identity `cam:PassRole` on that role. The platform uses this role to create the Sandbox Tool and to read Agent Registry and TokenHub in the background.
- The CLI identity can read and write harnesses and model providers, and can create, describe, and delete the underlying Sandbox Tools and Deployments and call `AcquireDeploymentToken`. Later publishes and deletes still manage the underlying resources with the identity of the harness creator.
- A **VPC subnet and security group** in the target region. Managed harnesses support VPC networking only. Instances need outbound access to model services, Registry, and MCP servers, so make sure the VPC has a NAT gateway or another public egress.
- The **ApiKeyId of a TokenHub API key** (for example `ak-...`). A model provider stores only the ApiKeyId; the key value is read by the platform at publish time and never stored in any resource.

Every example runs in `ap-chongqing` and passes the region explicitly. Sample output masks account numbers, resource IDs, timestamps, and request IDs.

Each example creates its own resources. Copy the IDs from the command output into the environment variables shown in the next step, and run the cleanup section when you finish.

Run `make run` in this directory to list the scenarios. It only prints navigation and creates no cloud resources.

## Examples

| Example | Description |
| --- | --- |
| [simple](./simple/README.md) | Register a TokenHub model, create a harness and wait for the first revision, check the ACP endpoint, send one prompt, and clean up every resource. |
| [revisions](./revisions/README.md) | Edit the draft, compare differences, publish a new revision, roll back; pick up a model provider update through a new revision, and confirm that a failed publish leaves the live revision untouched. |
| [connect](./connect/README.md) | Four ways to connect: multi-turn `prompt`, `acp` for editors, `proxy` for local debugging, and `endpoint` for the real address, plus a `curl` walkthrough of ACP Streamable HTTP. |
| [tool-market](./tool-market/README.md) | Browse and add official MCP servers, Skills, and Plugins from the tool market: an MCP server without credentials, one with a managed credential, fixed versions and upgrades, and every restriction that applies to tool market references. |
| [scaling-session](./scaling-session/README.md) | Set instance size, on-demand start, and idle policy through the initialization configuration; keep sessions across instances with a session space; and learn which underlying settings you can adjust directly with Deployment commands. |

In each scenario directory, `README.md` is English and `README_zh.md` is Chinese.

## Conventions for agents and scripts

- Every command supports `-o json` with one envelope: `Status`, `Data`, and `Failure{Code,Kind,Message,Hint,Fix,Details}`. Branch on `Failure.Code`; do not match `Message`.
- `agr harness status <harness-id> -o json --jq '.Data.Next'` returns the suggested next command, or an empty string when nothing is pending.
- `agr schema harness.create -o json` lists flags, side effects, and failure codes; `--dry-run` prints the final request without sending it.
- Without a TTY, `harness delete` and `model-provider delete` fail immediately with `CONFIRMATION_REQUIRED` unless `--yes` is set; they never wait for input.
- `harness create` and `model-provider create` are not idempotent, and the CLI never retries them. After a timeout, check with `agr harness list --name <name>` before creating again.
