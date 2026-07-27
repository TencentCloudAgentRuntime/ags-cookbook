# envd 0.5.14 source provenance

This directory contains source derived from the public
`e2b-dev/infra` repository at commit
`a3fb26eb4344bbaf66c0d2478c086623b560ef41`. At that revision,
`packages/envd/pkg/version.go` reports version `0.5.14`.

The distribution makes these changes:

- `src/internal/services/process/handler/handler.go` adds opt-in process
  environment inheritance through `EXEC_ENABLE_ALL_ENV=1`.
- `src/internal/services/process/handler/environment_test.go` tests disabled
  inheritance, enabled inheritance, and override precedence.
- Repository formatting hooks normalize trailing whitespace and final newlines
  in copied metadata, documentation, and protocol source files. These changes
  do not alter executable behavior.
- `shared/` contains only the public shared source files imported by this
  envd version. Its module file is reduced to those dependencies.

The source is distributed under Apache License 2.0. See `LICENSE`.
