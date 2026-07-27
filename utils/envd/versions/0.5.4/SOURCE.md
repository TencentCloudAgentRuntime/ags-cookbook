# envd 0.5.4 source provenance

This directory contains source derived from the public
`e2b-dev/infra` repository at commit
`017de20162f1d9ea340d3767eba2c43cd0dd8c33`. At that revision,
`packages/envd/main.go` reports version `0.5.4`.

The distribution makes these changes:

- `src/internal/services/process/handler/handler.go` adds opt-in process
  environment inheritance through `EXEC_ENABLE_ALL_ENV=1`.
- `src/internal/services/process/handler/environment_test.go` tests disabled
  inheritance, enabled inheritance, and override precedence.
- `src/internal/services/cgroups/cgroup2.go` backports the public upstream
  cgroup v2 detection fix from commit
  `452097909d71775a8953f1b4e4574519cbcb123d`. This prevents invalid cgroup
  file descriptors from breaking process startup on cgroup v1 systems.
- `src/internal/services/cgroups/cgroup2_test.go` tests that compatibility
  check.
- Repository formatting hooks normalize trailing whitespace and final newlines
  in copied metadata, documentation, and protocol source files. These changes
  do not alter executable behavior.
- `shared/` contains only the public shared source files imported by this
  envd version. Its module file is reduced to those dependencies.

The source is distributed under Apache License 2.0. See `LICENSE`.
