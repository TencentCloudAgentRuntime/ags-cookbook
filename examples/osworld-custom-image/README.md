# Customize an OSWorld image on AGS

Start an OSWorld desktop from a base OCI image, open noVNC, then build a derived
image containing Claude Code. AGS creates an automatic snapshot for eligible
Tools whose names contain `auto-snapshot`. Matching snapshots are reused;
otherwise the instance can cold-start while snapshot preparation continues.

The example uses OSWorld1. OSWorld2 shares the desktop interface but has separate
Docker storage requirements; see the [Chinese image guide](docs/image-guide.zh-CN.md).

## Prerequisites

- Python 3.11+ and [uv](https://docs.astral.sh/uv/).
- Tencent Cloud credentials with AGS Tool/instance permissions.
- Docker and your own CCR/TCR repository for the customization steps only.
- A reachable immutable OSWorld base image. The current `.env.example` points
  to a personal CCR validation candidate; publication to `ags-image` is pending.

For personal CCR, the script sends the immutable tag directly to Tool creation
for snapshot-converter compatibility, then checks the Tool's saved manifest
digest before starting an instance. No separate pre-cache API call is made.
Never overwrite the tag. Docker `FROM` keeps the full pinned reference.

## Open a desktop without building an image

```bash
cd examples/osworld-custom-image
make setup
# Edit .env: Tencent Cloud credentials and OSWORLD_BASE_IMAGE.
make quickstart
```

The Python script creates a custom Tool, waits for the Tool itself to be active,
and starts an instance without waiting for a new snapshot. It prints the
Tool ID, Instance ID and a browser-openable
noVNC URL. The instance remains running for up to one hour.

The example fixes the configuration at 8 CPUs, 16 GiB memory and the public
custom-Tool `Storage=20Gi` option. The image ensures `/dev/shm` is at least 4 GiB.
It starts `/sbin/init` and probes `GET :5000/platform`. These settings are not a
guarantee that every OSWorld2 heavy workload fits in this capacity.

`/platform` means the server responds; the optional `make smoke` check separately
waits for a real 1920×1080 desktop screenshot. Quickstart does not force that
validation; a cold desktop may take a little longer to appear in noVNC.
It does not require Chrome or CDP to be running
before task setup. Ports 5000, 5910, 8080 and 9222 are exposed.

## Build your own image

Set `CUSTOM_IMAGE` to a versioned image in your own CCR/TCR repository. Log in
using `docker login <your-registry>`; private TCR pulls may additionally require
`ROLE_ARN` for AGS. No cloud or model credential belongs in a Dockerfile.

```bash
make build
make push
make custom
```

[`Dockerfile.claude-code`](Dockerfile.claude-code) inherits the OSWorld base and
adds the native Claude Code 2.1.153 binary from the official npm package, with
SHA256 verification. Node.js is not required.
The original `/sbin/init` startup and desktop
services are preserved. The custom instance uses a separate local state file.
Building a derived image reuses OCI base layers; a different image/configuration
can require a new acceleration artifact and automatic snapshot.

To start Claude Code interactively, set `ANTHROPIC_API_KEY` and, if needed,
`ANTHROPIC_BASE_URL` in your local `.env`, then run:

```bash
make claude
```

The script uploads credentials through the authenticated OSWorld `5000` API to
a private directory in the running instance and opens a desktop terminal. It
does not send a model request automatically. Credentials are absent from the OCI
image and prebuilt Tool snapshot. Do not capture a new runtime snapshot after
injecting credentials unless retaining them is intentional.

## noVNC authentication

TOKEN is the default. The script obtains an instance token with
`AcquireSandboxInstanceToken` and includes it in both the page URL and the
WebSocket path. Treat the resulting URL as a credential; it expires with the
token/instance. Run `make quickstart` again to print a fresh token-backed link for
the retained instance.

To construct a link yourself, encode the WebSocket query first, then the page
query (replace the placeholders with the instance ID and API-issued token):

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

For deliberately unauthenticated temporary testing, set `AUTH_MODE=none` before
creating a new instance. The desktop and command APIs then have no AGS token
protection. Changing `.env` does not change an already running instance.

## Run OSWorld Benchmark

Use the existing [OSWorld AGS example](../osworld-ags/README.md). Follow its pinned
OSWorld checkout and dependency instructions, set `AGS_TEMPLATE` to the new Tool
ID and `E2B_DOMAIN` to the matching region, then run its existing agent. Set
`AGS_SUDO_PASSWORD` to the base image user's password (`password` for OSWorld1).
This example does not implement an agent. `OSWORLD_MOCK_LLM_DONE=1` validates setup
only and must not be reported as successful real-agent task completion.

## Status, verification and cleanup

```bash
make snapshot  # Describe status; does not wait for snapshot creation.
make smoke     # Separate test instance; stop it after validation, retain its Tool.
make clean     # Stop interactive instances and delete this example's Tools.
```

State and screenshots are saved under `.state/`; tokens and model credentials
are never saved there. The optional checks can also be run with `make check`.
Neither the checks nor the image conventions are enforced by the AGS platform.

Tool preparation failures and API timeouts retain local ownership information
for diagnosis/cleanup. This example creates the Tool directly, without a separate
image pre-cache API call. Platform-side Tool image preparation still applies.
For `tag@sha256` inputs, the script verifies the Tool's saved manifest digest
before starting an instance. Docker Hub/network failures inside OSWorld2 should
be distinguished from Docker storage errors.
