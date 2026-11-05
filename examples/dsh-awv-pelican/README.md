# DeepSeek Harness + AWV: pelican on a bicycle

[中文](README_zh.md)

Generate, independently review and publish an animated web page using multiple Agents. Code, Review and the display Pod sequentially mount one AWV workspace. A new Pod can continue using files left by a previous Pod, including across nodes.

This is a Kubernetes + AWV example. It uses Kubernetes Jobs and Helm directly, rather than the AGS/E2B SDK. [Architecture and limits](docs/architecture.md) explains the Provider and persistence boundary.

## Prerequisites

- A Kubernetes cluster with Ready **linux/amd64** nodes, AWV installed and a usable AWV StorageClass. AWV installation is outside this example.
- Namespace creation and application deployment permissions; permissions to perform the RBAC checks in `make verify`.
- LoadBalancer Service support for the published page. Harness Web itself uses local port forwarding.
- Local Node.js >=22, pnpm **11.19.0**, Docker with amd64 build support, kubectl, Helm 3 and jq. macOS and Linux are supported as local clients; Mac-native execution has not been verified by the historical cluster runs.
- A writable image registry reachable by cluster nodes, and an OpenAI Chat Completions-compatible model endpoint. The tested endpoint is Token Hub with `deepseek/deepseek-flash`.
- Outbound access from the Controller and Workers to the model endpoint; from builds to package registries and browser downloads.

## Setup and configuration

```bash
cd examples/dsh-awv-pelican
cp .env.example .env
make setup
```

Install pnpm 11.19.0 beforehand using your Node package-management tool. `make setup` installs locked dependencies for this example, its Provider and Worker. TypeScript tests run through `tsx` without a local compilation step. JavaScript plugin packaging happens inside the image build.

Edit `.env` with literal values. It is loaded by `dotenv`; existing process variables take precedence. Do not source it as shell code.

| Variable | Purpose |
| --- | --- |
| `KUBECONFIG` | Absolute path to the target cluster config |
| `NAMESPACE` | Dedicated demo Namespace; default `dsh-awv` |
| `REGISTRY`, `IMAGE_TAG` | Writable registry namespace and image version; no prebuilt demo images are assumed |
| `STORAGE_CLASS` | Existing AWV StorageClass; default `awv-btrfs` |
| `OPENAI_BASE_URL`, `OPENAI_API_TYPE` | Compatible model API endpoint and API type |
| `DSH_MODEL` | Main Agent model; Code/Review can override via `DSH_CODE_MODEL` / `DSH_REVIEW_MODEL` |
| `MODEL_SECRET` | Namespace-local model Secret name |
| `IMAGE_PULL_SECRET`, `DOCKER_CONFIG_FILE` | Optional private-registry Secret and Docker auth JSON path; leave both empty for public images |
| `CODE_NODE`, `REVIEW_NODE`, `SITE_NODE` | Optional distinct Ready node names for cross-node validation |
| `CONTROLLER_NODE` | Optional Controller node name |
| `OUTPUT_DIR` | Optional absolute artifact directory; defaults to ignored `.local/` |

Provide `OPENAI_API_KEY` through the process environment (for example a secret manager or a hidden terminal prompt). Do not put it in `.env`, source control, images or the workspace. The install script creates a Kubernetes Secret from it. If your Docker config uses an OS keychain credential helper, export a registry auth JSON usable by Kubernetes instead of copying that helper-only config.

## Build and run

Authenticate your Docker client to `REGISTRY`, then run:

```bash
make preflight
make build
make run
make verify
make access
```

`make build` builds and pushes **linux/amd64** Controller and Worker images, then records their digests in `.local/images.env` (or `OUTPUT_DIR`). `make run` deploys those digests, a Namespace-scoped ServiceAccount/RBAC, a model Secret and an AWV PVC. It does not submit a model task. `make access` prints recent Controller logs and forwards `http://127.0.0.1:3080`; keep it running in another terminal.

Open the login URL from the logs, including `?token=...`. Submit [the creation prompt](examples/prompts/create-pelican.md). The expected flow is:

```text
code_agent -> review_agent -> optional code_agent fix + review_agent -> publish_site
```

The final reply includes the review result and the page's LoadBalancer URL. Review failure or an Agent error must prevent publication. Generated files live in the AWV PVC `pelican-workspace`; the Controller does not mount it.

From the repository root, the shared entry points also work:

```bash
make example-setup EXAMPLE=dsh-awv-pelican
make example-run EXAMPLE=dsh-awv-pelican
```

For remote Harness Web exposure, configure its Service and `controller.trustedHosts` explicitly through Helm. The host entry excludes scheme/path. `trustedHosts` only permits Host validation; it does not provide TLS or network access control. See [architecture and limits](docs/architecture.md) before changing access. Local port forwarding is the primary path.

## Validation

```bash
make check  # Typecheck, shell syntax, Harness YAML syntax, Helm lint/render
make test   # Provider unit tests, no cluster or model calls
make e2e    # Dedicated demo only: two model-driven rounds and Pod recreation
```

E2E overwrites the demo page, injects a mobile-layout defect and calls the model. Logs, HTML snapshots and timing results stay in the ignored artifact directory. Cross-node validation requires three explicitly configured different nodes. See [validation scope](docs/validation.md) for historical evidence and the current-run checklist.

With pinned Harness `0.1.5-rc.2`, browser navigation, screenshots, DOM/layout, interactions and console checks work. Screenshot image blocks do not reach the model context, so this example does **not** demonstrate model-based screenshot recognition. AWV persists files, not processes, browser state or conversations. Controller recreation does not restore Harness sessions.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| `images.env` missing | Complete `make build` using the same `OUTPUT_DIR` before deployment |
| PVC/Job Pending | AWV StorageClass, node capacity, image pull access, node selectors and volume mount events |
| Registry pull fails on Mac-built images | Confirm the pushed image targets linux/amd64; check the pull Secret's auth JSON |
| Web loads but API returns 403 | Retain the login token and configure `controller.trustedHosts` for remote access |
| Workspace locked | Inspect running Jobs/display Pods and Lease; remove a stale Lease only after confirming no active task |
| Review fails or publication is rejected | Inspect Review `blocking_issues` and the state ConfigMap's generation/review fields |
| No published URL | Check LoadBalancer capability/quota and Service events |
| Cross-node mount is slow | Inspect old unmount and new mount events; do not force-detach an active volume |

```bash
make status
# Replace the placeholders using the values in .env:
kubectl --kubeconfig <path> -n <namespace> get events --sort-by=.lastTimestamp
kubectl --kubeconfig <path> -n <namespace> logs job/<job-name>
```

## Cleanup

```bash
make clean
```

This removes compute resources while retaining the PVC and credential Secrets. Delete the demo PVC or Namespace only after confirming its data and Secrets are no longer needed. PVC recovery after deletion depends on the StorageClass reclaim policy and backups. E2E, cleanup and model calls must use a dedicated demo environment.
