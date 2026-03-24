# deploy-custom-image

一键将现有 Docker 镜像部署为 AGS 自定义沙箱工具：拉取镜像 → 构建薄包装（注入 envd）→ 推送到腾讯云 CCR → 通过控制面 API 创建或更新沙箱工具。

## 前置条件

- Python >= 3.11
- `podman` 或 `docker` CLI，已登录目标 CCR 仓库
- 一个允许 AGS 从目标仓库拉取镜像的 CAM 角色
- `TENCENTCLOUD_SECRET_ID` / `TENCENTCLOUD_SECRET_KEY`

## 快速开始

```bash
make setup
make run
```

## 环境变量

| 变量 | 必填 | 说明 |
|---|---|---|
| `SOURCE_IMAGE` | 是 | 要部署的 Docker 镜像（如 `nginx:latest`） |
| `TENCENTCLOUD_REGISTRY` | 是 | CCR 完整镜像路径（如 `ccr.ccs.tencentyun.com/ns/my-image`） |
| `TENCENTCLOUD_SECRET_ID` | 是 | 腾讯云 API 凭据 |
| `TENCENTCLOUD_SECRET_KEY` | 是 | 腾讯云 API 凭据 |
| `TENCENTCLOUD_REGION` | 是 | 地域（如 `ap-guangzhou`） |
| `AGS_API_KEY` | 是 | AGS API Key |
| `AGS_DOMAIN` | 是 | AGS 端点域名 |
| `TOOL_NAME` | 是 | 要创建/更新的沙箱工具名称 |
| `TOOL_CPU` | 是 | CPU 核数（如 `4`） |
| `TOOL_MEMORY` | 是 | 内存（如 `8Gi`） |
| `ROLE_ARN` | 是 | 有 CCR 拉取权限的 CAM 角色 ARN |

## 工作原理

`Dockerfile` 通过多阶段构建，从官方 `ccr.ccs.tencentyun.com/ags-image/envd:latest` 镜像中提取 `envd` 二进制并注入到源镜像中，不做任何其他修改。

## 预期结果

1. 构建薄包装镜像（源镜像 + envd）并推送到 CCR（`:latest` 和 `:<hash>` 两个标签）
2. 创建（或更新）指向该镜像的 AGS 沙箱工具
3. 输出工具名称和创建沙箱实例的 SDK 使用示例

输出的使用示例需要 [e2b AGS SDK](https://pypi.org/project/e2b-code-interpreter/)，按需安装：`pip install e2b-code-interpreter`。
