# goscripts

AGS (Agent Sandbox) 镜像预热工具，用于批量预热 TCR 镜像到 AGS 集群。

## 快速开始

### 1. 配置

复制配置文件并填写：

```bash
cp config.example.toml config.toml
```

编辑 `config.toml`，填入腾讯云密钥和 TCR 信息。

### 2. 构建

```bash
go build -o precache ./cmd/precache
```

### 3. 运行

```bash
./precache --config config.toml
```

## 配置说明

| 配置项 | 说明 |
|--------|------|
| `cmd.precache.mode` | 预热模式：`precache`（API）或 `sandboxtool`（创建工具） |
| `cmd.precache.role_arn` | CAM 角色 ARN |
| `cmd.precache.tcr_registry_id` | TCR 实例 ID |
| `cmd.precache.tcr_namespace` | TCR 命名空间 |
| `cmd.precache.tcr_image_regex` | 镜像名过滤正则（可选） |
| `cmd.precache.concurrency` | 并发数 |
| `cmd.precache.max_retries` | 最大重试次数 |
| `tencent_cloud.region` | 腾讯云地域 |
| `tencent_cloud.secret_id` | API 密钥 ID |
| `tencent_cloud.secret_key` | API 密钥 Key |

## 预热模式

- **precache**: 调用 `CreatePreCacheImageTask` API，适合大批量预热
- **sandboxtool**: 创建临时 SandboxTool 触发预热，完成后自动删除

