# Phase 0 validation record

Complete this document with links to internal GitHub Actions runs. It separates
the runnable cookbook delivered in this repository from environment-specific
acceptance evidence.

## Exit criterion

An internal repository can use an existing GitHub Actions runner to create a fresh
AGS sandbox, execute a checked-out task, retrieve its status/logs/artifacts, and
clean up the sandbox.

## Representative workload matrix

| Scenario | Command | Expected result | Run URL | Result |
|---|---|---|---|---|
| Checkout upload and Python execution | `python examples/github-actions-sandbox/workload/ci_task.py` | Exit 0 and `result.json` returned | Pending | Pending |
| Workload failure propagation | `sh -c 'exit 7'` | Action exits 7; report says `workload_failed`; sandbox killed | Pending | Pending |
| Missing artifact path | `true` with a nonexistent artifact path | Exit 0; report contains artifact warning; sandbox killed | Pending | Pending |
| Cancelled workflow | Cancel while workload is running | Platform TTL or operations reconciliation removes sandbox | Pending | Pending |

Cancellation cannot be handled by a process `finally` block after GitHub terminates
the runner. Record the observed AGS timeout/TTL behavior here; native lifecycle
reconciliation belongs to the JIT runner phase.

## Image and toolchain inventory

| Requirement | Fixture expectation | Observed version | Decision |
|---|---|---|---|
| Shell | `bash` | Pending | Pending |
| Archive tools | `tar` with gzip support | Pending | Pending |
| Python | Python 3 | Pending | Pending |
| Git | Not required inside sandbox for the fixture | Pending | Pending |

Add the runtime, build tools, package managers, certificates, locale, and operating
system packages required by each accepted internal workload.

## Evidence to retain

- GitHub Actions run URL and conclusion
- uploaded `run-report.json`
- downloaded `artifacts.tar.gz` and expected file checks
- sandbox ID correlation in AGS operations logs
- create-to-command-start duration
- cleanup result, or TTL/reconciliation evidence for cancellation
- finalized network inventory from `NETWORK_REQUIREMENTS.md`

## Phase 0 sign-off

- [ ] At least one internal repository completed the end-to-end fixture.
- [ ] Success and non-zero workload exits were propagated correctly.
- [ ] Result status, logs, and artifacts were available from the Actions run.
- [ ] Normal completion and workload failure killed the sandbox.
- [ ] Cancellation cleanup behavior was measured and documented.
- [ ] No API key or explicitly forwarded secret appeared in the workspace archive,
      run report, or persisted sandbox metadata.
- [ ] Required image/toolchain components and sandbox egress destinations were
      recorded for the representative workload set.
