# Validate your sandbox integration

From this example directory, run `make setup` and `make test`.
Unit tests use fake sandbox services and require no cloud credentials. They cover
exit codes, cleanup, artifact errors, repeated output directories, streaming logs
on timeout/disconnection, literal Make arguments, and candidate reports.

## Real AGS run

Set the environment variables described in [README.md](./README.md), then run:

```bash
make run
tar -tzf ags-results/artifacts.tar.gz
```

Check that `run-report.json` records success, workload exit 0, and cleanup
`killed`. Inspect `workload/output/result.json` and `workload/output/junit.xml`
inside the archive: both should describe five tests with no failures or errors.
The console should show test progress before artifact collection starts.

To evaluate your own generated implementation, replace `workload/candidate.py`
or use `--candidate` with a path inside the uploaded workspace:

```bash
make run COMMAND='python workload/ci_task.py --candidate workload/candidate.py'
```

An incorrect implementation should return workload exit 1 and reports with
failures. An import error should produce an error report. Candidate code that
hangs or terminates the interpreter may not produce reports; inspect streamed
logs and the runner's infrastructure report instead.

## Failure checks

Use a disposable workspace/output directory, never production data.

| Check | Command / setup | Expected outcome |
|---|---|---|
| Workload failure | `make run COMMAND='exit 7'` | Workload code 7; overall workload failure; cleanup killed |
| Reused output with missing artifacts | After success, `make run COMMAND=true ARTIFACT_PATH=does-not-exist` | Warning, no old archive; unrelated output files remain |
| Command timeout | `AGS_COMMAND_TIMEOUT=5 make run COMMAND='echo started; sleep 30'` | Received log remains visible; overall code 2; cleanup attempted |

GNU Make returns 2 for a failed recipe; use `workload_exit_code` in the JSON
report to distinguish the workload result. Mocked transport failures test local
error handling, not all possible cloud outages.

## GitHub-hosted verification

Run the included workflow on the exact commit under test. Retain its URL,
`headSha`, console logs, run report, and archive contents in your PR or execution
record. A successful workflow alone does not prove that the expected test report
was returned: inspect the JSON and JUnit contents too.

Normal completion attempts explicit sandbox destruction. If the caller is killed
or the workflow is cancelled, its cleanup block may not execute; verify expiration
against the sandbox timeout separately. Do not claim immediate cancellation
cleanup from a successful normal run.
