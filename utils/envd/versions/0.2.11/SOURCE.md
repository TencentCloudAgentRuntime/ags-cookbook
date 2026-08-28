# envd 0.2.11 source provenance

This directory contains source derived from the public
`e2b-dev/infra` repository at commit
`1af78dd38a2cedce7f513c26aa2deb443cb0f0ef`. At that revision,
`packages/envd/main.go` reports version `0.2.11`.

The distribution makes these changes:

- `src/internal/services/process/handler/handler.go` adds opt-in process
  environment inheritance through `EXEC_ENABLE_ALL_ENV=1`.
- `src/internal/services/process/handler/environment_test.go` tests disabled
  inheritance, enabled inheritance, and override precedence.
- `src/go.mod` resolves the copied shared source through the sibling module.
- Repository formatting hooks normalize trailing whitespace and final newlines
  in copied metadata, documentation, and protocol source files. These changes
  do not alter executable behavior.
- `shared/` contains only the public shared source files imported by this
  envd version. Its module file is reduced to those dependencies.

The source is distributed under Apache License 2.0. See `LICENSE`.
