# Preserve OCI image environment variables with envd

A container image can define environment variables with `ENV`.

When envd is the container's PID 1, envd can read those variables. However,
the original envd does not automatically pass them to new commands. A command
started through envd may therefore be unable to read the image's `ENV` values.

This cookbook provides a modified envd binary and explains how to add it to a
customer image.

## The symptom

Suppose an image contains:

```dockerfile
ENV MODEL_DIR=/models
ENTRYPOINT ["/usr/bin/envd"]
```

After the container starts, envd can read `MODEL_DIR=/models`. AGS then asks
envd to start an application or shell command. That new command may not be
able to read `MODEL_DIR`.

```text
image ENV -> envd (available) -> new command (missing)
```

## The cause

envd explicitly sets the environment list when it creates a new process.

The original envd adds basic variables and variables that were explicitly
provided. It does not copy envd's complete environment. The image `ENV` values
received from the OCI runtime are therefore lost at this point.

## What we changed

The binary in `utils/envd/envd` adds this switch:

```text
EXEC_ENABLE_ALL_ENV=1
```

When the switch is enabled, envd copies its complete environment before
starting a new command:

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

## How to use it

### 1. Add envd to the image

The bundled binary targets Linux/amd64.

```dockerfile
COPY utils/envd/envd /usr/bin/envd
RUN chmod 0755 /usr/bin/envd
ENTRYPOINT ["/usr/bin/envd"]
```

The Docker build context must contain `utils/envd/envd`. This example's
Makefile uses the repository root as the build context.

### 2. Make envd PID 1

Set the AGS custom Tool command to:

```json
{
  "Command": ["/usr/bin/envd"]
}
```

If a wrapper script starts envd, envd receives only the variables preserved by
that script. Make sure the wrapper does not filter the image `ENV` values.

### 3. Enable complete environment inheritance

Set the switch in the same AGS custom Tool:

```json
{
  "Command": ["/usr/bin/envd"],
  "Env": [
    {
      "Name": "EXEC_ENABLE_ALL_ENV",
      "Value": "1"
    }
  ]
}
```

After rebuilding the Tool and starting a sandbox, commands started through
envd can read the image `ENV`.

For example:

```bash
agr instance exec <instance-id> --user root -- printenv MODEL_DIR
```

Expected output:

```text
/models
```

## How duplicate names are resolved

The same variable can be set through different inputs. Values applied later
take precedence:

| Source | Meaning | Scope |
|---|---|---|
| envd process environment | OCI image `ENV` and AGS `CustomConfiguration.Env` | All later commands |
| Basic identity variables | `PATH`, `HOME`, `USER`, and `LOGNAME` selected by envd for the execution user | All later commands |
| Sandbox initialization variables | Shared defaults the platform can set by calling envd's `/init` endpoint during sandbox startup | All commands after initialization |
| Current-command variables | For example, `agr instance exec --env KEY=VALUE` | Current command only; highest priority |

Customers do not need to call `/init` for this use case. To temporarily
override an image value for one command, use `--env`:

```bash
agr instance exec <instance-id> \
  --user root \
  --env MODEL_DIR=/temporary-models \
  -- printenv MODEL_DIR
```

## Security

The switch passes every envd environment variable to new commands. That
environment may contain passwords, tokens, or proxy settings.

Enable it only when every variable in envd's environment may be read by
sandbox commands. If only a few variables are needed, pass them with
`agr instance exec --env` instead.

## Validation example

Prerequisites:

- Bash, Docker, and `agr`
- A personal or enterprise image registry you can push to
- A CAM role that lets AGS pull the image
- An x86-64 base image containing `/bin/sh`, `/usr/bin/nice`,
  `/usr/bin/ionice`, and `readlink`

Create the configuration file:

```bash
make setup
```

Edit `.env` and set the Tencent Cloud credentials, region, image reference,
registry type, and `AGS_ROLE_ARN`. Git ignores `.env`; never commit real
credentials.

Then run:

```bash
make verify
make build
make push
make run
```

`make run` checks the disabled case, the enabled case, and a
current-command override. It automatically removes the temporary sandboxes and
Tools.

Expected result:

```text
PASS: image env is absent when inheritance is disabled
PASS: PID 1, image env, and runtime env verified
PASS: command-specific env overrides inherited image env
All envd inheritance checks passed
```

## Common failures

- **`MissingParameter.RoleArn`**: set `AGS_ROLE_ARN` to a role that can read
  the registry.
- **Image not found during pre-cache**: check the image reference and whether
  `ENVD_IMAGE_REGISTRY_TYPE` matches the registry.
- **Exec returns an internal error**: set `AGS_EXEC_USER` to a user that exists
  in the image.
- **Tool never becomes ready**: confirm envd listens on port `49983` and that
  the image contains the commands listed under Validation example.
- **Unexpected secret exposure**: disable the switch and pass only approved
  values to the specific command.
