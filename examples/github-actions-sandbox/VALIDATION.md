# Phase 0 validation record

This record separates the runnable cookbook delivered in this repository from
environment-specific acceptance evidence. The first real validation was completed
on 2026-09-10 against commit `d6fcc90` in the `KayIter/ags-cookbook` fork.

## Exit criterion

An internal repository can use an existing GitHub Actions runner to create a fresh
AGS sandbox, execute a checked-out task, retrieve its status/logs/artifacts, and
clean up the sandbox.

## Representative workload matrix

| Scenario | Command | Expected result | Evidence | Result |
|---|---|---|---|---|
| Checkout upload and Python execution | `python examples/github-actions-sandbox/workload/ci_task.py` | Exit 0 and `result.json` returned | [GitHub Actions run 34460706363](https://github.com/KayIter/ags-cookbook/actions/runs/34460706363) | Passed; report, log, artifact contents, and cleanup verified |
| Workload failure propagation | `exit 7` | Wrapper reports exit 7 and `workload_failed`; workflow step fails; sandbox killed | Real AGS local runner probe | Passed after the exit-code transport fix in `d6fcc90` |
| Missing artifact path | `true` with a nonexistent artifact path | Exit 0; report contains artifact warning; sandbox killed | Real AGS local runner probe | Passed |
| Cancelled workflow | Terminate the caller with `SIGTERM` while `sleep 300` is running in a sandbox with a 30-second TTL | Platform TTL removes the sandbox | Real AGS local cancellation probe | Passed; running immediately after termination and absent after TTL |

Cancellation cannot rely on a process `finally` block after GitHub terminates the
runner. The probe deliberately observed the sandbox still running after caller
termination, then confirmed it left the running set after its 30-second AGS TTL.
Native lifecycle reconciliation remains part of the JIT runner phase.

Two pre-fix non-zero workload probes returned a data-plane `StreamReset` instead of
the business exit code. Both instances were killed. Commit `d6fcc90` changed the
protocol so the sandbox command transport exits normally and the business exit code
is read from a dedicated result file. The real exit-7 probe then passed.

## Image and toolchain inventory

| Requirement | Fixture expectation | Observed version | Decision |
|---|---|---|---|
| Shell | `bash` | Available; version not captured | Accepted for fixture; capture exact version before freezing a Runner Profile |
| Archive tools | `tar` with gzip support | Available; checkout extraction and artifact creation passed | Accepted for fixture |
| Python | Python 3 | 3.12.11 | Accepted for fixture |
| Git | Not required inside sandbox for the fixture | Not exercised | Keep out of the Phase 0 fixture requirement |

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

- [x] The designated validation fork completed the end-to-end fixture from a GitHub-hosted runner.
- [x] Success and non-zero workload exits were propagated correctly.
- [x] Result status, logs, and artifacts were available from the Actions run.
- [x] Normal completion and workload failure killed the sandbox.
- [x] Cancellation cleanup behavior was measured and documented.
- [x] No API key or explicitly forwarded secret appeared in the workspace archive,
      run report, or persisted sandbox metadata.
- [x] Required image/toolchain components and sandbox egress destinations were
      recorded for the representative workload set.
