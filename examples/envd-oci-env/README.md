# Preserve OCI image environment variables with envd

This cookbook demonstrates why environment variables baked into an OCI image
can disappear from commands started through envd, and how to preserve them
when envd is the container's PID 1.

The workflow is executable: it builds an image from the bundled envd binary,
pre-caches the image, creates two temporary AGS sandboxes, verifies disabled
and enabled behavior, checks override precedence, and removes the temporary
resources.

## The problem

An OCI runtime gives the image's `ENV` values to the container's initial
process:

```text
OCI image ENV -> envd (PID 1) -> command started through envd
```

envd normally constructs a new environment for every child process instead of
implicitly copying its own environment. It includes identity variables such as
`PATH`, `HOME`, `USER`, and `LOGNAME`, then applies `/init` variables and the
environment supplied with the individual execution request.

As a result, envd itself can see an image variable while a command started
through envd cannot.

## The solution

The binary in `utils/envd/envd` adds an opt-in switch:

```text
EXEC_ENABLE_ALL_ENV=1
```

Set the switch on envd itself, usually through
`CustomConfiguration.Env`. envd then initializes each child environment from
its complete PID 1 environment before applying the existing explicit values.

The effective precedence, from lowest to highest, is:

```text
envd PID 1 environment
< PATH/HOME/USER/LOGNAME
< /init environment
< per-request environment
```

The default remains unchanged when the switch is absent or has a value other
than `1`.

> Security: enabling this switch exposes every variable in envd's environment
> to commands started through envd. Keep control-plane credentials out of the
> container environment, or use `/init`/per-request variables as an allowlist
> instead.

## Prerequisites

- Linux or macOS shell with Bash
- Docker with permission to push to your image registry
- `agr` CLI configured for your AGS account
- Tencent Cloud credentials in `TENCENTCLOUD_SECRET_ID` and
  `TENCENTCLOUD_SECRET_KEY`
- A CAM role that lets AGS pull the selected image
- An x86-64 base image containing `/bin/sh`, `/usr/bin/nice`,
  `/usr/bin/ionice`, and `readlink`

The supplied example uses `ubuntu:22.04`.

## Configure

From this directory:

```bash
make setup
```

Edit `.env` and set:

| Variable | Required | Meaning |
|---|---:|---|
| `TENCENTCLOUD_SECRET_ID` | yes | Tencent Cloud API credential |
| `TENCENTCLOUD_SECRET_KEY` | yes | Tencent Cloud API credential |
| `TENCENTCLOUD_REGION` | yes | AGS region, for example `ap-guangzhou` |
| `ENVD_DEMO_IMAGE` | yes | Image reference you can push and AGS can pull |
| `ENVD_IMAGE_REGISTRY_TYPE` | yes | `personal` or `enterprise` |
| `AGS_ROLE_ARN` | yes | CAM role used by AGS to pull the image |
| `AGS_EXEC_USER` | no | Existing image user; defaults to `root` |
| `BASE_IMAGE` | no | Application base image; defaults to `ubuntu:22.04` |

`.env` is ignored by Git. Never commit real credentials.

## Build and publish

Verify the bundled binary, build the demo image, and push it:

```bash
make verify
make build
make push
```

The Docker build context must remain the repository root because the
Dockerfile copies `utils/envd/envd`. The Makefile handles this automatically.

## Run the validation

```bash
make run
```

`make run` performs these operations:

1. Pre-caches `ENVD_DEMO_IMAGE` and waits for `Success`.
2. Creates a temporary Tool without `EXEC_ENABLE_ALL_ENV`.
3. Creates another temporary Tool with `EXEC_ENABLE_ALL_ENV=1`.
4. Starts a 20-minute sandbox from each Tool.
5. Confirms the disabled sandbox does not expose `ENVD_IMAGE_ONLY`.
6. Confirms the enabled sandbox uses envd as PID 1 and exposes both the
   image-baked and AGS runtime variables.
7. Confirms a per-request variable overrides the inherited image value.
8. Deletes both sandboxes and Tools, including on failure.

Expected terminal output includes:

```text
PASS: image env is absent when inheritance is disabled
PASS: PID 1, image env, and runtime env verified
PASS: request env overrides inherited image env
All envd inheritance checks passed
```

To execute the complete build-to-validation workflow:

```bash
make all
```

## Adapt an existing image

Keep the application image's existing `ENV` directives and add the bundled
binary:

```dockerfile
COPY utils/envd/envd /usr/bin/envd
RUN chmod 0755 /usr/bin/envd
ENTRYPOINT ["/usr/bin/envd"]
```

Then configure the AGS custom Tool with:

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

If a wrapper process starts envd instead of making it PID 1, envd inherits the
wrapper's environment; verify that the wrapper has not filtered the image
variables.

## Common failures

- **`MissingParameter.RoleArn`**: set `AGS_ROLE_ARN` to a role that can read
  the registry.
- **Image not found during pre-cache**: check the image reference and whether
  `ENVD_IMAGE_REGISTRY_TYPE` matches the registry.
- **Exec returns an internal error**: set `AGS_EXEC_USER` to a user that exists
  in the image.
- **Tool never becomes ready**: confirm envd listens on port `49983` and that
  the image contains the command dependencies listed under Prerequisites.
- **Unexpected secret exposure**: disable the switch and pass only approved
  values through `/init` or the individual execution request.
