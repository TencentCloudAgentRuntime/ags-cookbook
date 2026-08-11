# Preserve OCI image environment variables with envd

A container image can define environment variables with `ENV`.

When envd is the container's PID 1, envd can read those variables. The original
envd does not automatically pass all of them to new commands. A command started
through envd may therefore be unable to read the image's `ENV` values.

This cookbook provides modified envd source and shows how to compile it into an
application image.

## The symptom

Suppose an image contains:

```dockerfile
ENV MODEL_DIR=/models
ENTRYPOINT ["/usr/bin/envd"]
```

After the container starts, envd can read `MODEL_DIR=/models`. AGS then asks
envd to start an application or shell command. That new command may not be able
to read `MODEL_DIR`.

```text
image ENV -> envd (available) -> new command (missing)
```

## The cause

envd explicitly sets the environment list when it creates a new process.

The original envd adds basic variables and values explicitly supplied for the
sandbox or command. It does not copy envd's complete environment. The image
`ENV` values received from the OCI runtime are lost at this point.

## What we changed

The repository contains three independently buildable source distributions:

| envd version | Source path | Public source revision |
|---|---|---|
| `0.5.14` | `utils/envd/versions/0.5.14` | `a3fb26eb4344bbaf66c0d2478c086623b560ef41` |
| `0.5.14-modified` | `utils/envd/versions/0.5.14-modified` | `a3fb26eb4344bbaf66c0d2478c086623b560ef41` |
| `0.2.11` | `utils/envd/versions/0.2.11` | `1af78dd38a2cedce7f513c26aa2deb443cb0f0ef` |

The `0.5.14` and `0.2.11` distributions add this switch:

```text
EXEC_ENABLE_ALL_ENV=1
```

When enabled, envd copies its complete environment before starting a command:

```text
image ENV -> envd (available) -> new command (available)
```

The behavior is equivalent to:

```go
if os.Getenv("EXEC_ENABLE_ALL_ENV") == "1" {
    childEnv = append(childEnv, os.Environ()...)
}
```

The switch is enabled only when its value is exactly `1`. If it is absent or
has another value, envd keeps its original behavior.

`0.5.14-modified` takes a different approach: it snapshots envd's startup
environment and real identity and uses them as defaults for commands and
filesystem operations. Environment inheritance is always active in this
distribution, independently of `EXEC_ENABLE_ALL_ENV`. This also allows envd to
run unprivileged without trying to reapply its own credentials. Its binary
still reports `0.5.14`.

The `0.5.14` source includes upstream detection for cgroup v1 before enabling
cgroup v2 process placement. This prevents child-process startup from failing
with `bad file descriptor` in a cgroup v1 container.

## Choose a version

envd does not negotiate this version automatically. Use the version required
by the client or integration that connects to envd. If neither requires a
specific version, use the example default, `0.5.14`.

Set one of these values in `.env`:

```dotenv
ENVD_VERSION=0.5.14
```

or:

```dotenv
ENVD_VERSION=0.5.14-modified
```

or:

```dotenv
ENVD_VERSION=0.2.11
```

Use a distinct image tag for each source distribution, for example:

```dotenv
ENVD_DEMO_IMAGE=ccr.ccs.tencentyun.com/your-namespace/your-repository:envd-0.5.14
```

The Makefile selects the matching source directory, Go toolchain, and source
revision automatically. This example calls the selection `ENVD_VERSION`;
commands run directly in `utils/envd` call the same selection `VERSION`.
For a suffixed source selector such as `0.5.14-modified`, validation removes
the suffix before comparing `/usr/bin/envd -version`.

## Build envd into an image

The supplied Dockerfile uses a multi-stage build. Its version-selection part is:

```dockerfile
ARG GO_VERSION=1.25.9
ARG BASE_IMAGE=ubuntu:22.04

FROM golang:${GO_VERSION}-bookworm AS envd-builder
ARG ENVD_VERSION=0.5.14
WORKDIR /workspace
COPY utils/envd/versions/${ENVD_VERSION}/src ./src
COPY utils/envd/versions/${ENVD_VERSION}/shared ./shared
WORKDIR /workspace/src
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 \
    go build -trimpath -buildvcs=false -a -o /out/envd .

FROM ${BASE_IMAGE}
COPY --from=envd-builder /out/envd /usr/bin/envd
RUN chmod 0755 /usr/bin/envd
ENV EXEC_ENABLE_ALL_ENV=1
ENTRYPOINT ["/usr/bin/envd"]
```

The final image contains the compiled envd binary but not the Go toolchain.

## Configure AGS

Make envd the container's PID 1:

```json
{
  "Command": ["/usr/bin/envd"]
}
```

For the opt-in `0.5.14` and `0.2.11` distributions, enable complete environment
inheritance before envd starts. You can set it in the image:

```dockerfile
ENV EXEC_ENABLE_ALL_ENV=1
```

Or set it in the AGS Tool's container environment:

```json
{
  "Env": [
    {
      "Name": "EXEC_ENABLE_ALL_ENV",
      "Value": "1"
    }
  ]
}
```

Either method places the switch in envd's PID 1 environment. You do not need
both. If both set the same name, the AGS container configuration overrides the
image value. `0.5.14-modified` always inherits its startup environment and does
not require this switch.

After rebuilding the image and Tool, commands started through envd can read
the image `ENV`:

```bash
agr instance exec <instance-id> --user root -- printenv MODEL_DIR
```

Expected output:

```text
/models
```

Do not use `agr instance exec --env EXEC_ENABLE_ALL_ENV=1` to enable this
feature. That value is attached to one child-process request after envd has
already started, so it cannot change envd's inheritance behavior.

## How duplicate names are resolved

The same variable can be set through different inputs. Values applied later
take precedence:

| Source | Meaning | Scope |
|---|---|---|
| envd process environment | Final values given to PID 1 by the container runtime, including image `ENV` and AGS `CustomConfiguration.Env` | Starting layer for all later commands |
| Basic identity variables | `PATH`, `HOME`, `USER`, and `LOGNAME` selected by envd | All later commands |
| Sandbox startup defaults | Common command values supplied by the sandbox platform while envd is initialized, if any | All later commands |
| Current-command variables | `agr instance exec --env KEY=VALUE` | Current command only; highest priority |

To override an image value for one command:

```bash
agr instance exec <instance-id> \
  --user root \
  --env MODEL_DIR=/temporary-models \
  -- printenv MODEL_DIR
```

## Validate on AGS

Prerequisites:

- Bash, Docker, and `agr`
- A personal or enterprise image registry
- A CAM role that lets AGS pull the image
- An x86-64 base image containing `/bin/sh`, `/usr/bin/nice`,
  `/usr/bin/ionice`, and `readlink`

Create the configuration file:

```bash
make setup
```

Edit `.env` and set the Tencent Cloud credentials, region, image reference,
registry type, `AGS_ROLE_ARN`, and `ENVD_VERSION`.

Then run:

```bash
make verify
make build
make push
make run
```

`make run` pre-caches the selected image, creates two temporary sandboxes, and
checks:

- the binary reports the underlying envd version (`0.5.14` for
  `0.5.14-modified`);
- opt-in versions disable inheritance with `EXEC_ENABLE_ALL_ENV=0`, while
  `0.5.14-modified` continues to inherit its startup environment;
- `EXEC_ENABLE_ALL_ENV=1` exposes image and sandbox-level variables;
- a current-command value overrides an inherited value.

The example image contains `EXEC_ENABLE_ALL_ENV=1`. To test the disabled case
with that same image, the first temporary Tool sets
`CustomConfiguration.Env` to `EXEC_ENABLE_ALL_ENV=0`. This also verifies that
the AGS container environment overrides the image value. The second Tool does
not override the switch, so the image value remains enabled.
For `0.5.14-modified`, the first Tool instead verifies that startup environment
inheritance remains active because that distribution does not use the switch.

The temporary sandboxes and Tools are removed automatically.

Expected result for `ENVD_VERSION=0.5.14`:

```text
PASS: envd 0.5.14 does not inherit image env when disabled
PASS: envd 0.5.14 PID 1, image env, and runtime env verified
PASS: command-specific env overrides inherited image env
All envd inheritance checks passed
```

Repeat with `ENVD_VERSION=0.2.11` and a different image tag to validate the
older source version. Use `ENVD_VERSION=0.5.14-modified` to validate the
always-on startup identity and environment behavior; its PASS output reports
binary version `0.5.14`.

## Common failures

- **`MissingParameter.RoleArn`**: set `AGS_ROLE_ARN` to a role that can read
  the registry.
- **Image not found during pre-cache**: check the image reference and whether
  `ENVD_IMAGE_REGISTRY_TYPE` matches the registry.
- **Exec returns an internal error**: set `AGS_EXEC_USER` to a user that exists
  in the image.
- **Tool never becomes ready**: confirm envd listens on port `49983` and that
  the image contains the commands listed under Validate on AGS.

---

# OCI `USER` and `WORKDIR` as command defaults

Everything above is about the image's `ENV`. This section is about the other two
pieces of OCI configuration that a command needs: **who** it runs as and **where**
it runs.

Requires `ENVD_VERSION=0.5.14-modified`.

## The symptom

Suppose a business image ends with:

```dockerfile
USER appuser
WORKDIR /opt/app/work
```

and a command is started through the E2B Python SDK without naming a user or a
directory:

```python
sandbox.commands.run("id; pwd")
```

With unmodified envd the command runs as **root** in **`/root`** — neither the
image's `USER` nor its `WORKDIR`. Measured against this repository's own fixture:

```text
unmodified envd 0.5.14:  uid=0      pwd=/root
0.5.14-modified:         uid=10001  pwd=/opt/app/work
```

Two separate causes. For the identity, envd recorded its *effective* UID as its
startup identity; behind a setuid binary that is 0, so root was recorded as the
default user. For the directory, envd never captured its startup working
directory, so path resolution fell back to the user's home directory.

## The behavior contract

| SDK call | Runs as | Runs in |
|---|---|---|
| `run(cmd)` | the image's OCI `USER` | the image's OCI `WORKDIR` |
| `run(cmd, user="root")` | `root` | the image's OCI `WORKDIR` |
| `run(cmd, cwd="/tmp")` | the image's OCI `USER` | `/tmp` |
| `run(cmd, user="root", cwd="/tmp")` | `root` | `/tmp` |

An explicit `user` may be any username resolvable in the business rootfs. An OCI
`USER` that is a bare numeric UID with no `/etc/passwd` entry still works as the
default identity.

`PWD` always matches the directory the process actually starts in. If the target
user cannot enter the resolved directory, the request fails with an error naming
both the user and the directory.

## Why the envd Image Volume is setuid

envd is delivered separately from the business image, mounted through
`StorageMounts.Image`. An Image Volume contributes **files only**: its own OCI
`USER`, `WORKDIR`, `ENTRYPOINT`, `CMD`, and `ENV` are not merged into the business
process. The business image supplies all of those.

For envd to switch a command to an explicitly requested user it needs privilege it
would not otherwise have, because the OCI runtime starts it as the image's
unprivileged `USER`. That comes from the file metadata:

```text
/usr/bin/envd   owner 0:0   mode 4755
```

The kernel then gives envd:

```text
real UID = the image's OCI USER      effective UID = 0
```

envd records the **real** identity as the default, and drops back to it for every
command that does not request another user. `Dockerfile.envd-volume` fixes the
ownership and mode in the layer, because the mount is read-only and cannot be
chmod-ed at runtime.

Two mount-level prerequisites: the mount must not be `nosuid`, and the process
must have `NoNewPrivs=0`. Either one suppresses the setuid bit.

## Files

| File | Purpose |
|---|---|
| `Dockerfile.envd-volume` | the Image Volume artifact: `/usr/bin/envd` as `0:0`, mode `4755`, on `scratch` |
| `Dockerfile.fixture-a` | business fixture: `USER appuser`, `WORKDIR /opt/app/work`, several users and a shared group |
| `Dockerfile.fixture-b` | business fixture: `USER 61234:61235` with no passwd entry |
| `verify-envd-volume.sh` | checks `0:0`/`4755` in the exported image layer |
| `validate_user_workdir.py` | the assertions, through the E2B Python SDK |
| `validate_user_workdir.sh` | prepares AGS resources, runs the assertions, cleans up |

## Build and verify

```bash
make envd-volume-build ENVD_VERSION=0.5.14-modified \
    ENVD_VOLUME_IMAGE=<registry>/<namespace>/envd-oci-user-workdir:<unique-tag>
```

`envd-volume-build` runs the envd test suite first, then builds, then verifies the
layer metadata. Verify an existing image on its own with:

```bash
make envd-volume-verify ENVD_VOLUME_IMAGE=<reference>
```

Expected output:

```text
   tar owner:  0:0
   OK: owner is 0:0
   OK: mode is -rwsr-xr-x (4755), setuid bit present
   sha256:     <binary digest>
   envd commit:<repository commit>
   image commit:<repository commit>
VERIFY OK: ... carries /usr/bin/envd as 0:0 mode 4755
```

Do not tag the artifact `latest`. A mutable tag cannot be pinned to a digest, and
the digest is how a specific envd build is identified.

Then the fixtures, and the push:

```bash
make fixtures-build FIXTURE_A_IMAGE=<ref-a> FIXTURE_B_IMAGE=<ref-b>
make user-workdir-push ENVD_VERSION=0.5.14-modified \
    ENVD_VOLUME_IMAGE=<ref> FIXTURE_A_IMAGE=<ref-a> FIXTURE_B_IMAGE=<ref-b>
```

## Run on AGS

```bash
make setup            # then edit .env
make run-user-workdir
```

The Tool mounts the Image Volume read-only and points its `Command` at the
mounted binary:

```text
StorageMounts[0].MountPath                       /opt/envd
StorageMounts[0].StorageSource.Image.Reference   <envd Image Volume>
CustomConfiguration.Image                        <business fixture>
CustomConfiguration.Command                      ["/opt/envd/usr/bin/envd"]
```

`ImageRegistryType` accepts `personal` or `enterprise`. Confirm the current
accepted values with `agr schema` rather than copying them from older documents.
`--role-arn` is required whenever `--storage-mounts` is used, and
`Probe.ReadyTimeoutMs` is capped at `30000`.

`validate_user_workdir.sh` deletes every Tool and Instance it creates, including on
failure, and fails the run if cleanup cannot be proven. It pre-caches the envd
Image Volume and both business fixtures; the volume digest returned by AGS must
equal `ENVD_VOLUME_IMAGE_DIGEST`.

## Two AGS integration settings

**Normalize the API-key prefix.** AGS issues an `ark_...` key. Replace only the
`ark_` prefix with `e2b_` before giving it to the E2B SDK; the AGS data plane
accepts the normalized key. SDK 2.35 still rejects AGS's non-hex suffix locally,
so use `e2b >= 2.30` with `E2B_VALIDATE_API_KEY=false`. The script performs both
steps from `AGS_API_KEY` without printing the secret.

**Set the envd compatibility version in Instance Metadata.** In the Cloud API or
a full `--request` body, create each sandbox with:

```yaml
- Name: x-envd-version
  Value: 0.4.0
```

The SDK injects its historical default username `user` whenever the reported
version is below `0.4.0`:

```python
if user is None and envd_version < ENVD_DEFAULT_USER:   # 0.4.0
    user = default_username                             # "user"
```

A backend whitelist may supply the value when Metadata is absent; if no rule
matches, AGS reports `0.2.10`. Passing Metadata makes the behavior deterministic.
The validation asserts that the SDK sees exactly `0.4.0` and never patches the
SDK version gate.

The Cloud API and full request body use `Name/Value`. The `agr instance create
--metadata` convenience flag uses `Key/Value` and maps it to the Cloud API shape;
the included script follows the CLI form.

The SandPortal path must also be a version that does not synthesize a default
cwd. The current implementation forwards an omitted cwd unchanged, allowing
envd to use the business image's OCI `WORKDIR`.

To inspect the value seen by the SDK:

```python
print(sandbox._envd_version)          # what the control plane advertises
sandbox.commands.run("/opt/envd/usr/bin/envd -version", user="root")   # what is actually running
```

## Troubleshooting

| Symptom | Check |
|---|---|
| commands run as root instead of the OCI `USER` | `ENVD_VERSION` is `0.5.14-modified`; `envd -version` in the sandbox |
| commands run in `/root` instead of the OCI `WORKDIR` | same as above; the modified distribution captures the startup cwd |
| `invalid username: 'user'` | Instance Metadata is missing `x-envd-version=0.4.0` |
| `Invalid API key format` | normalize `ark_` to `e2b_`, use `e2b >= 2.30`, and set `E2B_VALIDATE_API_KEY=false` |
| explicit `user="root"` fails | `stat` the mounted envd: it must be `0:0` and `4755` |
| `NoNewPrivs: 1`, or `nosuid` on the mount | the setuid bit is suppressed; the sandbox cannot switch users |
| a command fails with a permission error on its cwd | the error names the user and the directory; check search permission on every parent |

Useful probes, all runnable through the SDK:

```python
sandbox.commands.run("id; pwd; echo $PWD")
sandbox.commands.run("stat -c '%u:%g %04a' /opt/envd/usr/bin/envd", user="root")
sandbox.commands.run("grep -E '^(Uid|Gid|Groups|NoNewPrivs):' /proc/1/status", user="root")
sandbox.commands.run("grep /opt/envd /proc/self/mountinfo", user="root")
```

`Uid: <oci-uid> 0 0 0` on envd's own PID 1 is the setuid state working as intended:
the real UID is the image's `USER`, and the effective UID is 0.
