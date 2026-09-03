# Run Docker-in-Docker on AGS

This example provides a DinD image that can be used directly by an AGS Custom Tool. Once the Sandbox is ready, `dockerd`, `docker compose`, and `envd` are available immediately. Clients can upload files and execute commands as `root` without manually mounting storage or starting a daemon.

Public images:

- Guangzhou: `ccr.ccs.tencentyun.com/ags-image/dind:v1.0.0`
- Hong Kong: `hkccr.ccs.tencentyun.com/ags-image/dind:v1.0.0`
- OCI image index: `sha256:b1332e5cfaeaa335e1c3aae69ffd8a84b42dd78e014247e972d56003338595d3`
- Architecture: `linux/amd64`
- Build file: [`image/Dockerfile`](./image/Dockerfile)

The image is based on the official `docker:29.3.1-dind` image. It contains Docker Engine, Docker CLI, BuildKit, Docker Compose 5.1.1, Bash, util-linux, and [`envd` 0.5.14-oci](../../utils/envd/versions/0.5.14-oci/) built from this repository. This envd distribution preserves the image startup environment and default working directory.

The [`image/entrypoint.sh`](./image/entrypoint.sh) wrapper detects the cgroup layout, mounts the AGS-provided `/dev/vda` at `/mnt`, and bind-mounts Docker and containerd data onto that disk. It then starts and supervises `dockerd` and `envd` as `root`. The readiness probe succeeds only after both are available.

To customize the image, build it from this directory:

```bash
make build-image
```

Push the result to your own TCR/CCR repository, or use one of the public images above.

## Prerequisites

- Use the latest version of `agr`.
- Configure Tencent Cloud credentials.
- This example uses Hong Kong with `PUBLIC` networking because it downloads Harbor and example images from GitHub, PyPI, and Docker Hub.

## 1. Create the Tool and Sandbox

Run the setup check. It verifies that `agr` is installed and up to date, then creates `.env` from `.env.example` if needed:

```bash
make setup
```

Review `.env` before continuing. If `agr` does not already have Tencent Cloud credentials configured locally, set `TENCENTCLOUD_SECRET_ID` and `TENCENTCLOUD_SECRET_KEY`; also set `TENCENTCLOUD_TOKEN` when using temporary credentials. [`tool-custom-configuration.hk.json`](./tool-custom-configuration.hk.json) anonymously pulls the public Hong Kong image at a pinned digest and requests 4 CPUs, 8 GiB memory, and a 20 GiB disk. It does not require a `RoleArn`.

Create the Tool and Sandbox:

```bash
make create-tool
make start
```

The Tool ID and Instance ID are stored in `.tool-id` and `.instance-id`. `make start` waits for the envd data plane, then checks that the default user is `root`, the default directory is `/workspace`, and Docker Engine and Compose are ready.

You can also run a command directly:

```bash
agr --region ap-hongkong instance exec "$(cat .instance-id)" \
  --user root -- docker compose version
```

## 2. Run a real Terminal-Bench Compose task with Harbor Oracle

This example uses Harbor v0.22.0 to run the [`intrastat-meldung`](https://github.com/harbor-framework/terminal-bench/tree/v3.0.0/tasks/intrastat-meldung) task from Terminal-Bench 3.0.0 with Harbor's built-in `oracle` agent:

```bash
make harbor-oracle
```

[`run-harbor-oracle.sh`](./scripts/run-harbor-oracle.sh) uploads a runner through envd. Inside the Sandbox, the runner installs Git, Python, and `uv`, checks out only this task, and invokes:

```bash
harbor trial start \
  --path terminal-bench/tasks/intrastat-meldung \
  --agent oracle \
  --env docker
```

Harbor then manages the complete task lifecycle on the inner Docker daemon:

1. Build the task's original images and start its six-service Compose environment: `main`, `odoo`, `compliance-hub`, `idev`, `services`, and `dms`.
2. Wait for the services to become healthy, copy the task's `solution/` into `main`, and run the official Oracle solution. The Oracle makes live API calls to the five sidecars and produces the task artifacts.
3. Collect the artifacts declared in `task.toml` from `main` and `compliance-hub`.
4. Build the original `tests/Dockerfile`, run the verifier in the separate environment declared by `task.toml`, and require reward `1.0`.
5. Remove the Compose containers, network, and volumes, then write the structured trial result under `/mnt/ags-dind/harbor-oracle-intrastat-meldung-v3.0.0/trials/`.

This single run validates Harbor's native Compose startup and healthchecks, service DNS, shared volumes, cross-service artifact collection, Oracle execution, separate verifier, and resource cleanup on the AGS DinD image.

The final line on success is:

```text
Harbor Oracle validation: PASS (.../result.json)
```

On a first run, `make run` creates the Tool, starts the Sandbox, and runs this Oracle validation in one sequence.

## Cleanup

Delete the Instance and Tool created by this example:

```bash
make cleanup
```
