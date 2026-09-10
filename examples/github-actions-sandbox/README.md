# GitHub Actions to AGS sandbox

This Phase 0 cookbook runs a checked-out GitHub repository inside a fresh Tencent
Cloud Agent Sandbox (AGS) from an existing GitHub-hosted runner. It validates the
workload path before adopting a native, just-in-time self-hosted runner:

```text
GitHub-hosted runner -> AGS SDK -> fresh sandbox -> command -> report/artifacts -> cleanup
```

This example does **not** register a GitHub Actions runner in AGS and does not
provide the future `runs-on: [self-hosted, tencent-agr]` integration.

## What it demonstrates

- packages the current checkout while excluding `.git`, local virtual environments,
  caches, `.env`, and `.env.*` files (but retaining `.env.example`)
- creates one sandbox and uploads the checkout
- runs one shell command without forwarding the host environment by default
- captures and propagates the workload exit code without relying on a non-zero
  data-plane command transport response
- returns stdout/stderr to the Actions log
- downloads a selected result path as `artifacts.tar.gz`
- writes a machine-readable `run-report.json`
- kills the sandbox after success, workload failure, or infrastructure failure

## Prerequisites

- Python 3.12 or newer
- [`uv`](https://docs.astral.sh/uv/)
- an AGS API key with access to the selected sandbox template
- outbound HTTPS from the existing runner to the configured AGS endpoint

## Required environment variables

```bash
export E2B_API_KEY="your_ags_api_key"
export E2B_DOMAIN="ap-guangzhou.tencentags.com"
```

Optional settings are shown in [`.env.example`](./.env.example). The script does
not load that file automatically.

## Run locally

Install the isolated dependency set:

```bash
make setup
```

From this example directory, run the included fixture:

```bash
make run
```

To upload a repository checkout and run its own CI command, set paths explicitly:

```bash
make run \
  WORKSPACE=/path/to/checkout \
  COMMAND="python -m unittest" \
  ARTIFACT_PATH=test-results \
  OUTPUT_DIR=ags-results
```

`ARTIFACT_PATH` is relative to the uploaded workspace. A missing artifact path
is reported as a warning and does not replace the workload's exit code.

Transport or artifact download failures set the overall `exit_code` to 2 and
`status` to `infrastructure_error`. The separate `workload_exit_code` retains the
business result (or is null if unavailable). `main.py` returns the overall code;
GNU Make returns 2 when a recipe fails, so read the report for the original code.

Make passes command and path values through environment variables without
expanding their contents. Quote arguments for your invoking shell, for example:

```bash
make run COMMAND='python -c "print(1)" && echo "$PATH" | head -c 100'
```

Shell variables and command substitutions in this single-quoted argument run
inside the sandbox. Pass literal values; Make variable references such as
`$(OTHER_VARIABLE)` are not expanded by this target.

If `OUTPUT_DIR` is inside `WORKSPACE`, its entire subtree is automatically excluded
from uploads, including on repeated runs. Other directories with the same name
remain included. The output directory cannot equal the workspace.

## Run with GitHub Actions

The repository includes
[`ags-sandbox-phase0.yml`](../../.github/workflows/ags-sandbox-phase0.yml).

1. Add `E2B_API_KEY` as a GitHub Actions repository secret.
2. Optionally add `E2B_DOMAIN` as a repository variable. The workflow defaults to
   `ap-guangzhou.tencentags.com`.
3. Open **Actions > AGS Sandbox Phase 0 > Run workflow**.
4. Inspect the job log and download the `ags-sandbox-...` workflow artifact.

The artifact contains:

- `run-report.json`: sandbox ID, template, workload outcome, timings, cleanup result,
  and a SHA-256 digest of the command (the command itself is not persisted)
- `artifacts.tar.gz`: the selected result directory produced inside the sandbox

## Forwarding workload credentials

No GitHub Actions environment variables or secrets are copied into the sandbox
automatically. Forward only the names a workload needs:

```bash
uv run python main.py \
  --workspace /path/to/checkout \
  --command "./ci.sh" \
  --artifact-path test-results \
  --env PACKAGE_REGISTRY_TOKEN
```

Do not embed secrets in `--command`: the shell command may be visible in process
diagnostics. Workload output is sent to the Actions log, so workflows remain
responsible for avoiding secret output and configuring GitHub masking.

## Validation

Run the unit tests without AGS credentials:

```bash
make test
```

For Phase 0 acceptance evidence and the expected network inventory, see
[`VALIDATION.md`](./VALIDATION.md) and
[`NETWORK_REQUIREMENTS.md`](./NETWORK_REQUIREMENTS.md).

## Common failure modes

- **Sandbox creation fails:** verify `E2B_API_KEY`, `E2B_DOMAIN`, template access,
  and runner-to-AGS HTTPS connectivity.
- **Command is not found:** the selected sandbox template does not contain the
  required runtime or toolchain. Record it in the image requirements section of
  `VALIDATION.md` and test a suitable managed template.
- **Dependency download fails:** add only the required package registry domains to
  the sandbox network policy; see `NETWORK_REQUIREMENTS.md`.
- **No artifact archive:** ensure `ARTIFACT_PATH` is relative to the checkout and is
  created by the workload.
- **Cleanup reports `failed`:** preserve `run-report.json` and ask AGS operations to
  reconcile the recorded sandbox ID.
