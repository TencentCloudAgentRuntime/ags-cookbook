# 在 AGS 上运行无状态 DeepSeek Harness Brain 与持久 Hands

[English](./README.md) | 中文

本示例把推理与命令执行拆开：

```text
客户端 -> AGS Brain Deployment（2 个以上可互换副本）
                      |  DSH session log、workspace 绑定、turn lease
                      v
                   MySQL 8
                      |
                      |  E2B 2.29.1 协议、envd :49983、affinity header
                      v
           AGS Hands Deployment（EXCLUSIVE + PAUSE）
                      |
                      v
               持久保留的 /workspace
```

Brain 包含 DeepSeek Harness（DSH）、TokenHub 模型 adapter 和 HTTP API，本地磁盘不保存权威 session 或 workspace 状态。Hands 只包含 `envd` 与常用命令行工具，不包含 DSH、MySQL client、SQLite、COS SDK 或 COS mount。Hands `PAUSE` 后由 AGS 保留 `/workspace`，恢复时继续使用原目录。

这是一个单用户 cookbook，不是公网多租户服务。`BRAIN_WORKSPACE_USER_ID` 由部署者配置，HTTP 客户端不能覆盖。Brain Deployment 应由 AGS Deployment-token 网关保护；Brain 进程本身不实现终端用户认证。

## 持久化契约

| 关注点 | 契约 |
| --- | --- |
| DSH session | 通过 `SessionPersistence` 以 MySQL 为权威来源；每个 turn 都 resume Agent，完成后 flush 并 dispose。 |
| Workspace | MySQL 把服务端身份映射到一个不透明的 AGS affinity ID；Brain API 永不返回 affinity。 |
| 并发 turn | 每个 session 只有一个 MySQL lease；第二个请求返回 `409 SESSION_BUSY`，不排队。 |
| 旧 Brain 副本 | 每次 DSH append 都在同一 MySQL 事务内锁定并校验 turn generation；每次新 Hands 操作还会校验 lease 与 `/workspace/.ags` 中的单调 generation。 |
| 分配结果不确定 | `PENDING` 绑定 fail closed；必须显式恢复，不会静默创建第二个 workspace。 |
| Hands 数据 | `/workspace` 由 AGS Hands Sandbox 保留，不需要 COS mount。 |

## 前置条件

- `agr` v0.6.6 或更高版本、`pnpm` 11.19.0，以及 Podman 或 Docker。
- CCR 仓库，以及允许 AGS 拉取两个镜像的 CAM role。
- 名为 `dsh-cookbook` 的 MySQL 8 数据库；所有 Brain 副本必须能用同一组凭证连接它。
- 可为 Hands Deployment 调用 [`AcquireDeploymentToken`](https://cloud.tencent.com/document/api/1814/136842) 的腾讯云凭证。
- 可调用 `deepseek-v4-flash` 的腾讯云 TokenHub API Key。

本参考配置按需求使用普通非 TLS MySQL 连接。请把数据库账号权限限制在 `dsh-cookbook`，并限制网络暴露范围。TLS 配置不属于本示例范围。

## 1. 准备并验证 MySQL

只需创建一次数据库：

```sql
CREATE DATABASE `dsh-cookbook`
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
```

复制环境变量模板并在本地填入真实值：

```bash
cp .env.example .env
pnpm install --frozen-lockfile
pnpm migrate
pnpm test:mysql
```

Brain 启动时也会在 MySQL advisory lock 下执行带 checksum 的迁移。checksum 不一致或获取迁移锁超时都会让 `/readyz` 保持不可用。

## 2. 构建并发布两个镜像

```bash
make build

export CCR_REGISTRY='ccr.ccs.tencentyun.com/replace-me'
export BRAIN_IMAGE="$CCR_REGISTRY/dsh-brain:0.1.0"
export HANDS_IMAGE="$CCR_REGISTRY/dsh-hands:0.1.0"

podman tag ags-cookbook/dsh-brain:local "$BRAIN_IMAGE"
podman tag ags-cookbook/dsh-hands:local "$HANDS_IMAGE"
podman push "$BRAIN_IMAGE"
podman push "$HANDS_IMAGE"
```

源码 pin 与可复现检查见 [dockerfiles](./dockerfiles/README_zh.md)。个人版 CCR Tool 的镜像引用必须使用 `tag@sha256:digest`；只写 digest 会被平台拒绝。

## 3. 创建持久 Hands Deployment

设置名称与镜像拉取 role：

```bash
export AGR_REGION=ap-shanghai
export AGR_ROLE_ARN='qcs::cam::uin/100000000001:roleName/replace-me'
export HANDS_TOOL_NAME='dsh-hands-your-name'
export HANDS_DEPLOYMENT_NAME='dsh-hands-your-name'
```

创建 Tool。Hands 不需要数据库或对象存储环境变量。

```bash
agr tool create \
  --region "$AGR_REGION" \
  --tool-name "$HANDS_TOOL_NAME" \
  --tool-type custom \
  --persistent \
  --role-arn "$AGR_ROLE_ARN" \
  --network-configuration '{"NetworkMode":"PUBLIC"}' \
  --custom-configuration '{
    "Image": "replace-with-hands-image-tag@sha256:digest",
    "ImageRegistryType": "personal",
    "Command": ["/usr/bin/envd"],
    "Args": ["-port", "49983"],
    "Ports": [{"Name":"envd","Port":49983,"Protocol":"TCP"}],
    "Resources": {"CPU":"2000m","Memory":"4Gi"},
    "Probe": {
      "HttpGet": {"Path":"/health","Port":49983,"Scheme":"HTTP"},
      "ReadyTimeoutMs":30000,
      "ProbeTimeoutMs":3000,
      "ProbePeriodMs":5000,
      "SuccessThreshold":1,
      "FailureThreshold":6
    }
  }' \
  --wait
```

复制 Tool ID，再创建独占 affinity、空闲暂停的 Deployment：

```bash
export HANDS_TOOL_ID='sdt-replace-me'

agr deployment create \
  --region "$AGR_REGION" \
  --deployment-name "$HANDS_DEPLOYMENT_NAME" \
  --tool-id "$HANDS_TOOL_ID" \
  --scaling-configuration '{
    "MinInstanceCount":0,
    "MaxInstanceCount":20,
    "MaxInstanceRequestConcurrency":200
  }' \
  --lifecycle-configuration '{
    "IdleTimeoutSeconds":300,
    "IdleAction":"PAUSE"
  }' \
  --affinity-configuration '{
    "Mode":"EXCLUSIVE",
    "HeaderName":"X-Tencent-Agr-Affinity-Id"
  }'

export HANDS_DEPLOYMENT_ID='dpl-replace-me'
```

`MaxInstanceCount` 同时限制并发活跃的独占 workspace 数量，应按活跃用户或 session 数配置。`MaxInstanceRequestConcurrency` 表示同一个独占 workspace 内的 HTTP/RPC 请求容量；E2B 会连续调用 Files 与 Commands 接口，因此不能把它降到 1。单写由 MySQL turn lease 保证，不依赖这个请求容量字段。

## 4. 创建无状态 Brain Deployment

Brain 需要 `.env.example` 中列出的变量。平台侧的关键条件只有一个：每个 Brain 副本都能连接同一个 MySQL endpoint。请通过部署环境的 secret 流程注入密钥，不要提交 `.env`，也不要把真实凭证粘贴进仓库。

下面的命令给出完整 Tool 形状。所有 `replace-me` 都是占位符；真实密码和密钥应通过平台的 secret 注入流程提供，不要留在 shell history 中。

```bash
export BRAIN_TOOL_NAME='dsh-brain-your-name'

agr tool create \
  --region "$AGR_REGION" \
  --tool-name "$BRAIN_TOOL_NAME" \
  --tool-type custom \
  --persistent \
  --role-arn "$AGR_ROLE_ARN" \
  --network-configuration '{"NetworkMode":"PUBLIC"}' \
  --custom-configuration '{
    "Image":"replace-with-brain-image-tag@sha256:digest",
    "ImageRegistryType":"personal",
    "Command":["node","/app/dist/brain/server.js"],
    "Env":[
      {"Name":"MYSQL_HOST","Value":"replace-me"},
      {"Name":"MYSQL_PORT","Value":"3306"},
      {"Name":"MYSQL_USER","Value":"replace-me"},
      {"Name":"MYSQL_PASSWORD","Value":"replace-me"},
      {"Name":"MYSQL_DATABASE","Value":"dsh-cookbook"},
      {"Name":"BRAIN_WORKSPACE_USER_ID","Value":"replace-me"},
      {"Name":"AGS_REGION","Value":"ap-shanghai"},
      {"Name":"HANDS_DEPLOYMENT_ID","Value":"dpl-replace-me"},
      {"Name":"TENCENTCLOUD_SECRET_ID","Value":"replace-me"},
      {"Name":"TENCENTCLOUD_SECRET_KEY","Value":"replace-me"},
      {"Name":"TOKENHUB_API_KEY","Value":"replace-me"}
    ],
    "Ports":[{"Name":"http","Port":8080,"Protocol":"TCP"}],
    "Resources":{"CPU":"2000m","Memory":"4Gi"},
    "Probe":{
      "HttpGet":{"Path":"/readyz","Port":8080,"Scheme":"HTTP"},
      "ReadyTimeoutMs":30000,
      "ProbeTimeoutMs":3000,
      "ProbePeriodMs":5000,
      "SuccessThreshold":1,
      "FailureThreshold":12
    }
  }' \
  --wait
```

AGS 要求关联 Deployment 的 Tool 标记为 `persistent`。这个能力标志不会让 Brain 变成有状态服务：Brain Tool 没有 storage mount，Deployment 使用 `STOP`，所有权威状态仍在 MySQL。Brain 进程以非特权 `node` 用户运行。

然后创建无 affinity 的多副本 Deployment：

```bash
export BRAIN_TOOL_ID='sdt-replace-me'
export BRAIN_DEPLOYMENT_NAME='dsh-brain-your-name'

agr deployment create \
  --region "$AGR_REGION" \
  --deployment-name "$BRAIN_DEPLOYMENT_NAME" \
  --tool-id "$BRAIN_TOOL_ID" \
  --scaling-configuration '{
    "MinInstanceCount":2,
    "MaxInstanceCount":4,
    "MaxInstanceRequestConcurrency":20
  }' \
  --lifecycle-configuration '{
    "IdleTimeoutSeconds":300,
    "IdleAction":"STOP"
  }'

export BRAIN_DEPLOYMENT_ID='dpl-replace-me'
```

不要给 Brain 配置 session affinity。MySQL 保存 session log、binding、migration journal 和 turn lease，因此任意副本都能处理任意请求。

## 5. 调用 API

本地调试时代理 Brain Deployment：

```bash
agr deployment proxy "$BRAIN_DEPLOYMENT_ID" 18080:8080 --region "$AGR_REGION"
```

创建 session。`user` 模式让当前 cookbook 用户的多个 session 共享一个 Hands workspace；`session` 模式为每个 DSH session 分配独立 Hands workspace。

```bash
curl --fail-with-body --silent --show-error \
  --request POST \
  --header 'content-type: application/json' \
  --data '{"workspaceMode":"user"}' \
  http://127.0.0.1:18080/v1/sessions
```

复制返回的 `sessionId`，再发送一个 turn：

```bash
export DSH_SESSION_ID='replace-with-session-id'

curl --fail-with-body --silent --show-error \
  --request POST \
  --header 'content-type: application/json' \
  --data '{"message":"Create /workspace/hello.txt containing hello from Hands, then read it back."}' \
  "http://127.0.0.1:18080/v1/sessions/$DSH_SESSION_ID/turns"
```

响应包含最终的 DSH assistant content，不会包含 Hands affinity ID 或 Deployment token。

如果创建 session 返回 `WORKSPACE_RECOVERY_REQUIRED`，Brain 不会自动分配第二个 workspace。确认可以重试后，使用返回的 session ID 做显式恢复：

```bash
curl --fail-with-body --silent --show-error \
  --request POST \
  "http://127.0.0.1:18080/v1/sessions/$DSH_SESSION_ID/recover"
```

## 失败语义

| API 结果 | 含义 | 操作 |
| --- | --- | --- |
| `409 SESSION_BUSY` | 另一个 Brain 持有未过期 turn lease。 | 不要并发重试；等待原请求结束或 lease 过期。 |
| `409 WORKSPACE_RECOVERY_REQUIRED` | 之前的 workspace 分配处于 `PENDING` 或 `FAILED`。 | 先调查，再显式恢复。 |
| `503 WORKSPACE_RECOVERY_REQUIRED` | 分配或原子发布未完成。 | 把结果视为不确定；确认后再显式恢复。 |
| `500 INTERNAL` | Brain 未完成 turn 边界。 | claim 过期后，下次 DSH resume 会记录 interrupted tail，不会重放 tool call。 |

lease 过期时，已经运行的 Hands 命令无法撤销。fencing 会阻止旧 Brain 启动后续操作或提交后续 DSH event。

## 清理

先删除 Brain，避免继续创建 Hands session，再删除 Hands：

```bash
agr deployment delete "$BRAIN_DEPLOYMENT_ID" --region "$AGR_REGION" --wait
agr tool delete "$BRAIN_TOOL_ID" --region "$AGR_REGION" --yes --wait
agr deployment delete "$HANDS_DEPLOYMENT_ID" --region "$AGR_REGION" --wait
agr tool delete "$HANDS_TOOL_ID" --region "$AGR_REGION" --yes --wait
```

只有确认没有其他 Brain Deployment 使用时，才能删除 `dsh-cookbook`。

## 范围限制

本示例不提供公网用户认证、租户隔离、浏览器 UI、跨地域容灾、备份自动化或 SLO。它只演示 Brain/Hands 的状态边界，不是通用 Agent 平台。
