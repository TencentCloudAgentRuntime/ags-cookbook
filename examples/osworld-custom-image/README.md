# Customize an OSWorld image on AGS

Open an OSWorld desktop, then build and run your own image with Claude Code installed.
If you only want to try the desktop, complete the first step. Docker is not required.

See the [Chinese base image guide](docs/image-guide.zh-CN.md) for more customization
options and OSWorld2 Docker usage.

## Prerequisites

- Python 3.11+ and [uv](https://docs.astral.sh/uv/).
- Tencent Cloud credentials with AGS permissions.
- An OSWorld base image address (to be added). `OSWORLD_BASE_IMAGE` is currently blank.
- Docker and your own CCR/TCR repository if you want to build a custom image.

## Step 1: Open a desktop

```bash
cd examples/osworld-custom-image
make setup
# Edit .env: cloud credentials, AGS_REGION and OSWORLD_BASE_IMAGE.
make quickstart
```

`make run` is an alias for `make quickstart`. The command prints a Tool ID,
an instance ID and a noVNC link. Open the link in your browser to use the desktop.

Automatic snapshots are enabled by the example. An existing snapshot is reused;
a new image can take longer on its first run. You can still cold-start while
its snapshot is being prepared. The desktop may appear shortly after the link is printed.

The example uses 8 CPUs, 16 GiB memory, a 20 GiB writable disk and at least 4 GiB
of shared memory at `/dev/shm`. Instances run for up to one hour.
Run `make clean` when you are finished.

## Step 2: Build an image with Claude Code

Set `CUSTOM_IMAGE` in `.env` to a new image address in your own repository,
using a versioned tag such as `:v1`. Log in with `docker login`, then run:

```bash
make build
make push
make custom
```

[Dockerfile.claude-code](Dockerfile.claude-code) installs Claude Code 2.1.153
on the base image and keeps the existing desktop. You can edit it to install
other software. Use a new tag whenever you publish new contents.

After startup, set `ANTHROPIC_API_KEY` in your local `.env`. Set
`ANTHROPIC_BASE_URL` as well if you use a custom endpoint. Then run:

```bash
make claude
```

The script sends the credentials to the running sandbox and opens Claude Code
in a desktop terminal. Enter your task there. Credentials are not built into
the container image. Do not save a credential-configured environment as a snapshot
for other people to use.

For a private TCR repository, you may also need to set `ROLE_ARN` to a role
that allows AGS to pull the image.

## noVNC authentication

Token authentication is enabled by default. The generated noVNC link already
includes the token. Treat the link as a credential and do not share it publicly.
Run `make quickstart` again for a fresh link, or `make custom` for the custom image.

To generate a link yourself, obtain an instance token with
`AcquireSandboxInstanceToken` and use the following code. Both the page and
the WebSocket connection need the token:

```python
from urllib.parse import urlencode

host = "5910-INSTANCE_ID.ap-guangzhou.tencentags.com"
token = "INSTANCE_TOKEN"
path = "websockify?" + urlencode({"token": token})
url = "https://" + host + "/vnc.html?" + urlencode({
    "autoconnect": "true", "resize": "scale",
    "access_token": token, "path": path,
})
```

For temporary testing, set `AUTH_MODE=none` before creating an instance to disable
token authentication. Anyone with the address can then access the desktop and
command APIs. Changing this setting does not affect an existing instance.

## Run OSWorld Benchmark

Follow the [OSWorld AGS example](../osworld-ags/README.md) to install the Benchmark.
Set `AGS_TEMPLATE` to the Tool ID printed by this example and `E2B_DOMAIN` to the
matching region. For OSWorld1, set `AGS_SUDO_PASSWORD=password`.
The Benchmark uses its own agent, independently of the Claude Code installation.

## Status and cleanup

```bash
make snapshot  # Check snapshot status.
make smoke     # Optional: check screenshots and noVNC in a separate instance, then stop it.
make clean     # Stop instances and delete this example's Tools.
```

You do not need to run `make smoke` for normal use. The local `.state/` directory
keeps Tool and instance details, plus any screenshots and test reports.
Keep it if creation fails so you can retry or clean up the resources.
