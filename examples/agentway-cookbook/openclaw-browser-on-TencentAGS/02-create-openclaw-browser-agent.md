# 02. 快速启动一个自带浏览器和角色设定的 OpenClaw

## 本章场景

本章创建带浏览器、默认角色描述和模型配置的 OpenClaw 实例，验证页面启动与模型调用。

清单一次创建 **3 个 AGS Agent**，每个 2 CPU / 4Gi，合计 6 CPU / 12Gi；云端资源和费用按 3 个实例估算。只需要一个实例时，先删除清单中 `openclaw-browser-agent2`、`openclaw-browser-agent3` 两个文档块。

`skillPacks` 默认注释，本章只安装 SkillHub 工具，不承诺预装 Skill。可选技能安装见第 04、07 章。

---

## 前置章节

请先完成：
- [00. 准备集群环境并部署 Operator](./00-prepare-cluster-and-deploy-operator.md)
- [01. 准备 Tencent Agent Runtime 基础设施](./01-prepare-tencent-agent-runtime.md)

---

## 原理说明

这一章虽然底层会用到 `AgentProfile`、`AgentTemplate` 和 `Agent` 三类对象，但你可以把它们理解成三层不同职责：

- **运行画像**：定义 OpenClaw 镜像如何启动、对外怎么暴露、命令默认用哪个用户执行
- **业务预设**：定义角色描述、模型配置注入和可选 Skill
- **实例对象**：真正创建一个可以访问的 OpenClaw

也就是说：
- `AgentProfile` 更像“运行底座”
- `AgentTemplate` 更像“业务套餐”
- `Agent` 才是“真正上线的那个实例”

这样分层后，你后面要做网络防护、配置复用和灰度发布时，会自然很多。

---

## 场景示意图

```mermaid
flowchart LR
    Profile[运行画像]
    Skills[可选 Skill，默认关闭]
    Files[角色描述 / 模型配置]
    Boot[启动脚本]
    Profile --> Template[业务套餐]
    Skills --> Template
    Files --> Template
    Boot --> Template
    Template --> Agent[OpenClaw Agent]
    Agent --> URL[可访问的浏览器 URL]
```

## 你需要填写的参数

这一章大多数内容可以直接复制。你只需要按实际情况替换：

| 参数 | 是否必填 | 示例 |
|---|---|---:|
| namespace | 是 | `default` |
| 模型配置 | 功能验收必填 | 确认 `openclaw-model-config` 中 provider、baseUrl、模型与 Key 匹配 |
| 模型 API Key | 功能验收必填 | 将模板 env 中 `CHANGE_ME_MODEL_API_KEY` 换成真实 Key；仅验证页面启动时可以暂不配置 |
| 角色描述 | 否 | 可以先使用文档里的默认值 |
| Skill 列表 | 可选 | 默认未启用 `skillPacks`，需要时自行配置并验收 |

---

## 这一步最终会得到什么

执行完本章后，你会得到一组示例 OpenClaw Agent：
- 运行在 Tencent Agent Runtime 上的 OpenClaw
- 自带浏览器访问能力
- 已安装 SkillHub 工具；默认不预装 Skill
- 自带默认角色描述
- 已经注入模型配置文件
- 可以直接拿 URL 打开
- 可以通过 `Agent` 名称直接进入对应 AGS 实例的 shell

---

## 使用 manifest

你可以直接使用旁边的 manifest 文件：`./manifests/02-openclaw-browser-agent.yaml`

先替换模型 Key 并确认实例数量，再执行：

```bash
kubectl apply -f ./openclaw-browser-on-TencentAGS/manifests/02-openclaw-browser-agent.yaml
```

YAML 内容以上文链接的 `manifests/` 文件为唯一事实来源，本文不再重复维护。

固定版本 `d5afc116` 使用小写 `volumeMounts[].subpath`：省略时按 Agent UID 和挂载名称隔离，显式填写时固定到文件系统中的指定目录。本例 `/shared` 挂载使用固定 `subpath: shared-subpath`，三个实例共享该目录；`/openclaw` 则各自隔离。

模板统一提供 `MODEL_API_KEY` 和 `OPENCLAW_MODE=browser`；第三个 Agent 追加 `OPENCLAW_DEBUG=true`。如需按实例覆盖模型 Key，可在该 Agent 的 `env` 中设置同名 key。

---

## 这一份 YAML 里分别完成了什么

为了让你能边复制边理解，我把它拆成业务视角来解释：

### 1. 让 OpenClaw 本体能跑起来

`AgentProfile` 里定义了：
- 浏览器镜像
- 访问端口
- 健康检查
- 存储目录

这部分决定的是：

> 这个 OpenClaw 作为“运行时”应该怎样启动、存活和对外提供访问。

### 2. 安装 SkillHub 工具（可选技能另行启用）

`bootstrapScripts` 安装 SkillHub 并创建工作目录。`skillPacks` 保持注释，因此默认没有 Skill 安装任务；页面可访问不代表 Skill 可用。需要预装时，取消注释并确认所选技能存在、安装状态成功，再在实例内检查技能目录。

### 3. 给 OpenClaw 一个默认角色描述

`fileInjects` 中写入 `AGENTS.md`，本质上就是在给 OpenClaw 提供默认工作说明。

这样做的意义是：
- 不同业务团队可以给不同 OpenClaw 预设不同人格和任务边界
- 第一次打开时，它就知道自己大概要做什么

### 4. 自动注入模型配置

同样通过 `fileInjects`，我们把模型配置文件写进 `/openclaw/.openclaw/openclaw.json`。

这一步解决的问题是：

> OpenClaw 不只是“能打开”，还应该一启动就知道去哪里调用模型。

所以业务负责人不需要在 OpenClaw 启动后再手工去补模型连接配置。

### 5.（可选）暴露额外的对外端口

`AgentProfile.spec.access.port` 声明的是 Agent 的**主访问端口**（OpenClaw 网关 9000），Agent 运行起来后 AgentWay 会把这个端口的 URL 放到 `agent.status.accessURL`。

但实际业务里，沙箱容器可能同时暴露多个端口：例如 5900（VNC 远程桌面）、9100（Prometheus metrics）、6080（noVNC Web 端），它们也需要从公网访问。

对这种场景，在 profile 里用 `ports:` 列出来即可：

```yaml
spec:
  image: ccr.ccs.tencentyun.com/yaominxia/sandbox-openclaw-browser:v1.12
  access:
    port: 9000
    path: /
  ports:
    - name: vnc
      port: 5900
      protocol: TCP
    - name: metrics
      port: 9100
      protocol: TCP
```

使用 Tencent AGS provider 时，operator 会把这些端口合并到 AGS `CustomConfiguration.Ports` 一起申请（在 `envd(49983)` 和 `access.port` 之后追加），AGS 平台会为每个端口分配一个独立的公网访问域名：

```
https://{port}-{sandboxId}.{region}.tencentags.com
```

例如 `sandboxId=sbx-abcd1234`、`region=ap-shanghai`、声明了 `vnc/5900` 后，就可以通过 `https://5900-sbx-abcd1234.ap-shanghai.tencentags.com` 直连容器内 5900 端口的服务。

几个容易踩坑的点：

- `name` 必须是 DNS label（小写字母开头、只含 `a-z0-9-`），且**不能叫 `envd` 或 `http`**，这两个名字被 operator 内部保留用来表示"envd sidecar"和"主访问端口"。
- `port` 不能是 `49983`——该端口固定给 envd sidecar 使用。
- `protocol` 目前仅支持 `TCP`，留空时默认就是 TCP。
- 只有 **Tencent AGS provider** 会读取这个字段；使用 K8s provider（本地 k3d / 自建集群）时 `ports` 会被静默忽略，不报错也不建 Service。

### 选择是否关闭访问 token（`spec.authMode`）

AGS 默认会为每个 sandbox 实例分配一个 access token，访问 `status.accessURL` 时必须在 HTTP header 中带 `X-Access-Token: <token>` 才能通过。这份默认策略对大部分业务是合理的，但在下列场景里会成为阻碍：

- 想把 `AccessURL` 直接分享给同事、客户或嵌入到外部系统里，不希望使用方额外处理 token。
- 已经在网关侧 / 业务侧自建访问控制（SSO、WAF、SPN 等），平台再加一层 token 校验反而冗余。
- 单纯做演示或 demo 页面，要求"打开链接即可使用"。

这时可以在 `Agent.spec.authMode` 声明：

```yaml
spec:
  authMode: none   # 默认 default，改成 none 代表不下发 token（DEFAULT / NONE 也都接受）
```

字段说明：
- `default`（或留空）：保持现有行为，AGS 下发 token，Operator 回填到 `status.gatewayToken`。
- `none`：AGS 不下发 token，`status.gatewayToken` 为空，`status.accessURL` 不带 `access_token` 查询参数，直接访问即可。
- 取值大小写均可：`default`/`DEFAULT` 等价，`none`/`NONE` 等价。推荐使用小写。
- 改动 `authMode` 会触发 sandbox **实例重建**，短暂不可用。
- `authMode` 仅定义在 `Agent.spec` 上；`AgentProfile` 不再承载该字段。
- 仅 Tencent AGS provider 读取；K8s provider 当前不支持此语义，该字段会被静默忽略。

> 安全提醒：`authMode: none` 意味着平台不再提供访问保护，必须由你自己保证访问来源可信（VPN、网关白名单、公网授权等），否则会构成未授权访问。

---

## 执行步骤

```bash
kubectl apply -f ./openclaw-browser-on-TencentAGS/manifests/02-openclaw-browser-agent.yaml
```

等待 Agent Ready：

```bash
kubectl get agent openclaw-browser-agent -n default -w
```

获取访问 URL：

```bash
kubectl get agent openclaw-browser-agent -n default -o jsonpath='{.status.accessURL}'
```

---

## 如何直接进入这个 Agent 的 shell

如果你在第 00 章增量应用了 `00-01-connect.yaml`，集群里会部署 `agent-way-connect` 服务，并注册 Agent connect API：`connect.agentway.io/v1alpha1`。

它的目标就是让你**不需要手工查询 sandbox ID**，只要知道：

- `Agent` 所在 namespace
- `Agent` 名称

就能登录到对应 AGS 实例里做验证或排障。

### 1. 先确认 Agent connect API 已就绪

如果还没有开启 AA/connect 服务，先执行：

```bash
kubectl apply -f ./openclaw-browser-on-TencentAGS/manifests/00-01-connect.yaml
kubectl rollout status deployment/agent-way-connect -n agent-way-system
```

```bash
kubectl get apiservice v1alpha1.connect.agentway.io
```

你应该看到 `AVAILABLE=True`。

### 2. 安装并使用 `kubectl agent exec` 进入 shell

首次使用时，从 cookbook 目录进入第 00 章获取的固定版本源码：

```bash
cd agentway-v1.0.15-d5afc116/operator
go build -o ./bin/kubectl-agent ./cmd/kubectl-agent
mkdir -p "$HOME/.local/bin"
install -m 755 ./bin/kubectl-agent "$HOME/.local/bin/kubectl-agent"
export PATH="$HOME/.local/bin:$PATH"

kubectl agent exec -n default openclaw-browser-agent
```

默认会进入：

```text
/bin/bash -i
```

也就是说，你现在只需要给出 `Agent` 名称 `openclaw-browser-agent`，插件会自动：

1. 启动本地 `kubectl proxy`
2. 连接 `connect.agentway.io/v1alpha1`
3. 由 `agent-way-connect` 在集群内把你的终端输入转发到对应 AGS 实例

### 3. 如果只想执行一条命令

```bash
kubectl agent exec -n default openclaw-browser-agent -- bash -lc 'id && pwd && ls -la /openclaw'
```

这个模式很适合做“实例是否真的起来了”的快速验证。

### 4. 权限要求

调用方需要具备下面这个 Kubernetes 权限：

- API Group: `agent.agentway.io`
- Resource: `agents/exec`
- Verb: `create`

如果你使用的是集群管理员账号，通常已经具备该权限。

---

## 预期效果

做完后，你应该看到：
- `status.phase=Running`
- `status.accessURL` 非空
- bootstrap、file inject 有成功状态记录；默认未启用 skillPacks，不要求 Skill 安装成功状态
- `kubectl agent exec` 能通过 `Agent` 名称直接进入实例 shell

页面启动、模型调用和 Skill 安装需要分别验收，不能用 `Running` 或 URL 非空替代功能验证。

---

## 如何验证

```bash
kubectl get agent openclaw-browser-agent -n default -o yaml
```

重点看：
- `status.phase`
- `status.message`
- `status.accessURL`
- `status.bootstrapStatus`
- `status.skillStatus`（仅启用 `skillPacks` 时检查）
- `status.fileInjectStatus`

如果这些都正常，你就可以把 `status.accessURL` 复制到浏览器打开。

真实模型 Key 配置后，在 OpenClaw 页面发送一条消息，确认收到模型回复且没有鉴权错误。未完成这一步，只能认定页面/实例启动成功。

如果启用了 `skillPacks`，还需确认 `status.skillStatus` 成功，并进入 shell 检查 `/openclaw/.openclaw/workspace/skills` 下存在对应技能，再实际触发一次技能使用。

如果你还想进一步确认实例内部状态，可以直接进入 shell：

```bash
kubectl agent exec -n default openclaw-browser-agent
```

---

## 下一章

完成后，继续：
- [03. 保护 OpenClaw 只访问你允许的目标](./03-build-secure-network-access-policy.md)
