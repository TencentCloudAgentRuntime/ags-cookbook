# 托管 Harness 的伸缩、空闲策略与会话持久化

本教程独立创建一个 Harness：创建时通过初始化配置设置资源规格、按需启动和空闲暂停；然后配置 Session Space，删除实例后在新实例上继续同一个会话；最后用 Deployment 命令直接调整伸缩。

开始前，请完成公共[前置条件](../README_zh.md#前置条件)和[配置](../README_zh.md#配置)。伸缩与空闲参数的含义与 Deployment 完全一致，详细说明见 [Deployment 弹性伸缩](../../deployment-cookbook/httpbin/scaling/README_zh.md)和 [Deployment 生命周期](../../deployment-cookbook/httpbin/lifecycle/README_zh.md)。

## 哪些配置归谁管

| 配置 | 在哪里设置 | 之后如何修改 |
| --- | --- | --- |
| 引擎、模型、提示词、Skill、Plugin、MCP、Session Space | Harness 草稿 | `harness update` 后创建并发布修订 |
| 角色、VPC 网络 | `harness create` 的初始化配置 | 不能通过 Harness 修改 |
| 实例规格、存储挂载、日志 | `harness create` 的初始化配置 | 使用 `agr tool update` 修改底层 Tool |
| 伸缩、空闲策略、会话亲和 | `harness create` 的初始化配置 | 使用 `agr deployment update` 修改底层 Deployment |

初始化配置只在首次发布创建 Tool 和 Deployment 时使用。之后的发布只更新 Harness 管理的镜像、启动参数和受管环境变量，不会覆盖你通过 Tool 或 Deployment 命令所做的网络、挂载、伸缩等修改。

省略初始化配置时使用以下默认值：

| 字段 | 默认值 |
| --- | --- |
| `SandboxTool.CustomConfiguration.Resources` | `CPU: "2"`, `Memory: "2Gi"` |
| `Deployment.ScalingConfiguration` | `MinInstanceCount: 1`, `MaxInstanceCount: 1`, `MaxInstanceRequestConcurrency: 200` |
| `Deployment.LifecycleConfiguration` | `IdleTimeoutSeconds: 300`, `IdleAction: STOP` |
| `Deployment.AffinityConfiguration` | `Mode: BEST_EFFORT`, `HeaderName: X-Tencent-Agr-Affinity-Id` |

示例输出中的真实信息均已脱敏。

## 1. 设置环境变量并创建 Session Space

```bash
set -a
source ../.env
set +a
bash ../scripts/preflight.sh scaling-session &&

export MODEL_PROVIDER_NAME="harness-scaling-$HARNESS_NAME_SUFFIX" &&
export HARNESS_NAME="harness-scaling-$HARNESS_NAME_SUFFIX" &&
export SESSION_SPACE_NAME="harness-scaling-$HARNESS_NAME_SUFFIX"
```

Session Space 用于在云端保存会话历史。实例使用底层 Sandbox Tool 当前 `RoleArn` 换取的临时凭据访问，请确认这个运行角色具备所选 Session Space 的读写权限。初始运行角色就是创建时通过 `--role-arn` 指定的角色。

```bash
SESSION_SPACE_ID=$(python3 ../scripts/resources.py create scaling-session session-space \
  --name "$SESSION_SPACE_NAME") && export SESSION_SPACE_ID
```

SpaceId 已保存到 `SESSION_SPACE_ID` 和 `.state/scaling-session.json`。

## 2. 登记模型并创建 Harness

```bash
MODEL_PROVIDER_ID=$(python3 ../scripts/resources.py create scaling-session model-provider \
  --name "$MODEL_PROVIDER_NAME" \
  --tokenhub-api-key-id "$TOKENHUB_API_KEY_ID" \
  --model hy3) && export MODEL_PROVIDER_ID
```

把初始化配置写成文件。角色和 VPC 仍由 `--role-arn`、`--subnet-id`、`--security-group-id` 提供，CLI 会把它们合并进这个对象。下面把实例改为 1 核 2Gi，允许缩到零、最多两个实例，并在空闲 60 秒后暂停：

```bash
cat > init.json <<'EOF'
{
  "SandboxTool": {
    "CustomConfiguration": {
      "Resources": {"CPU": "1", "Memory": "2Gi"}
    }
  },
  "Deployment": {
    "ScalingConfiguration": {
      "MinInstanceCount": 0,
      "MaxInstanceCount": 2,
      "MaxInstanceRequestConcurrency": 50
    },
    "LifecycleConfiguration": {
      "IdleTimeoutSeconds": 60,
      "IdleAction": "PAUSE"
    }
  }
}
EOF
```

省略的 `AffinityConfiguration` 使用默认值。创建 Harness，同时启用 Session Space：

```bash
HARNESS_ID=$(python3 ../scripts/resources.py create scaling-session harness \
  --name "$HARNESS_NAME" \
  --engine pi \
  --engine-version 1.3.0 \
  --model "$MODEL_PROVIDER_ID:hy3" \
  --session-space-id "$SESSION_SPACE_ID" \
  --role-arn "$AGR_ROLE_ARN" \
  --subnet-id "$HARNESS_SUBNET_ID" \
  --security-group-id "$HARNESS_SECURITY_GROUP_ID" \
  --initialize-configuration @init.json \
  --wait) && export HARNESS_ID
```

脚本会保存 Harness、Tool 和 Deployment ID。查看底层资源：

```bash
agr harness get "$HARNESS_ID" --region "$AGR_REGION" -o json \
  --jq '.Data.Harness.ResourceInfo'
```

```json
{"DeploymentId":"dpl-********","ToolId":"sdt-********"}
```

```bash
HARNESS_TOOL_ID=$(python3 ../scripts/resources.py get scaling-session ToolId) && export HARNESS_TOOL_ID
HARNESS_DEPLOYMENT_ID=$(python3 ../scripts/resources.py get scaling-session DeploymentId) && export HARNESS_DEPLOYMENT_ID
```

## 3. 确认初始化配置已生效

底层 Deployment 是普通的 AGS Deployment，可以直接查询：

```bash
agr deployment get "$HARNESS_DEPLOYMENT_ID" --region "$AGR_REGION"
```

```text
Name:          hns-********-********
ID:            dpl-********
Tool:          sdt-********
Status:        ACTIVE
Tags:          <none>
Created:       <masked-time>
Scaling:
  Min Instances:                0
  Max Instances:                2
  Max Requests per Instance:    50
Lifecycle:
  Idle Action:                  PAUSE
  Idle Timeout:                 1m
Affinity:
  Mode:                         BEST_EFFORT
  Header:                       X-Tencent-Agr-Affinity-Id
```

`MinInstanceCount` 为 `0`，所以此时可能还没有实例：

```bash
agr instance list --tool-id "$HARNESS_TOOL_ID" --region "$AGR_REGION"
```

## 4. 按需启动与空闲暂停

第一次请求会触发实例启动，可能比后续请求慢一些。将本次会话的 `SessionId` 和 `AffinityId` 记下来，下一步会用到：

```bash
agr harness prompt "$HARNESS_ID" --region "$AGR_REGION" -o json \
  --jq '.Data | {AffinityId, Reply, SessionId}' \
  'Remember the code word "maple". Reply only with "OK".'
```

```json
{"AffinityId":"<masked-affinity-id>","Reply":"OK","SessionId":"<masked-session-id>"}
```

```bash
export HARNESS_SESSION_ID='replace-with-session-id'
export HARNESS_AFFINITY_ID='replace-with-affinity-id'

agr instance list --tool-id "$HARNESS_TOOL_ID" --region "$AGR_REGION"
```

列表中会出现一个 `RUNNING` 实例。停止访问至少 60 秒后再次查询，实例会进入 `PAUSED`。回收是异步的，实际时间可能略长于配置值：

```text
ID                    TOOL                   STATUS  TIMEOUT  EXPIRES  MOUNTS  CREATED
<masked-instance-id>  hns-********-********  PAUSED  0s       -        -       <masked-time>
```

带上同一个亲和值继续对话，Deployment 会恢复这个实例。暂停会保留内存和磁盘，因此即使不配置 Session Space 也能记住之前的内容：

```bash
agr harness prompt "$HARNESS_ID" --region "$AGR_REGION" \
  --session-id "$HARNESS_SESSION_ID" \
  --affinity-id "$HARNESS_AFFINITY_ID" \
  'What was the code word?'
```

回复应包含 `maple`。

## 5. 删除实例后在新实例上继续会话

删除实例会丢弃实例内的本地会话文件。开启 Session Space 后，pi 会把会话条目同步到云端，在新实例上可以通过 `session/load` 从云端还原。

删除之前，先确认对话已经写入云端。托管 Harness 固定使用 Harness ID 作为会话的 UserId：

```bash
agr session list --region "$AGR_REGION" --space-id "$SESSION_SPACE_ID" --user-ids "$HARNESS_ID"
agr session event list --region "$AGR_REGION" --space-id "$SESSION_SPACE_ID" \
  --user-id "$HARNESS_ID" --session-id "$HARNESS_SESSION_ID"
```

确认事件中包含带有 `maple` 的消息。prompt 成功不代表云端同步成功；如果还没有历史，先等待并检查运行角色对 Session Space 的权限，再删除实例。

找到并删除当前实例：

```bash
agr instance list --tool-id "$HARNESS_TOOL_ID" --region "$AGR_REGION"
export HARNESS_INSTANCE_ID='replace-with-instance-id'
agr instance delete "$HARNESS_INSTANCE_ID" --region "$AGR_REGION" --yes --wait
```

再次检查端点，让 Deployment 启动替代实例。如果检查返回 `ACP_UNAVAILABLE`，稍等后重复执行：

```bash
agr harness endpoint "$HARNESS_ID" --region "$AGR_REGION" --check
```

旧的亲和值指向已删除的实例，因此这次**不带** `--affinity-id`，只带 `--session-id`。替代实例会从 Session Space 加载同一个会话：

```bash
agr harness prompt "$HARNESS_ID" --region "$AGR_REGION" \
  --session-id "$HARNESS_SESSION_ID" \
  'What was the code word?'
```

回复仍应包含 `maple`。删除后立即恢复，可能短暂返回 `SESSION_RESTORE_FAILED` 和 HTTP `404`，提示沙箱实例已删除。如果云端历史已存在，稍等后重新检查端点，再用相同的 SessionId 和 cwd 重试上述恢复命令，不带旧的亲和值。

使用 Session Space 时需要注意：

- 同一个 Harness 的所有会话共用一个 UserId，不区分你应用里的聊天用户。应用需要记录每个 SessionId 的归属，并校验访问权限。
- 同一个会话同一时刻应只有一个写入进程。应用应按 SessionId 串行发送请求，会话持久化不负责协调并发写入。不要让两个实例同时对同一个 SessionId 发起对话。
- 只恢复对话历史，不迁移实例内的工作区文件。恢复时需要使用与创建会话时相同的 `--cwd`（默认 `/workspace`）。
- 只支持 `pi` 和 `dsh` 引擎。移除 Session Space 使用 `agr harness update <harness-id> --session-space-id ''`，然后发布新修订。

实现细节见 [Session Cookbook](../../session-cookbook/README_zh.md)。

## 6. 直接调整底层 Deployment

初始化配置不能通过 Harness 修改，但可以直接调整底层 Deployment。下面把最小实例数改为 1，保持一个常驻实例以消除冷启动延迟。`--scaling-configuration` 会完整替换伸缩对象，因此必须提供全部三个字段：

```bash
agr deployment update "$HARNESS_DEPLOYMENT_ID" \
  --region "$AGR_REGION" \
  --scaling-configuration '{
    "MinInstanceCount": 1,
    "MaxInstanceCount": 2,
    "MaxInstanceRequestConcurrency": 50
  }'

agr deployment get "$HARNESS_DEPLOYMENT_ID" --region "$AGR_REGION"
```

```text
Scaling:
  Min Instances:                1
  Max Instances:                2
  Max Requests per Instance:    50
```

之后发布新的 Harness 修订不会覆盖这个修改。可以自己验证：

```bash
agr harness update "$HARNESS_ID" --region "$AGR_REGION" --system-prompt 'You are a helpful assistant.'
agr harness revision create "$HARNESS_ID" --region "$AGR_REGION" --publish --wait
agr deployment get "$HARNESS_DEPLOYMENT_ID" --region "$AGR_REGION"
```

`Min Instances` 仍为 `1`。

不要用 `agr tool update` 修改 Harness 管理的镜像、启动参数或平台保留的环境变量，下一次发布会把它们恢复为修订中的配置。你自己添加的环境变量会被保留。

## 7. 清理资源

删除本场景保存的资源。脚本从 `.state/` 读取 ID、地域和 endpoint，等待删除完成并回查结果；清理中断后可以重复执行。它也会删除该 Harness 的会话和本教程创建的 Session Space。

```bash
python3 ../scripts/resources.py cleanup scaling-session --yes
rm -f init.json
```

## 常见问题

| 现象 | 原因与处理 |
| --- | --- |
| 初始化配置报 `ROLE_ARN_CONFLICT` 或 `NETWORK_CONFLICT` | `init.json` 中的角色或网络与命令行参数不一致。只在一处设置 |
| 初始化配置报 `INVALID_NETWORK_MODE` | 托管 Harness 只支持 VPC。删除 `init.json` 中的 `NetworkMode` 或改为 `VPC` |
| 第一次 prompt 很慢或返回 `ACP_UNAVAILABLE` | `MinInstanceCount` 为 `0`，需要先启动实例。稍后重试，或按第 6 步保持一个常驻实例。如果持续启动失败，按 [simple](../simple/README_zh.md#常见问题) 查询 Tool 事件 |
| 删除实例后新实例记不住之前的内容 | 检查底层 Tool 当前 `RoleArn` 的 Session Space 权限，使用与创建会话时相同的 `--cwd`，并在删除实例前用 `agr session event list` 确认云端历史 |
| 删除后立即恢复返回 `SESSION_RESTORE_FAILED` 和 HTTP `404` | 等待请求不再命中已删除的实例，重新执行 `endpoint --check`，再用相同的 SessionId 和 cwd 重试，不带旧的亲和值 |
| `session space delete` 失败 | Space 中还有会话。先删除全部会话 |
