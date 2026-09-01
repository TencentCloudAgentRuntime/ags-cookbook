# DeepSeek Harness all-in-one image

This directory builds the pinned image:

```text
ccr.ccs.tencentyun.com/ags.dev/deepseek-harness:v0.1.1-rc.2-ags.4
```

The Dockerfile clones tag `dsh-v0.1.1-rc.2` from the official DeepSeek repository, verifies commit `b150a551b8d465e31e418e1b2eaf5e79bbb7d28e`, applies the retained [`0001-support-ags-deployment-web.patch`](./0001-support-ags-deployment-web.patch), then installs dependencies, runs the patch-focused tests, and performs the official full build. The build stage uses the upstream release flow to pack both the `vendor` and `dsh` package families; the final `linux/amd64` stage installs those packages and starts the official CLI with Node's `--expose-internals` flag, without an extra wrapper script.

The patch contains only the four compatibility changes needed for Web deployment:

1. Permit an explicit `dsh web --host 0.0.0.0` binding.
2. Let `trustedHosts` accept a single-label wildcard such as `*.ap-shanghai.agents.tencentags.com`. It matches exactly one left-most DNS label and is not a general glob.
3. Accept a reverse-proxy request when its HTTPS `Origin` and rewritten `Host` each match an explicit `trustedHosts` entry. This covers the AGS gateway's external Deployment origin and internal instance host without trusting arbitrary authorities.
4. Add an explicit `--allow-remote-management` switch. Only requests that both pass `trustedHosts` validation and run with this switch may reach settings, credentials, model discovery, preset management, and other management RPCs that upstream pins to loopback. Without the switch, the upstream restriction remains intact.

## Build and publish

Log in to CCR:

```bash
podman login ccr.ccs.tencentyun.com
```

Build and push the `linux/amd64` image from this directory:

```bash
podman build \
  --platform linux/amd64 \
  --tag ccr.ccs.tencentyun.com/ags.dev/deepseek-harness:v0.1.1-rc.2-ags.4 \
  .

podman push \
  ccr.ccs.tencentyun.com/ags.dev/deepseek-harness:v0.1.1-rc.2-ags.4
```

Inspect the remote manifest:

```bash
skopeo inspect docker://ccr.ccs.tencentyun.com/ags.dev/deepseek-harness:v0.1.1-rc.2-ags.4
```

This example never publishes `latest`. For an upgrade, update the official tag, commit, patch, CCR version tag, and every image reference together, then rerun both the build-time tests and the complete deployment validation.
