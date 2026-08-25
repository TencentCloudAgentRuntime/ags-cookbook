# 在 AGR 上运行 all-in-one DeepSeek Harness

本教程把 DeepSeek Harness 的 Web UI、Agent Host 和命令执行环境放在同一个 Sandbox Instance 中，并通过一个 Deployment 对外提供服务。读者将完成以下链路：

1. 使用固定版本镜像创建 Sandbox Tool。
2. 创建一个可缩至零、空闲后暂停、使用独占会话亲和的 Deployment。
3. 通过 `agr deployment proxy` 打开 Web UI。
4. 在 Web UI 中接入腾讯云 TokenHub，使用 Standard Agent 完成一个真实编码任务。
5. 停止访问并观察实例进入 `PAUSED`，再用同一个 affinity ID 恢复工作区与会话。

命令输出示例来自实际命令的结构，并对账号、资源 ID、时间和请求 ID 做了脱敏。不要直接复制示例输出中的占位值。

## 前置条件

- 已安装 `agr`，当前账号可以创建和删除 Sandbox Tool、Deployment 与 Instance。
- 已准备允许 AGR 拉取 CCR 镜像的 CAM 角色 ARN。
- 本机端口 `18080` 可用。
- 已开通腾讯云 TokenHub 并准备 API Key。TokenHub API 使用说明见[官方文档](https://cloud.tencent.com/document/product/1823/130078)。
- 可以访问公共镜像 `ccr.ccs.tencentyun.com/ags.dev/deepseek-harness:v0.1.1-rc.2-ags.4`。

本教程不会把 TokenHub API Key 写入镜像、Tool、Deployment 或命令行；它只在 DeepSeek Harness Web UI 中手工录入。

## 1. 设置本地环境变量

把角色 ARN 和两个名称替换为自己的值。名称中的后缀应保持唯一。

```bash
export AGR_REGION=ap-shanghai
export AGR_ROLE_ARN='qcs::cam::uin/100000000001:roleName/replace-me'
export DSH_TOOL_NAME='deepseek-harness-all-in-one-your-name'
export DSH_DEPLOYMENT_NAME='deepseek-harness-all-in-one-your-name'

agr status
```

预期输出格式如下。`agr status` 显示的是本机默认 region；后续命令都会通过 `--region "$AGR_REGION"` 明确使用 `ap-shanghai`。

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

## 2. 创建 DeepSeek Harness Tool

Tool 使用固定版本镜像、`2 vCPU / 4 GiB` 资源和 `3080` HTTP 端口。启动参数允许容器监听 `0.0.0.0`，同时信任 `ap-shanghai` 的 Deployment 外部域名和网关转发到容器时使用的实例内部域名。`--allow-remote-management` 让这些受信任、且已经过 AGS Deployment Token 网关保护的请求可以完成 Provider、凭据和其他 Web UI 管理操作；它不会放行未命中 `trustedHosts` 的请求。镜像如何从官方源码构建见 [dockerfiles](./dockerfiles/README_zh.md)。

```bash
agr tool create \
  --region "$AGR_REGION" \
  --tool-name "$DSH_TOOL_NAME" \
  --tool-type custom \
  --persistent \
  --role-arn "$AGR_ROLE_ARN" \
  --network-configuration '{"NetworkMode":"PUBLIC"}' \
  --custom-configuration '{
    "Image": "ccr.ccs.tencentyun.com/ags.dev/deepseek-harness:v0.1.1-rc.2-ags.4",
    "ImageRegistryType": "personal",
    "Command": [
      "node",
      "--expose-internals",
      "/usr/local/lib/node_modules/@deepseek-ai/dsh/lib/bin.js"
    ],
    "Args": [
      "web",
      "--host",
      "0.0.0.0",
      "--port",
      "3080",
      "--trusted-host",
      "*.ap-shanghai.agents.tencentags.com",
      "--trusted-host",
      "*.ap-shanghai.internal.tencentags.com",
      "--allow-remote-management",
      "--no-open"
    ],
    "Ports": [
      {
        "Name": "web",
        "Port": 3080,
        "Protocol": "TCP"
      }
    ],
    "Resources": {
      "CPU": "2000m",
      "Memory": "4Gi"
    },
    "Probe": {
      "HttpGet": {
        "Path": "/",
        "Port": 3080,
        "Scheme": "HTTP"
      },
      "ReadyTimeoutMs": 30000,
      "ProbeTimeoutMs": 3000,
      "ProbePeriodMs": 5000,
      "SuccessThreshold": 1,
      "FailureThreshold": 6
    }
  }' \
  --wait
```

`--wait` 会等待 Tool 进入最终状态，成功输出包含真实 Tool ID。例如：

```text
ID:          sdt-********
Name:        deepseek-harness-all-in-one-****
Type:        custom
Status:      ACTIVE
NetworkMode:  PUBLIC
Description:
Tags:        qcs:tag:createdBy=<masked-creator>
Created:     <masked-time>
RoleArn:     qcs::cam::uin/************:roleName/****
```

先从 `ID` 行复制真实 Tool ID，再设置环境变量：

```bash
export DSH_TOOL_ID='sdt-replace-me'
```

## 3. 创建独占会话 Deployment

这个配置有三层含义：

- `MinInstanceCount=0`：没有活跃会话时可以缩至零。
- `IdleTimeoutSeconds=60` 与 `PAUSE`：最后一个 Deployment 连接结束 60 秒后，暂停实例但保留工作区状态。
- `EXCLUSIVE`：每个 affinity ID 独占一个不可迁移的实例；`MaxInstanceCount=3` 因而也是同时存在的独占会话上限。

```bash
agr deployment create \
  --region "$AGR_REGION" \
  --deployment-name "$DSH_DEPLOYMENT_NAME" \
  --tool-id "$DSH_TOOL_ID" \
  --scaling-configuration '{
    "MinInstanceCount": 0,
    "MaxInstanceCount": 3,
    "MaxInstanceRequestConcurrency": 200
  }' \
  --lifecycle-configuration '{
    "IdleTimeoutSeconds": 60,
    "IdleAction": "PAUSE"
  }' \
  --affinity-configuration '{
    "Mode": "EXCLUSIVE",
    "HeaderName": "X-Tencent-Agr-Affinity-Id"
  }'
```

成功输出包含真实 Deployment ID 和完整配置。例如：

```text
Name:          deepseek-harness-all-in-one-****
ID:            dpl-********
Tool:          sdt-********
Status:        ACTIVE
Tags:          <none>
Created:       <masked-timestamp>
Updated:       <masked-timestamp>
Scaling:
  Min Instances:                0
  Max Instances:                3
  Max Requests per Instance:    200
Lifecycle:
  Idle Action:                  PAUSE
  Idle Timeout:                 1m
Affinity:
  Mode:                         EXCLUSIVE
  Header:                       X-Tencent-Agr-Affinity-Id
```

从 `ID` 行复制真实 Deployment ID 后设置环境变量，并查询一次确认配置：

```bash
export DSH_DEPLOYMENT_ID='dpl-replace-me'

agr deployment get "$DSH_DEPLOYMENT_ID" --region "$AGR_REGION"
```

## 4. 通过本地 proxy 打开 Web UI

运行下面的命令后，proxy 会一直占用当前终端。它监听 `127.0.0.1:18080`，自动获取短期 Deployment Token，并在第一次请求后打印服务返回的 affinity ID。

```bash
agr deployment proxy "$DSH_DEPLOYMENT_ID" 18080:3080 --region "$AGR_REGION"
```

预期输出格式如下：

```text
<masked-timestamp> Proxy listening on 127.0.0.1:18080 (forwarding to https://3080-dpl-********.ap-shanghai.agents.tencentags.com)
Deployment proxy is recommended only for local debugging.
Forwarding from 127.0.0.1:18080 -> 3080
  Local:  http://127.0.0.1:18080
  Remote: https://3080-dpl-********.ap-shanghai.agents.tencentags.com

Press Ctrl+C to stop.
Affinity ID: <masked-affinity-id>
```

proxy 只适合本地调试。生产客户端应通过 `AcquireDeploymentToken` 接口获取短期 Token，再直接访问 Deployment 数据面域名。HTTP 端口的域名规则为 `https://{port}-{deployment-id}.{region}.agents.{data-plane-domain}`；默认数据面域名是 `tencentags.com`，因此本例为 `https://3080-{deployment-id}.ap-shanghai.agents.tencentags.com`。

保持 proxy 运行，在浏览器打开 <http://127.0.0.1:18080>。如果首次启动需要创建实例，页面出现前会有一段冷启动等待；若首次请求因超过 proxy 的响应等待时间而显示 `Bad Gateway`，待实例启动后刷新页面即可。

看到 affinity ID 后立即复制它，并在另一个终端设置环境变量；这个值将在恢复步骤使用：

```bash
export DSH_AFFINITY_ID='replace-with-proxy-output'
```

## 5. 在 Web UI 中接入 TokenHub

首次进入时如果出现 DeepSeek 官方 API Key 引导，选择“稍后配置”。然后打开“设置 → 模型”，添加一个自定义提供方：

| 字段 | 值 |
| --- | --- |
| Provider ID | `tokenhub` |
| 显示名称 | `Tencent Cloud TokenHub` |
| API 地址 | `https://tokenhub.tencentmaas.com/v1` |
| API 协议 | `openai-completions` |
| API Key | 在页面中手工输入 TokenHub API Key |
| 模型 ID | `deepseek-v4-flash` |

创建提供方后，新建 Agent，选择 `Standard` preset，并选择 `tokenhub/deepseek-v4-flash` 模型。这里不安装额外插件，也不修改 DeepSeek Harness 的预设。

发送任务前，把输入框旁的文件访问模式切换为 `Full access`。当前 all-in-one 镜像没有安装可供 DeepSeek Harness 使用的 OS 沙箱后端；如果保持 `workspace-write`，Agent 的 Bash 调用会失败并进入提权审批，页面将停在 `Waiting for approval`。本教程的独占实例只服务一个 affinity 会话，并且前面已经接受使用 root 运行，因此直接使用 `Full access`。

## 6. 完成第一个真实任务

向 Agent 发送下面的任务：

```text
在 /workspace/todo-cli 中创建一个零依赖的 Node.js CLI：

- node cli.mjs add <text>：新增事项；
- node cli.mjs list：列出全部事项；
- node cli.mjs done <id>：把指定事项标记为完成；
- 数据持久化到 /workspace/todo-cli/todos.json；
- 使用 node:test 编写测试；
- 编写简短 README，包含命令示例。

完成后运行 node --test，并展示一次 add、list、done 的实际结果。
```

验收时至少确认：

- `/workspace/todo-cli` 中存在实现、测试和 README；
- `node --test` 通过；
- 三个命令的实际输出符合 README；
- Agent 没有引入第三方 npm 依赖。

## 7. 观察空闲暂停

回到 proxy 所在终端，按 `Ctrl+C` 结束连接。不要再访问本地页面，手工等待至少 60 秒；实例状态异步收敛，实际时间可能略长。

在另一个终端查询该 Tool 的实例：

```bash
agr instance list --tool-id "$DSH_TOOL_ID" --region "$AGR_REGION"
```

预期会看到同一个实例进入 `PAUSED`：

```text
ID                    TOOL                                STATUS  TIMEOUT  EXPIRES  MOUNTS  CREATED
<masked-instance-id>  deepseek-harness-all-in-one-****    PAUSED  0s       -        -       <masked-time>
```

如果仍是 `RUNNING`，继续保持无连接并稍后重新执行同一条查询命令；本教程不使用轮询脚本。

## 8. 恢复同一个独占会话

确认当前终端已经设置了真实 affinity ID，然后显式恢复该会话：

```bash
export DSH_AFFINITY_ID='replace-with-proxy-output'

agr deployment proxy "$DSH_DEPLOYMENT_ID" 18080:3080 \
  --region "$AGR_REGION" \
  --affinity-id "$DSH_AFFINITY_ID"
```

proxy 会恢复 affinity ID 对应的已暂停实例，而不是把会话迁移到另一个实例。重新打开 <http://127.0.0.1:18080>，确认之前的 Agent 会话和 `/workspace/todo-cli` 都仍然存在。

然后发送一个增量任务：

```text
继续修改同一个 /workspace/todo-cli 项目：增加 clear-completed 命令，删除所有已完成事项；补充测试和 README，并再次运行 node --test。不要重写已有实现。
```

验收 `clear-completed` 后，本例同时证明了独占 affinity 路由、`PAUSE` 恢复和工作区连续性。

## 9. 清理资源

完成验收后先按 `Ctrl+C` 停止 proxy，再删除 Deployment：

```bash
agr deployment delete "$DSH_DEPLOYMENT_ID" --region "$AGR_REGION"
agr instance list --tool-id "$DSH_TOOL_ID" --region "$AGR_REGION"
```

如果仍有非 `STOPPED` 实例，逐个复制实例 ID，先设置环境变量再删除：

```bash
export DSH_INSTANCE_ID='replace-with-instance-id'
agr instance delete "$DSH_INSTANCE_ID" --region "$AGR_REGION" --yes --wait
```

最后删除 Tool：

```bash
agr tool delete "$DSH_TOOL_ID" --region "$AGR_REGION" --yes --wait
```
