# envd with OCI environment inheritance

This directory contains a Linux/amd64, statically linked `envd` binary with
opt-in parent-environment inheritance for processes started through envd.

## Artifact

| Field | Value |
|---|---|
| File | `envd` |
| envd version | `0.6.11` |
| Platform | Linux/amd64 |
| Linkage | Static |
| Go toolchain | `1.26.5` |
| Embedded build revision | `7c23f7b-execenv` |
| Build date | 2026-07-27 |
| SHA-256 | `6e48a7fa21384be23577f881ec8eaabc7610f15da62a02368e124144faa7f1ed` |

Verify the artifact before use:

```bash
./verify.sh
```

## Added behavior

The default remains unchanged. When envd starts without
`EXEC_ENABLE_ALL_ENV=1`, child processes receive only envd's normal explicit
environment.

When envd itself has `EXEC_ENABLE_ALL_ENV=1`, every process started through
envd first inherits envd's complete process environment. Variables configured
when the sandbox starts, and variables passed to a specific command with
`agr instance exec --env`, are applied afterward. These explicit values
override inherited values with the same name.

The exact production source change is included as a zero-context patch in
`enable-all-env.patch`. Apply it with `git apply --unidiff-zero`.

## Security note

This option deliberately passes the complete envd environment to child
processes. Do not enable it if envd's environment contains control-plane
credentials or other values that sandbox commands must not read. Use
command-specific `agr instance exec --env` variables when only a small
allowlist should be propagated.

See `examples/envd-oci-env` for a complete AGS validation workflow.
