# deploy-custom-image

One-click workflow to deploy any existing Docker image as a custom AGS sandbox tool: pull → build thin wrapper (inject envd) → push to Tencent Cloud CCR → create or update the AGS sandbox tool via the control-plane API.

## Prerequisites

- Python >= 3.11
- `podman` or `docker` CLI, logged in to the target CCR registry
- A Tencent Cloud CAM role that allows AGS to pull from the target registry
- `TENCENTCLOUD_SECRET_ID` / `TENCENTCLOUD_SECRET_KEY`

## Local commands

```bash
make setup
make run
```

## Important environment variables

| Variable | Required | Description |
|---|---|---|
| `SOURCE_IMAGE` | yes | Docker image to deploy (e.g. `nginx:latest`, `ccr.ccs.tencentyun.com/ns/img:tag`) |
| `TENCENTCLOUD_REGISTRY` | yes | Full target image path in CCR (e.g. `ccr.ccs.tencentyun.com/ns/my-image`) |
| `TENCENTCLOUD_SECRET_ID` | yes | Tencent Cloud API credential |
| `TENCENTCLOUD_SECRET_KEY` | yes | Tencent Cloud API credential |
| `TENCENTCLOUD_REGION` | yes | Region (e.g. `ap-guangzhou`) |
| `AGS_API_KEY` | yes | AGS API key for sandbox instances |
| `AGS_DOMAIN` | yes | AGS endpoint domain |
| `TOOL_NAME` | yes | Name for the sandbox tool to create/update |
| `TOOL_CPU` | yes | CPU cores (e.g. `4`) |
| `TOOL_MEMORY` | yes | Memory (e.g. `8Gi`) |
| `ROLE_ARN` | yes | CAM role ARN with CCR pull permission |

## How it works

```
SOURCE_IMAGE (any registry)
        │
        ▼
┌───────────────────┐     podman/docker      ┌──────────────────────────┐
│  Dockerfile       │ ──────────────────────▶ │  TENCENTCLOUD_REGISTRY   │
│  (inject envd)    │     build + push        │  (full image path)       │
└───────────────────┘                         └──────────────────────────┘
                                                       │
                              TencentCloud SDK         │
                              CreateSandboxTool /      │
                              UpdateSandboxTool        ▼
                                              ┌─────────────────────┐
                                              │  AGS Sandbox Tool   │
                                              │  (ready to start)   │
                                              └─────────────────────┘
```

The `Dockerfile` uses a multi-stage `COPY --from` to inject the `envd` binary from the official `ccr.ccs.tencentyun.com/ags-image/envd:latest` image into the source image. No other modifications are made to the original image.

## Expected result

A successful run should:

1. Build a thin wrapper image (source image + envd) and push it to CCR with `:latest` and `:<hash>` tags
2. Create (or update) an AGS sandbox tool pointing to the pushed image
3. Print the tool name and SDK usage examples for creating sandbox instances

## Common failure hints

- If `podman push` fails with auth errors, re-run `podman login ccr.ccs.tencentyun.com`
- If the control plane rejects the role ARN, verify the CAM role trusts the AGS service and has TCR/CCR pull permissions
- If `UpdateSandboxTool` fails, ensure the tool was initially created by the same account
