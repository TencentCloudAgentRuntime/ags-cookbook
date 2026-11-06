# DSH handoff image: build notes

Back to the [DSH handoff reference](../README.md).

## Why the image must be built from source

The base example installs the published `@deepseek-ai/dsh` package. This scheme changes DSH itself (it keeps the Agent's teardown handle, adds a checkpoint before each new input, and adds a persistence barrier for `turn/start`), and the published package has none of that. So the build must:

1. fetch the pinned DSH source (tag `dsh-v0.2.1-rc.2`, verifying commit `687f282e8625c6b8d11ff58211a90524be2e4317`);
2. apply [`0001-stateless-handoff.patch`](./0001-stateless-handoff.patch);
3. install dependencies from the lockfile, run tests, and build the official way;
4. copy the compiled workspace into the runtime stage, then install this directory's plugin.

This is the same way the all-in-one image in `deployment-cookbook` patches DSH.

## Build

Run from the reference root (not this directory):

```sh
docker build --build-arg DSH_GATE_CONCURRENCY=1 -f dockerfiles/Dockerfile -t dsh-session-handoff:local .
```

Two groups of tests run during the build, and either one failing aborts it:

- after dependencies are installed and before the long build: three `session-controller` test files (Agent handle, prompt admission, controller);
- after `build:official`: the whole `agent-loop` suite (it guards the synchronous `turn/start` append and the claim barrier). Part of that suite takes file locks through DSH's native addon, which `build:official` compiles, so it can only run after the build.

## Build arguments

| Argument | Default | When to change it |
| --- | --- | --- |
| `DSH_GATE_CONCURRENCY` | unset (one per CPU) | Set to `1` on a Docker VM of about 8 GB. Otherwise the parallel build steps run out of memory and BuildKit reports `error reading from server: EOF` |
| `BUILD_IMAGE` | `node:24.22.2-bookworm-slim` | A same-version Node image from your internal mirror |
| `RUNTIME_IMAGE` | `node:24.8.0-bookworm-slim` | Same |
| `DSH_MODULES` | `/opt/deepseek-harness/apps/cli/node_modules/@deepseek-ai` | Usually never. Only if DSH's `@deepseek-ai/*` packages are not at that path |

The build and runtime stages use different Node images. The Debian keys in `node:24.8.0-bookworm-slim` predate the bookworm archive key rotation, so `apt-get update` fails with `NoPubKey`. The build stage needs `apt` to install `git`, `g++`, `make`, and `python3`, so it uses a newer image; the runtime stage keeps the base example's version.

## Troubleshooting

**`pnpm install` sits on SheetJS for a long time.**
One package in DSH's lockfile (`xlsx`) is only available from `cdn.sheetjs.com`, not the npm registry. That host is very slow on some networks (hundreds of bytes to tens of KB per second in our tests). The Dockerfile keeps pnpm's store in a BuildKit cache and raises the download timeout to 30 minutes, so **a second build reuses what was already downloaded**. If it still stalls: keep the build cache and retry from a network that can reach that host directly, or pre-seed the package in your internal mirror. Do not substitute an empty package or disable lockfile verification; the resulting build cannot be trusted.

**`apt-get update` reports `NoPubKey` / `not signed`.**
The build-stage Node image is too old. Keep the default `BUILD_IMAGE`, or use a newer bookworm image.

**Docker reports `error reading from server: EOF` mid-build, or an install step prints `Killed`.**
The Docker VM ran out of memory. Set `DSH_GATE_CONCURRENCY=1`. The runtime stage copies the compiled workspace instead of globally installing hundreds of packages again precisely to avoid this kind of memory peak.

**The image is large.**
The runtime stage keeps the complete compiled workspace and dependency graph to avoid re-resolving dependencies; the price is size. Build for the architecture you actually run (`amd64` / `arm64`), since native dependencies are tied to it.

## Upgrading DSH

The patch targets `dsh-v0.2.1-rc.2` only; do not assume it works for another version. To upgrade:

1. fetch the new tag and run `git apply --check` first;
2. conflicts usually appear in four places: create/resume and handle storage in `ApiSessionAgentController`, the admission path of `SessionCommandController.prompt`, the forwarding methods of `SessionController`, and `turn()` in `agent-loop`;
3. if upstream has since provided equivalent native "before new input" and "tear down an Agent by session" interfaces, delete the patch and register the service against the native interfaces;
4. if you also need the AGS deployment patch (`0001-support-ags-deployment-web.patch`), apply it first, then this one, and rerun the tests.
