# AGS TCR 工作流程

该工作流程将数据集镜像推送到 TCR，从这些 TCR 镜像创建 AGS SandboxTools，然后使用 AGS 作为运行时运行 R2E-Gym。

## 1) 将数据集镜像推送到 TCR

```bash
# 手动登录
docker login ccr.ccs.tencentyun.com --username=xxx

# 可选：在 docker 命令前添加 sudo
export USE_SUDO=1

# 下载数据集、解析镜像、推送到tcr
python3 push_to_tcr.py --dataset R2E-Gym/R2E-Gym-Subset --registry ccr.ccs.tencentyun.com --limit 10
```

这将写入一个映射文件：`tcr_image_mapping.json`（源镜像 -> TCR 镜像）。

## 2) 从 TCR 镜像创建 AGS SandboxTools

```bash
export TENCENTCLOUD_SECRET_ID=xxx
export TENCENTCLOUD_SECRET_KEY=xxx
export TENCENTCLOUD_ROLE_ARN=qcs::cam::uin/3321337994:roleName/tcr-full-ags
export AGS_REGION=ap-guangdong
export SANDBOX_IMAGE_REGISTRY_TYPE=personal

AGS_TOOL_DIR=/home/ubuntu/rllm-ags/ags-tool python3 ags_tool_sync.py --mapping tcr_image_mapping.json
```

这将写入 `tool_mapping.json`，包含：

- image -> tool_name -> tool_id
- image -> tcr_image

工具名称由 TCR 镜像生成：取仓库最后一段加上 tag，将非法字符替换为连字符（仅允许字母、数字、下划线和连字符；最长 50 个字符）。例如：

```
ccr.ccs.tencentyun.com/namanjain12/aiohttp_final:006fbe03fe...b6
-> aiohttp_f-006fbe03fede4eaa1eeba7b8393cbf4d63cb44b6
```

每个工具都带有以下标签：

- `image`：原始镜像名称
- `tcr_image`：TCR 镜像名称

## 3) 使用 AGS 运行时运行 R2E-Gym

R2E-Gym AGS 运行时通过镜像名称（tool_name）或标签解析工具。如果缺少工具，将报错并提示您先运行 `ags_tool_sync.py`。

在运行 AGS 运行时之前，请确保设置了 `E2B_API_KEY` 和 `AGS_REGION`。
