# envd 0.5.14-modified source provenance

This distribution is based on the public `e2b-dev/infra` envd source at
revision `a3fb26eb4344bbaf66c0d2478c086623b560ef41`. It applies the changes
listed below and packages the result as `0.5.14-modified`.

The source changes:

- capture envd's startup identity and environment as command defaults;
- record that startup identity from the **real** UID, GID, and supplementary
  groups, so a setuid envd records the OCI User rather than root;
- keep it as an immutable numeric snapshot that does not depend on the passwd
  database, so an OCI User that is a bare numeric UID with no `/etc/passwd` entry
  can still execute commands;
- capture the startup working directory, so a request without an explicit `cwd`
  uses the business image's OCI Workdir instead of falling back to the user's
  home directory. If it cannot be determined, the default becomes `/` and a
  warning is written to stderr: leaving the default unset would reinstate the
  home-directory fallback the contract forbids;
- allow requests without an explicit username to use that startup identity,
  preserving its GID and supplementary groups exactly;
- resolve an explicit username against the business rootfs, including its
  supplementary groups from `/etc/group`. When the group database cannot be read
  the command still runs with the correct primary identity and the loss is
  recorded on the identity and logged, rather than rejecting a request that the
  baseline would have served;
- decide whether a child process needs `syscall.Credential` by comparing the
  target against envd's **effective** UID, GID, and current supplementary
  groups — never the real ones, because under setuid the real UID equals the
  default target while the effective UID is 0, and comparing real IDs would skip
  the credential and leak a root effective UID to the command;
- keep `PWD` consistent with `cmd.Dir` for both the default and an explicit
  `cwd`, and write the identity variables (`HOME`, `USER`, `LOGNAME`) from the
  resolved target rather than from envd's own startup snapshot, so they describe
  the process being started; request-level environment variables still override
  all of them;
- report a failure to start a command in the resolved working directory with the
  target user, the directory, and the path components that appear to lack search
  permission, and map a kernel permission refusal to `PermissionDenied` rather
  than `InvalidArgument`. The kernel remains the only authority on that decision — it also
  honors POSIX ACLs, SELinux, and capabilities that the classic permission bits
  do not show — so envd does not pre-judge it and never denies a request the
  kernel would have allowed;
- run requested commands directly so an unprivileged envd does not require
  privileges for nice, OOM score, or redundant credential changes;
- consistently use the no-op cgroup manager;
- default to standalone logging mode;
- avoid creating runtime marker files; and
- disable envd-managed port scanning and forwarding.

## Behavior contract for User and cwd

| Request | Identity used | Working directory used |
|---|---|---|
| no BasicAuth username, no `cwd` | envd's startup identity (OCI User) | envd's startup cwd (OCI Workdir) |
| explicit username, no `cwd` | that user, resolved in the business rootfs | envd's startup cwd |
| no BasicAuth username, explicit `cwd` | envd's startup identity | the requested path |
| explicit username, explicit `cwd` | that user | the requested path |

Because the identity variables are now written after the startup snapshot, an
`/init` caller that injects its own `HOME`, `USER`, or `LOGNAME` through
`EnvVars` no longer overrides them; a request-level variable still does. Nothing
on the AGS data-plane path injects those, and an image-provided `HOME` still
reaches the command, because the startup snapshot is where the startup identity's
`HomeDir` comes from.

`/init`'s `DefaultUser` and `DefaultWorkdir` remain a compatibility interface for
callers that set them. A `DefaultUser` naming a user other than the startup
identity takes precedence over the startup identity, and a `DefaultWorkdir`
replaces the captured startup cwd. Neither is set on the AGS data-plane path, so
the table above is what applies there. The precedence is covered by tests in
`internal/permissions`.

## Version reporting

`pkg.Version` still reports `0.5.14`. That string is what the E2B SDK parses and
compares against its `ENVD_DEFAULT_USER` gate (`0.4.0`), so it has to stay a
valid version: the directory name `0.5.14-modified` is **not** parseable by
`packaging.version.Version`, while `0.5.14` and `0.5.15` are.

Because the reported version does not change even though behavior did, the image
tag, envd commit, build revision, manifest digest, and binary SHA256 are the only
way to identify this artifact. Whether to raise `pkg.Version` to a new semver
(for example `0.5.15`) is a maintainer decision and is deliberately not made
here.

## Testing

```bash
make -C utils/envd test VERSION=0.5.14-modified
make -C utils/envd test-race VERSION=0.5.14-modified
make -C utils/envd build VERSION=0.5.14-modified
```

Unit tests cover the startup snapshot, group normalization, request identity
resolution, credential selection, cwd precedence, `PWD` and identity-variable
consistency, and the diagnostic built for a cwd failure.

The privileged tests below are what make the security claims real, so they must
actually run. `make -C utils/envd test VERSION=0.5.14-modified` runs the container
as the invoking user; verify with `-v` that the `TestSetuid*` and
`TestPrivileged*` cases report PASS rather than SKIP before treating this
distribution as verified.

Changing a process UID requires privileges, so the assertions that a command
*really* ends up with the intended identity live in build-tagged Linux tests that
run only when the effective UID is 0 and skip otherwise
(`ENVD_SKIP_PRIVILEGED_TESTS=1` skips them as well):

- `internal/execcontext/context_setuid_linux_test.go` re-executes the test binary
  through a root-owned mode-4755 copy of itself under an unprivileged credential
  that carries real supplementary groups. The child therefore runs with real UID
  != effective UID — the exact state a setuid envd runs in — and asserts that the
  snapshot records the real identity and its groups while the credential decision
  reads the effective identity. Without a genuine setuid child these two cannot be
  told apart, because real and effective IDs are equal in an ordinary process.
- `internal/services/process/handler/handler_privileged_linux_test.go` starts real
  processes through the handler and reads back `id`, `pwd`, and `$PWD`, including a
  check that a dropped process can no longer read a root-only directory, and that
  an unreachable cwd (both a locked leaf and a locked ancestor) fails with the user
  and directory named.

The delivery also ran a mutation harness that injects each forbidden
implementation in turn and asserts the suite fails for each,
so a passing suite is known to be load-bearing rather than merely green. It covers
the real-ID comparison, an ignored group list, an effective-ID startup snapshot,
dropped supplementary groups, a suppressed failure context, a missing `PWD`, an
identity rebuilt from a username, a suppressed cwd diagnostic, an always-permissive
search check, the non-terminating ancestor walk, an empty startup Workdir, a
flattened permission code, a rejected request on unreadable groups, a passwd entry
overwriting the captured GID, a silenced degradation warning, a Credential skipped
because the group list is incomplete, envd's own groups used in the Credential, an
unset degradation flag, a default-identity fallback for an unknown username, and
`%v` instead of `%w` when wrapping a start failure (which would keep the message
but break the permission-code mapping).

A mutation detected only by a compile failure is reported as a harness failure, not
a pass: a compile error says nothing about test coverage. The harness restores every
file it touches and re-runs the clean tree afterwards.

## Packaging

The distribution makes these packaging changes:

- `shared/` contains only the public shared packages imported by envd, and its
  module metadata is reduced to those dependencies.
- `src/go.mod` resolves the matching `shared/` module locally.
- Selected public source files, tests, and build metadata required by this
  distribution are included.
- The source Makefile provides a local binary build; distribution-level builds
  use the Makefile in `utils/envd`.
- Focused tests cover startup identity, environment, permissions, process
  execution, and filesystem identity defaults.

The source is distributed under Apache License 2.0. See `LICENSE`.
