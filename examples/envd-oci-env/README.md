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
environment and effective identity and uses them as defaults for commands and
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
