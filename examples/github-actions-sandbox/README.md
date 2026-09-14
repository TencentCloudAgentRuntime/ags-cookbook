# GitHub Actions to AGS sandbox

Evaluate agent-generated code without executing it on your GitHub Actions runner.
This example uploads the checkout to a fresh Tencent Cloud Agent Sandbox (AGS),
tests a candidate implementation, streams its logs, and returns JSON and JUnit
reports before destroying the sandbox.

The included `workload/candidate.py` is a deterministic stand-in for an agent's
output, not a live model call. Replace it with generated code implementing
`unique_in_order(values)` (deduplicate while preserving order). Five test cases
exercise empty input, duplicates, unique input, negative values, and strings.
No model API key or sandbox network access is needed for this fixture.

```text
GitHub-hosted runner -> AGS SDK -> fresh sandbox -> command -> report/artifacts -> cleanup
```

This example does **not** register a GitHub Actions runner in AGS and does not
provide a `runs-on: [self-hosted, tencent-agr]` integration. The evaluation harness
and candidate share a sandbox: this isolates execution from the host, but is not
a tamper-proof grading system. Upload only a disposable, secret-free checkout;
filename exclusions are not a general secret scanner.

## What it demonstrates

- packages the current checkout while excluding `.git`, local virtual environments,
  caches, `.env`, and `.env.*` files (but retaining `.env.example`)
- creates one sandbox and uploads the checkout
- runs one shell command without forwarding the host environment by default
- captures and propagates the workload exit code without relying on a non-zero
  data-plane command transport response
- streams stdout/stderr to the Actions log, retaining received output on timeout
- downloads a selected result path as `artifacts.tar.gz`
- writes a machine-readable `run-report.json`
- attempts to kill the sandbox after success, workload failure, or infrastructure failure

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

Expected workload output:

```text
Ran 5 tests
OK
{"tests": 5, "failures": 0, "errors": 0, "status": "passed"}
```

`ags-results/run-report.json` records `status: succeeded`, `workload_exit_code: 0`,
and `cleanup: killed`. `ags-results/artifacts.tar.gz` contains
`workload/output/result.json` and `workload/output/junit.xml`. An incorrect candidate
returns exit 1 and still produces test reports; a hang is bounded by the command timeout.

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

Only an explicit not-found result from the SDK's path check is treated as missing.
Permission or transport errors during that check, and any non-zero tar result for
an existing path, fail the run. Tar stdout/stderr is printed for diagnosis; no
artifact download is attempted after packaging fails.

Path-check, packaging, transport or artifact download failures set the overall `exit_code` to 2 and
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
At the start of each run, only the runner-owned `artifacts.tar.gz` and
`run-report.json` are removed from that directory. Unrelated files are preserved;
a failed or missing download cannot leave a previous run's archive behind.
Use a separate output directory for concurrent runs.

## Run with GitHub Actions

The repository includes
[`ags-sandbox-phase0.yml`](../../.github/workflows/ags-sandbox-phase0.yml).

1. Add `E2B_API_KEY` as a GitHub Actions repository secret.
2. Optionally add `E2B_DOMAIN` as a repository variable. The workflow defaults to
   `ap-guangzhou.tencentags.com`.
3. Open **Actions > AGS Sandbox Code Evaluation > Run workflow** (select the branch containing the workflow).
4. Inspect the job log and download the `ags-sandbox-...` workflow artifact.

The artifact contains:

- `run-report.json`: sandbox ID, template, workload outcome, timings, cleanup result,
  and a SHA-256 digest of the command (the command itself is not persisted)
- `artifacts.tar.gz`: the selected result directory produced inside the sandbox

The workflow uploads the repository root, so its archive paths start with
`examples/github-actions-sandbox/workload/output/`, unlike the shorter paths from
local `make run` above. The report-verification step expects the bundled candidate
to pass all five tests; adjust those expectations if you change the evaluation task.

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

Local tests execute only fixed, trusted fixtures, never your replaceable
`workload/candidate.py`. Use `make run` to evaluate that candidate in AGS;
do not run `workload/ci_task.py` directly on the host with untrusted code.

For reproducible validation steps and network requirements, see
[`VALIDATION.md`](./VALIDATION.md) and
[`NETWORK_REQUIREMENTS.md`](./NETWORK_REQUIREMENTS.md).

## Common failure modes

- **Sandbox creation fails:** verify `E2B_API_KEY`, `E2B_DOMAIN`, template access,
  and runner-to-AGS HTTPS connectivity.
- **Command is not found:** the selected sandbox template does not contain the
  required runtime or toolchain. This fixture needs Python 3, Bash, and tar/gzip.
- **Dependency download fails:** add only the required package registry domains to
  the sandbox network policy; see `NETWORK_REQUIREMENTS.md`.
- **No artifact archive:** ensure `ARTIFACT_PATH` is relative to the checkout and is
  created by the workload.
- **Cleanup reports `failed`:** preserve `run-report.json` and ask AGS operations to
  reconcile the recorded sandbox ID.

Cancellation or forced caller termination may prevent cleanup code from running.
The sandbox timeout (default 900 seconds) bounds its lifetime; it is not evidence
of immediate cleanup after cancelling a workflow.
