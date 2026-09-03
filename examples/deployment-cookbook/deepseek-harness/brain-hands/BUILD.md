# Build the Brain and Hands images (optional)

English | [中文](./BUILD_zh.md)

The [deployment tutorial](./README.md) already provides these `linux/amd64` images:

```text
ccr.ccs.tencentyun.com/ags.dev/deepseek-harness-brain:v0.1.1-rc.2-ags.4
ccr.ccs.tencentyun.com/ags.dev/deepseek-harness-hands-ubuntu:v0.6.13
ccr.ccs.tencentyun.com/ags.dev/deepseek-harness-hands-alpine:v0.6.13
```

Use this page only when you change the source or publish to your own registry.

## Verify and build locally

Install Node.js 24, pnpm 11.19, and Podman. From the `brain-hands` directory, run:

```bash
make install
make typecheck
make test
make build
```

With `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, and `MYSQL_DATABASE` set for a disposable MySQL 8 database, run `make test-mysql`. Repository CI runs this target against an ephemeral MySQL service.

The local image tags are:

```text
ags-cookbook/dsh-brain:local
ags-cookbook/dsh-hands:ubuntu-local
ags-cookbook/dsh-hands:alpine-local
```

## Publish to your registry

Tag each local image for the target registry, then push it with Podman:

```bash
podman login ccr.ccs.tencentyun.com
podman tag ags-cookbook/dsh-brain:local ccr.ccs.tencentyun.com/replace-me/deepseek-harness-brain:v0.1.1-rc.2-ags.4
podman tag ags-cookbook/dsh-hands:ubuntu-local ccr.ccs.tencentyun.com/replace-me/deepseek-harness-hands-ubuntu:v0.6.13
podman tag ags-cookbook/dsh-hands:alpine-local ccr.ccs.tencentyun.com/replace-me/deepseek-harness-hands-alpine:v0.6.13
```

```bash
podman push ccr.ccs.tencentyun.com/replace-me/deepseek-harness-brain:v0.1.1-rc.2-ags.4
podman push ccr.ccs.tencentyun.com/replace-me/deepseek-harness-hands-ubuntu:v0.6.13
podman push ccr.ccs.tencentyun.com/replace-me/deepseek-harness-hands-alpine:v0.6.13
```

Replace the three `Image` values in the deployment tutorial with your tags.
