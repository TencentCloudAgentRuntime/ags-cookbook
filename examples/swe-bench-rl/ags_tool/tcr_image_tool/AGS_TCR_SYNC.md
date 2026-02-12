# AGS TCR Workflow

This workflow pushes dataset images to TCR, creates AGS SandboxTools from those TCR images, and then runs R2E-Gym with AGS as the runtime.

## 1) Push dataset images to TCR

```bash
# Login manually
docker login ccr.ccs.tencentyun.com --username=xxx

# Optional: prefix docker commands with sudo
export USE_SUDO=1

# Download dataset, extract images, push to TCR
python3 push_to_tcr.py --dataset R2E-Gym/R2E-Gym-Subset --registry ccr.ccs.tencentyun.com --limit 10
```

This writes a mapping file: `tcr_image_mapping.json` (src image -> TCR image).

## 2) Create AGS SandboxTools from TCR images

```bash
export TENCENTCLOUD_SECRET_ID=xxx
export TENCENTCLOUD_SECRET_KEY=xxx
export TENCENTCLOUD_ROLE_ARN=qcs::cam::uin/3321337994:roleName/tcr-full-ags
export AGS_REGION=ap-guangdong
export SANDBOX_IMAGE_REGISTRY_TYPE=personal

AGS_TOOL_DIR=/home/ubuntu/rllm-ags/ags-tool python3 ags_tool_sync.py --mapping tcr_image_mapping.json
```

This writes `tool_mapping.json` with:

- image -> tool_name -> tool_id
- image -> tcr_image

Tool names are derived from the TCR image: the last segment of the repository plus the tag, with invalid characters replaced by hyphens (only letters, numbers, underscores, and hyphens are allowed; max 50 characters). For example:

```
ccr.ccs.tencentyun.com/namanjain12/aiohttp_final:006fbe03fe...b6
-> aiohttp_f-006fbe03fede4eaa1eeba7b8393cbf4d63cb44b6
```

Each tool is tagged with:

- `image`: original image name
- `tcr_image`: TCR image name

## 3) Run R2E-Gym with AGS runtime

R2E-Gym AGS runtime resolves a tool by image name (tool_name) or by tag. If a tool is missing, it will error and tell you to run `ags_tool_sync.py` first.

Ensure `E2B_API_KEY` and `AGS_REGION` are set before running the AGS runtime.
