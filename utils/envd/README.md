# envd source with OCI environment inheritance

This directory contains buildable envd source code. It does not contain a
prebuilt envd binary.

The source is based on envd `0.5.14` at revision `a3fb26e`. This distribution
adds opt-in inheritance of the environment received by envd.

## Layout

| Path | Contents |
|---|---|
| `src/` | envd source code and tests |
| `shared/` | Only the shared source packages imported by envd |
| `Makefile` | Containerized build and test commands |
| `LICENSE` | Source license |

The envd module keeps its original module path. Its `go.mod` uses the local
`shared/` module, so the build does not require another source checkout.

## Build

Docker is the only required build dependency:

```bash
make build
```

The build uses Go `1.25.9` and produces:

```text
bin/envd
```

The default target is Linux/amd64. To build Linux/arm64:

```bash
make build TARGET_ARCH=arm64
```

No file under `bin/` is committed.

## Test

Run the environment inheritance and process regression tests:

```bash
make test
```

Run the same tests with the Go race detector:

```bash
make test-race
```

## Added behavior

The modification is in:

```text
src/internal/services/process/handler/handler.go
```

The default behavior is unchanged. When envd starts with
`EXEC_ENABLE_ALL_ENV=1`, a command started through envd first inherits envd's
complete process environment.

Variables configured when the sandbox starts, and variables passed to a
specific command with `agr instance exec --env`, are applied afterward. These
explicit values override inherited values with the same name.

Tests for disabled inheritance, enabled inheritance, and override order are in:

```text
src/internal/services/process/handler/environment_test.go
```

See `examples/envd-oci-env` for a multi-stage Docker build and AGS usage.
