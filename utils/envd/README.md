# envd source with OCI environment inheritance

This directory contains four buildable envd source distributions. It does not
contain prebuilt binaries.

The standard distributions add opt-in environment inheritance. The
`0.5.14-modified` distribution captures envd's startup identity and environment
as unconditional defaults. The `0.5.14-oci` sibling adds OCI User and Workdir
command defaults without changing `0.5.14-modified`:

| envd version | Public source revision | Go version | Source path |
|---|---|---|---|
| `0.5.14` | `a3fb26eb4344bbaf66c0d2478c086623b560ef41` | `1.25.9` | `versions/0.5.14/` |
| `0.5.14-modified` | `a3fb26eb4344bbaf66c0d2478c086623b560ef41` | `1.25.9` | `versions/0.5.14-modified/` |
| `0.5.14-oci` | `a3fb26eb4344bbaf66c0d2478c086623b560ef41` | `1.25.9` | `versions/0.5.14-oci/` |
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
make build VERSION=0.5.14-modified
make build VERSION=0.5.14-oci
make build VERSION=0.2.11
```

`VERSION` selects source when commands are run directly in `utils/envd`. The
cookbook under `examples/envd-oci-env` uses `ENVD_VERSION` for the same choice
and passes it to this Makefile.

Or build all four:

```bash
make build-all
```

The Linux/amd64 outputs are:

```text
bin/envd-0.5.14
bin/envd-0.5.14-modified
bin/envd-0.5.14-oci
bin/envd-0.2.11
```

Build Linux/arm64 binaries with:

```bash
make build-all TARGET_ARCH=arm64
```

No file under `bin/` is committed.

## Test

Run the focused environment, identity, and process tests for all four:

```bash
make test-all
```

Test just one version with:

```bash
make test VERSION=0.5.14
make test VERSION=0.5.14-modified
make test VERSION=0.5.14-oci
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

The `0.5.14` and `0.2.11` functional modification is:

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

Both opt-in versions have tests for disabled inheritance, enabled inheritance, and
override order:

```text
versions/<version>/src/internal/services/process/handler/environment_test.go
```

`0.5.14-modified` instead snapshots envd's full startup environment and its
startup identity (the process's effective UID and GID).
Commands and filesystem operations use those defaults when a request does not
name another user. Environment inheritance is always active
for this distribution; `EXEC_ENABLE_ALL_ENV` does not control it. Its focused
tests are in `internal/execcontext`, `internal/permissions`, and the affected
service packages. The binary still reports version `0.5.14`.

### OCI User and Workdir as command defaults (`0.5.14-oci`)

This distribution also snapshots envd's startup identity and startup working
directory, and uses them for commands that do not request their own:

| Request | Identity used | Working directory used |
|---|---|---|
| no user, no `cwd` | envd's startup identity | envd's startup working directory |
| explicit user, no `cwd` | that user, resolved in the rootfs | envd's startup working directory |
| no user, explicit `cwd` | envd's startup identity | the requested path |
| explicit user, explicit `cwd` | that user | the requested path |

When a container runtime starts envd, its startup identity and working directory
come from the image's `USER` and `WORKDIR`, so those become the command defaults.

Three properties are worth calling out:

- The startup identity is captured from the process's **real** UID, GID, and
  supplementary groups. A setuid envd has an effective UID of 0, so reading the
  effective UID would record root as the default identity.
- It is a numeric snapshot and does not require a passwd entry, so an image whose
  `USER` is a bare numeric UID still works.
- Whether a child process needs explicit credentials is decided by comparing the
  target against envd's **effective** UID, GID, and current groups. Comparing real
  IDs would, under setuid, skip the credential change and leave the command with a
  root effective UID. When the target already matches, credentials are inherited
  instead of re-applied, so an unprivileged envd does not call `setgroups` without
  the privileges to do so.

`PWD` and the identity variables (`HOME`, `USER`, `LOGNAME`) describe the process
being started, not envd itself: they are written after the startup environment
snapshot, so an explicit user or an explicit `cwd` is reflected correctly.
Request-level environment variables still override all of them, matching the
existing precedence.

If a command cannot be started in the resolved working directory, the error names
the target user, the directory, and the path components that appear to lack search
permission. The kernel remains the only authority on that decision — it also
honors POSIX ACLs, SELinux, and capabilities that the permission bits do not show
— so envd does not pre-judge it and will not refuse a request the kernel would
have allowed.

If the startup working directory cannot be determined, the default becomes `/` and
a warning is written to stderr, so the default never silently reverts to the user's
home directory.

If the group database cannot be read when resolving an explicit user, the command
still runs with that user's primary group and a warning is logged. Losing the
supplementary groups does not reject the request, because the primary identity is
still correct.

`/init`'s `DefaultUser` and `DefaultWorkdir` remain available for callers that set
them and take precedence over the captured startup values. An `/init` caller that
injects `HOME`, `USER`, or `LOGNAME` through the environment no longer overrides
the identity variables, because those are now written afterwards; a request-level
variable still does. Nothing on the
E2B-compatible data-plane path sets them.

See `versions/0.5.14-oci/SOURCE.md` for the full change list and for how the
privileged setuid tests are run.

See `examples/envd-oci-env` for a selectable multi-stage Docker build and AGS
usage.
