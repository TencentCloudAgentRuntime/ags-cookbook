# 使用 `agr` 创建托管 Harness：最短完整链路

本教程登记一个 TokenHub 模型，创建一个使用 `pi` 引擎的托管 Harness 并等待修订 1 发布，确认 ACP 入口可用后对话一次，最后删除全部资源。变更与回滚、接入方式、伸缩与会话持久化由相邻教程独立讲解。

开始前，请完成公共[前置条件](../README_zh.md#前置条件)和[配置](../README_zh.md#配置)。

在本场景目录中执行命令。创建命令会自动保存资源 ID，供后续步骤和清理使用。示例输出中的账号、资源 ID、时间和请求 ID 均已脱敏。

## 1. 设置环境变量

加载前置条件中配置的公共 `.env`，并在创建资源前检查 CLI。`.env` 中的后缀用于区分本示例的资源名称。

```bash
set -a
source ../.env
set +a
bash ../scripts/preflight.sh simple &&

export MODEL_PROVIDER_NAME="harness-simple-$HARNESS_NAME_SUFFIX" &&
export HARNESS_NAME="harness-simple-$HARNESS_NAME_SUFFIX"
```

预检会输出 `agr status` 和 `agr doctor` 的结果，最后显示 `Preflight passed`。status 部分的格式如下；命令使用 `.env` 中的地域：

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
MODEL_PROVIDER_ID=$(python3 ../scripts/resources.py create simple model-provider \
  --name "$MODEL_PROVIDER_NAME" \
  --tokenhub-api-key-id "$TOKENHUB_API_KEY_ID" \
  --model hy3) && export MODEL_PROVIDER_ID
```

查看已创建的模型连接：

```bash
agr model-provider get "$MODEL_PROVIDER_ID" --region "$AGR_REGION" -o text
```

预期输出格式：

```text
Model provider:  mp-********
Name:            harness-simple-****
Source:          TokenHub (ApiKeyId ak-********)
Models:          hy3[TEXT]
Tags:            -
Updated:         <masked-time>
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

加上 `--wait` 正式创建，脚本会提取返回的 ID：

```bash
HARNESS_ID=$(python3 ../scripts/resources.py create simple harness \
  --name "$HARNESS_NAME" \
  --engine "$HARNESS_ENGINE" \
  --engine-version "$HARNESS_ENGINE_VERSION" \
  --model "$MODEL_PROVIDER_ID:hy3" \
  --system-prompt 'You are a concise assistant. Answer in one short paragraph.' \
  --role-arn "$AGR_ROLE_ARN" \
  --subnet-id "$HARNESS_SUBNET_ID" \
  --security-group-id "$HARNESS_SECURITY_GROUP_ID" \
  --wait) && export HARNESS_ID
```

脚本会将 Harness、Tool 和 Deployment ID 保存到 `.state/simple.json`。查看已发布的修订：

```bash
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
HARNESS_ID=$(python3 ../scripts/resources.py get simple HarnessId) && export HARNESS_ID
agr harness revision get "$HARNESS_ID" 1 --region "$AGR_REGION"
```

`Status reason` 一行说明失败在哪一步。如果是无需修改已保存初始化配置即可修正的外部原因，例如角色权限或 VPC 出网配置，修正后对同一个修订重试：

```bash
agr harness revision publish "$HARNESS_ID" 1 --region "$AGR_REGION" --wait
```

子网 ID 错误或地域不匹配时，需要修正初始化参数并创建新的 Harness。`harness update` 无法修改已保存的初始化配置，因此重试这个修订仍会使用错误的值。请先删除失败的 Harness，并按第 7 步清理已记录的 Sandbox Tool。

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

删除本场景保存的资源。脚本从 `.state/` 读取 ID 和地域，等待删除完成并回查结果；清理中断后可以重复执行。

```bash
python3 ../scripts/resources.py cleanup simple --yes
```
