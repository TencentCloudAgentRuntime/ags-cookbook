# Brain and Hands image sources

English | [中文](./README_zh.md)

Both images are built from public, pinned inputs:

| Image | Important pins |
| --- | --- |
| Brain | Node `24.8.0-bookworm-slim` by digest, pnpm `11.19.0`, DSH packages `0.1.0-rc.8`, E2B SDK `2.29.1`. |
| Hands | Go `1.26.5-alpine` and Ubuntu `24.04` by digest, envd commit `2acf2d51bd1e2fe146914f24c44f7ee07d2213c5` reporting version `0.6.13`. |

The Hands builder checks out the exact envd commit and verifies the compiled binary's version. The Brain build pins the `linux/amd64` child manifest for Node rather than an architecture-neutral tag, uses the committed `pnpm-lock.yaml`, applies the committed E2B no-redirect patch, compiles TypeScript, and removes development dependencies.

## Third-party license boundary

The exact DSH `0.1.0-rc.8` packages and E2B SDK `2.29.1` declare MIT licenses; their license files remain inside the production `node_modules` copied into Brain. The pinned envd source is Apache-2.0; Hands copies the upstream license from the same pinned commit to `/usr/share/doc/envd/LICENSE`. The Tencent Cloud SDK is Apache-2.0, while the other direct Node runtime dependencies use MIT, BSD-2-Clause, or Apache-2.0 licenses.

`pnpm licenses list --prod` currently resolves 215 production packages across MIT, Apache-2.0, BSD-2-Clause, BSD-3-Clause, ISC, 0BSD, BlueOak-1.0.0, and `(Apache-2.0 AND BSD-3-Clause)`. Regenerate that inventory and the image SBOM at publication time because transitive metadata and OS packages belong to the built artifact, not only to this source manifest.

## Build

Run from the `brain-hands` directory:

```bash
make build
```

Equivalent commands are:

```bash
podman build --platform linux/amd64 \
  --tag ags-cookbook/dsh-brain:local \
  --file dockerfiles/brain/Dockerfile .

podman build --platform linux/amd64 \
  --tag ags-cookbook/dsh-hands:local \
  --file dockerfiles/hands/Dockerfile dockerfiles/hands
```

Tencent Cloud mirrors are used for npm, Alpine, Ubuntu, and Go downloads. Git source still comes from the pinned public upstream URL.

## Verify before publication

```bash
pnpm typecheck
pnpm test
pnpm test:mysql

podman image inspect ags-cookbook/dsh-brain:local
podman image inspect ags-cookbook/dsh-hands:local
pnpm licenses list --prod
```

Start Brain with the variables in `.env.example` and require `GET /readyz` to return `200`. Start Hands and require `GET /health` on port `49983` to return `200`; then exercise a file write, read, and command through E2B `2.29.1`, not only through `curl`.

Before publishing a release, generate an SBOM and vulnerability report with the tools used by your registry, record the immutable image digests, and sign the digests. The checked-in [release manifest](../release-manifest.json) records source identities and intended image contents; it deliberately does not claim a published digest.

## Image boundaries

Brain contains DSH, MySQL connectivity, the Tencent Cloud API client, and the E2B client. It contains no authoritative local session directory.

Hands contains `envd`, `bash`, CA certificates, `curl`, `git`, `procps`, `ripgrep`, and `util-linux`. The build contract rejects a different envd version. Hands intentionally contains no Node.js, DSH, MySQL, SQLite, or COS integration.
