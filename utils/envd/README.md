# envd source with OCI environment inheritance

This directory contains two buildable envd source versions. It does not
contain prebuilt binaries.

Both versions add opt-in inheritance of the environment received by envd:

| envd version | Public source revision | Go version | Source path |
|---|---|---|---|
| `0.5.14` | `a3fb26eb4344bbaf66c0d2478c086623b560ef41` | `1.25.9` | `versions/0.5.14/` |
| `0.2.11` | `1af78dd38a2cedce7f513c26aa2deb443cb0f0ef` | `1.24.3` | `versions/0.2.11/` |

The versions are independent, and envd does not negotiate a version with its
client. Use the version required by your client or integration. If neither
requires a specific version, start with the default, `0.5.14`.

The `0.5.14` source already includes upstream cgroup v2 detection. It falls
back to the no-op manager on cgroup v1, preventing child-process startup from
failing with an invalid cgroup file descriptor.

## Layout

Each version contains:

| Path | Contents |
|---|---|
| `src/` | envd source code and tests |
| `shared/` | Only the public shared source packages imported by that version |
| `LICENSE` | Apache License 2.0 |
| `SOURCE.md` | Exact source revision and distribution changes |

Each envd module keeps its original module path. Its `go.mod` resolves the
matching `shared/` module locally, so the build does not require another source
checkout.

## Build

Docker is the only build dependency.

Build one version:

```bash
make build VERSION=0.5.14
make build VERSION=0.2.11
```

`VERSION` selects source when commands are run directly in `utils/envd`. The
cookbook under `examples/envd-oci-env` uses `ENVD_VERSION` for the same choice
and passes it to this Makefile.

Or build both:

```bash
make build-all
```

The Linux/amd64 outputs are:

```text
bin/envd-0.5.14
bin/envd-0.2.11
```

Build Linux/arm64 binaries with:

```bash
make build-all TARGET_ARCH=arm64
```

No file under `bin/` is committed.

## Test

Run the focused environment and process tests for both versions:

```bash
make test-all
```

Test just one version with:

```bash
make test VERSION=0.5.14
make test VERSION=0.2.11
```

Run the same tests with the Go race detector:

```bash
make test-race-all
```

Run every test and build step:

```bash
make verify-all
```

## Added behavior

The functional modification in each version is:

```text
versions/<version>/src/internal/services/process/handler/handler.go
```

The default behavior is unchanged. When envd starts with
`EXEC_ENABLE_ALL_ENV=1`, a command started through envd first inherits envd's
complete process environment.

The switch may come from image `ENV` or from the container environment supplied
when the sandbox is created. It must be present before envd starts; setting it
only on an individual child-process request is too late.

The container runtime combines OCI image `ENV` values and AGS
`CustomConfiguration.Env` values into envd's own process environment. envd
then applies identity variables, any common command defaults supplied by the
sandbox platform at startup, and the current command's variables. A value
applied later overrides an earlier value with the same name.

Each version has tests for disabled inheritance, enabled inheritance, and
override order:

```text
versions/<version>/src/internal/services/process/handler/environment_test.go
```

See `examples/envd-oci-env` for a selectable multi-stage Docker build and AGS
usage.
