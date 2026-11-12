# 使用 `agr` 创建托管 Harness：最短完整链路

本教程登记一个 TokenHub 模型，创建一个使用 `pi` 引擎的托管 Harness 并等待修订 1 发布，确认 ACP 入口可用后对话一次，最后删除全部资源。变更与回滚、接入方式、伸缩与会话持久化由相邻教程独立讲解。

开始前，请完成 [Managed Harness Cookbook 公共前置条件](../README_zh.md#前置条件)。

所有命令都直接在终端执行。请从输出中复制资源 ID，并在下一步设置环境变量。示例输出中的账号、资源 ID、时间和请求 ID 均已脱敏。

## 1. 设置环境变量

把角色 ARN、子网、安全组、ApiKeyId 和资源名称替换为自己的值。名称只能包含小写字母、数字、`-` 和 `.`，后缀应保持唯一。

```bash
export AGR_REGION=ap-chongqing
export AGR_ROLE_ARN='qcs::cam::uin/100000000001:roleName/replace-me'
export HARNESS_SUBNET_ID='subnet-replace-me'
export HARNESS_SECURITY_GROUP_ID='sg-replace-me'
export TOKENHUB_API_KEY_ID='ak-replace-me'
export MODEL_PROVIDER_NAME='harness-simple-your-name'
export HARNESS_NAME='harness-simple-your-name'

agr status
```

预期输出格式如下。本教程的每条命令都显式传入 `--region`，因此这里的默认地域不影响结果：

```text
Region:       <local-default-region>
Domain:       tencentags.com
Output:       text
Config file:  <masked>/.agr/config.toml
Config load:  true

Auth:
  Secret ID:  configured (source: <masked>)
  Secret Key: configured (source: <masked>)
  Token:      not configured
```

## 2. 查看可用的引擎

Harness Engine 是平台提供的 Agent 运行时。创建 Harness 时必须指定当前地域提供的引擎和版本。

```bash
agr harness engine list --region "$AGR_REGION"
```

预期输出格式如下，实际版本以当前地域为准：

```text
ENGINE  VERSIONS
dsh     0.2.1-rc.2
pi      1.3.0
```

本教程使用 `pi`：

```bash
export HARNESS_ENGINE=pi
export HARNESS_ENGINE_VERSION=1.3.0
```

## 3. 登记模型连接

Model Provider 记录一个模型服务来源和登记的模型。`--model hy3` 按纯文本模型登记；能识图的模型写成 `--model <id>:TEXT,IMAGE`。

```bash
agr model-provider create \
  --region "$AGR_REGION" \
  --name "$MODEL_PROVIDER_NAME" \
  --tokenhub-api-key-id "$TOKENHUB_API_KEY_ID" \
  --model hy3
```

成功输出包含真实 Model Provider ID：

```text
Model provider:  mp-********
Name:            harness-simple-****
Source:          TokenHub (ApiKeyId ak-********)
Models:          hy3[TEXT]
Tags:            -
Updated:         <masked-time>
Next: agr harness create --model mp-********:<model-id> ...
```

复制 `Model provider` 后设置环境变量：

```bash
export MODEL_PROVIDER_ID='mp-replace-me'
```

## 4. 创建 Harness 并等待修订 1 发布

`harness create` 保存草稿、创建修订 1，并异步发布：平台先创建 Sandbox Tool，再创建 Deployment。`--wait` 会一直等到修订 1 变成 `PUBLISHED` 或 `PUBLISH_FAILED`，通常需要几分钟。

`--model <provider-id>:<model-id>` 选择模型；只选一个模型时它就是默认模型。角色、子网和安全组在创建后不能修改。

先用 `--dry-run` 查看将要发送的请求，这一步不会创建任何资源：

```bash
agr harness create \
  --region "$AGR_REGION" \
  --name "$HARNESS_NAME" \
  --engine "$HARNESS_ENGINE" \
  --engine-version "$HARNESS_ENGINE_VERSION" \
  --model "$MODEL_PROVIDER_ID:hy3" \
  --system-prompt 'You are a concise assistant. Answer in one short paragraph.' \
  --role-arn "$AGR_ROLE_ARN" \
  --subnet-id "$HARNESS_SUBNET_ID" \
  --security-group-id "$HARNESS_SECURITY_GROUP_ID" \
  --dry-run -o json
```

输出中的 `Data.Request` 就是最终请求，可以看到快捷参数被展开成什么：

```json
{
  "Data": {
    "Action": "CreateHarness",
    "DryRun": true,
    "Request": {
      "HarnessName": "harness-simple-****",
      "HarnessEngine": "pi",
      "HarnessEngineVersion": "1.3.0",
      "SystemPrompt": "You are a concise assistant. Answer in one short paragraph.",
      "ModelProviders": [{"ModelProviderId": "mp-********", "Models": ["hy3"]}],
      "DefaultModel": {"ModelProviderId": "mp-********", "Model": "hy3"},
      "InitializeConfiguration": {
        "SandboxTool": {
          "RoleArn": "qcs::cam::uin/************:roleName/****",
          "NetworkConfiguration": {
            "NetworkMode": "VPC",
            "VpcConfig": {"SubnetIds": ["subnet-********"], "SecurityGroupIds": ["sg-********"]}
          }
        }
      }
    }
  }
}
```

去掉 `--dry-run -o json`，加上 `--wait` 正式创建：

```bash
agr harness create \
  --region "$AGR_REGION" \
  --name "$HARNESS_NAME" \
  --engine "$HARNESS_ENGINE" \
  --engine-version "$HARNESS_ENGINE_VERSION" \
  --model "$MODEL_PROVIDER_ID:hy3" \
  --system-prompt 'You are a concise assistant. Answer in one short paragraph.' \
  --role-arn "$AGR_ROLE_ARN" \
  --subnet-id "$HARNESS_SUBNET_ID" \
  --security-group-id "$HARNESS_SECURITY_GROUP_ID" \
  --wait
```

成功输出包含真实 Harness ID 和修订 1 的最终状态：

```text
Harness:        hns-********
Name:           harness-simple-****
Status:         ACTIVE
Engine:         pi@1.3.0
Models:         mp-********:hy3 (default)
System prompt:  You are a concise assistant. Answer in one short paragraph.
Skills:         -
Plugins:        -
MCP servers:    -
Sandbox tool:   -
Deployment:     -
Tags:           -
Updated:        <masked-time>

Revision 1 is PUBLISHED.
Next: agr harness endpoint hns-******** --check
```

上半部分打印的是创建请求返回的 Harness 记录，当时还没有开始发布，所以 `Sandbox tool` 和 `Deployment` 是 `-`；下方的 `Revision 1 is PUBLISHED.` 是等待结束时的结果。复制 `Harness` 后查看当前状态：

```bash
export HARNESS_ID='hns-replace-me'

agr harness status "$HARNESS_ID" --region "$AGR_REGION"
```

```text
Harness:    hns-******** (harness-simple-****)  ACTIVE
Live:       revision 1 (v1)  PUBLISHED  pi@1.3.0
Draft:      same as live revision
Resources:  tool=sdt-******** deployment=dpl-********
```

如果 `--wait` 返回 `WAIT_FAILED`，修订进入了 `PUBLISH_FAILED`。读取失败原因：

```bash
agr harness revision get "$HARNESS_ID" 1 --region "$AGR_REGION"
```

`Status reason` 一行说明失败在哪一步。修正原因（例如角色权限或子网）后，对同一个修订重试：

```bash
agr harness revision publish "$HARNESS_ID" 1 --region "$AGR_REGION" --wait
```

## 5. 检查 ACP 入口

`PUBLISHED` 只表示平台资源已就绪，不表示实例已经能对话。`--check` 会获取一个短期 Token，并向 ACP 入口发送一次 `initialize`：

```bash
agr harness endpoint "$HARNESS_ID" --region "$AGR_REGION" --check
```

预期输出格式如下：

```text
ACP URL:      https://8080-dpl-********.ap-chongqing.agents.tencentags.com/acp
Transport:    ACP Streamable HTTP
Auth header:  X-Access-Token   (add --show-token to issue one)
Affinity:     X-Tencent-Agr-Affinity-Id   (echo the value returned in responses)
Deployment:   dpl-********
Check:        reachable in <masked>ms
Local proxy:  agr harness proxy hns-********
```

首次检查可能要等实例启动。如果返回 `ACP_UNAVAILABLE`，等待一会儿再重试。

## 6. 对话一次

`prompt` 建立一个 ACP 会话，发送一轮问题，并把回复流式打印到终端。工具调用以 `⋯` 开头的进度行显示在 stderr。

```bash
agr harness prompt "$HARNESS_ID" --region "$AGR_REGION" \
  'What is an AI agent harness? Reply in two sentences.'
```

预期输出格式如下，实际回复会不同：

```text
An agent harness is the runtime around a language model that gives it tools, memory and a loop ...

[end_turn] session <masked-session-id> affinity <masked-affinity-id>
```

最后一行的 session 和 affinity 用于续接对话，用法见 [connect](../connect/README_zh.md)。

## 7. 清理资源

`harness delete` 删除 Deployment 和 Harness 记录，但**保留 Sandbox Tool 和 Model Provider**。先记下 Tool ID：

```bash
agr harness get "$HARNESS_ID" --region "$AGR_REGION" -o json --jq '.Data.Harness.ResourceInfo.ToolId'
```

```bash
export HARNESS_TOOL_ID='sdt-replace-me'

agr harness delete "$HARNESS_ID" --region "$AGR_REGION" --yes --wait
```

预期输出：

```text
Harness hns-******** deleted.
Kept: the Sandbox Tool, model providers, session spaces, Registry assets and credentials.
Next: agr tool delete sdt-********   # only if the Sandbox Tool is no longer needed
```

删除该 Tool 下仍在运行或暂停的实例：

```bash
agr instance list --tool-id "$HARNESS_TOOL_ID" --region "$AGR_REGION"
```

复制每个当前处于 `RUNNING` 或 `PAUSED` 状态的实例 ID，并逐个执行删除命令：

```bash
export HARNESS_INSTANCE_ID='replace-with-instance-id'
agr instance delete "$HARNESS_INSTANCE_ID" --region "$AGR_REGION" --yes --wait
```

删除 Tool 和 Model Provider。Model Provider 只有在没有任何 Harness 引用时才能删除：

```bash
agr tool delete "$HARNESS_TOOL_ID" --region "$AGR_REGION" --yes --wait
agr model-provider delete "$MODEL_PROVIDER_ID" --region "$AGR_REGION" --yes
```
