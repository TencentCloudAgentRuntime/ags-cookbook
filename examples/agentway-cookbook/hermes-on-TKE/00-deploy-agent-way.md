# 00. 在 TKE 上部署 AgentWay

本章介绍如何在你的 TKE 集群中部署完整 AgentWay 控制面，为后续创建 Hermes Dashboard 实例做准备。

完整平台 chart 会部署 Console / Backend、PostgreSQL、Operator、Kubernetes provider、Ingress Gateway、Egress Gateway 和 Model Gateway。Hermes on TKE 推荐使用完整平台 chart，而不是 operator-only 形态。

---

## 为什么先做这一步

Hermes Dashboard 后续会通过 Console 创建，也会由 Kubernetes provider 在 TKE 集群中运行。

所以第一步不是创建 Hermes，而是先把 AgentWay 控制面和平台入口准备好。控制面部署完成后，你才能继续配置模型、创建运行时、发布模板和创建实例。

---

## 你需要填写的参数

| 参数 | 是否必填 | 示例 |
|---|---|---:|
| `modelGateway.masterKey` | 是 | `<模型网关密钥>` |
| `securityGroups.system.id` | 是 | `sg-system` |
| `securityGroups.agent.id` | 是 | `sg-agent` |
| `postgres.external.host` | 生产建议 | `10.0.0.10` |
| `postgres.external.username` | 生产建议 | `agentway` |
| `postgres.external.password` | 生产建议 | `********` |
| `defaultInfraProvider.ingress.service.mode` | 本章安装必填 | `Public` / `Private` |
| `defaultInfraProvider.ingress.service.privateSubnetId` | 内网 CLB 必填 | `subnet-xxxxxxxx` |
| `console.extraEnv` | 测试环境可选 | `ENABLE_SWAGGER=true` |

---

## 1. 准备 TKE 环境

### 1.1 VPC 与子网

1. 在腾讯云 VPC 控制台创建一个 VPC，或使用已有 VPC。
2. 在该 VPC 下创建至少 2 个子网，建议分布在不同可用区。
3. 后续如果要使用 Ingress Gateway 内网 CLB，请记录可用于内网 CLB 的子网 ID，例如 `subnet-xxxxxxxx`。

### 1.2 NAT 网关

AgentWay 的 Egress Gateway 需要访问外部 LLM Provider，例如 OpenAI-compatible Provider、OpenRouter、企业内部模型服务等。

请为 TKE 集群所在 VPC 配置 NAT 网关，并在路由表中将相关子网的默认出站路由 `0.0.0.0/0` 指向 NAT 网关。

### 1.3 创建 TKE 集群

1. 在 TKE 控制台创建集群，选择上面准备的 VPC。
2. 添加 EKS Serverless 超级节点。
3. 为超级节点绑定上面准备的子网。
4. 在本地准备好 `kubectl` 和 Helm。部署手册要求 Helm 4.x，请不要自动降级为 Helm 3.x。

### 1.4 镜像访问

AgentWay 发布镜像位于 AgentWay 镜像仓库。TKE 集群需要能够拉取 Console、Operator、Istio、Model Gateway、PostgreSQL 等镜像。

如果集群无法访问该仓库，需要提前准备镜像仓库访问策略或离线镜像方案。

### 1.5 PostgreSQL

AgentWay 默认可在集群内部署 PostgreSQL。生产环境推荐使用腾讯云 PostgreSQL：

- 建议 PostgreSQL 16。
- 必须与 TKE 集群位于同一 VPC，保证集群 Pod 可以通过内网访问。
- 安装前准备好内网地址、端口、用户名和密码。

---

## 2. 安全组配置

推荐准备两个安全组：

- `sg-system`：AgentWay 系统组件安全组，承载 Console、Operator、PostgreSQL、Model Gateway、Istio 控制面和网关。
- `sg-agent`：Agent 实例安全组，承载创建出的 Agent 实例。

### 2.1 sg-system 入站规则

| 协议 | 端口 | 来源 | 说明 |
|---|---|---|---|
| TCP | 19654, 5432 | 办公网段 CIDR | Console Web UI / API、PostgreSQL 管理 |
| TCP | 80, 443 | 按 Ingress Gateway CLB 模式选择 | Console 与 Agent 实例入口。公网 CLB 可按业务需要开放互联网来源；内网 CLB 应限制为 VPC、VPN/专线或可信办公网段 |
| TCP | ALL | sg-system | 系统组件之间内部通信 |
| TCP | 80, 443, 4000, 8080, 8443, 8444, 8445, 15012, 15017, 50051 | sg-agent | Agent 实例访问 Model Gateway、Egress Gateway、istiod、ExtAuthz |

### 2.2 sg-system 出站规则

| 协议 | 端口 | 目标 | 说明 |
|---|---|---|---|
| TCP | ALL | 0.0.0.0/0 | Egress Gateway 可能需要访问外部模型服务 |

### 2.3 sg-agent 规则

Agent 实例只需要和系统组件通信，不建议直接出公网。

入站规则：

| 协议 | 端口 | 来源 | 说明 |
|---|---|---|---|
| TCP | 80, 443 | sg-system | Ingress Gateway 转发访问流量 |

出站规则：

| 协议 | 端口 | 目标 | 说明 |
|---|---|---|---|
| TCP | 80, 443, 4000, 8080, 8443, 8444, 8445, 15012, 15017, 50051 | sg-system | Model Gateway、Egress Gateway、istiod、ExtAuthz |
| UDP | 53 | VPC DNS | DNS 解析 |

不要为 `sg-agent` 添加出站到 `0.0.0.0/0` 的规则，这是“安全组 + Egress Gateway”双重防线的核心。

---

## 3. 安装 AgentWay

生产环境不要把真实密钥直接写进可共享的命令历史、CI 日志或截图中。下面用命令行展示参数是为了说明必填项；实际使用时建议使用受控 values 文件、Secret 管理或流水线变量。

### 3.1 添加 Helm 仓库

```bash
helm repo add agent-way-system https://agentway.tencentcloudcr.com/chartrepo/system
helm repo update
```

### 3.2 使用外部 PostgreSQL 安装

生产环境推荐使用外部 PostgreSQL：

```bash
helm install agent-way agent-way-system/agent-way \
  --version 1.3.5 \
  --namespace agent-way-system --create-namespace \
  --set defaultInfraProvider.ingress.service.mode=Public \
  --set modelGateway.masterKey=<模型网关密钥> \
  --set securityGroups.system.id=<系统组件安全组ID> \
  --set securityGroups.agent.id=<Agent实例安全组ID> \
  --set postgres.external.host=<PostgreSQL内网地址> \
  --set postgres.external.port=5432 \
  --set postgres.external.username=<数据库用户名> \
  --set postgres.external.password=<数据库密码>
```

如果数据库要求 SSL，可追加：

```bash
--set postgres.external.sslmode=require
```

chart 的 pre-install hook 会尝试自动创建 `agentway` 和 `litellm` 两个数据库。如果数据库用户无权 `CREATE DATABASE`，请提前手工创建：

```sql
CREATE DATABASE litellm;
CREATE DATABASE agentway;
```

### 3.3 使用内置 PostgreSQL 安装

测试环境可以使用内置 PostgreSQL：

```bash
helm install agent-way agent-way-system/agent-way \
  --version 1.3.5 \
  --namespace agent-way-system --create-namespace \
  --set defaultInfraProvider.ingress.service.mode=Public \
  --set modelGateway.masterKey=<模型网关密钥> \
  --set postgres.password=<内置PostgreSQL密码> \
  --set securityGroups.system.id=<系统组件安全组ID> \
  --set securityGroups.agent.id=<Agent实例安全组ID>
```

### 3.4 测试环境开启 Swagger API 文档

Console 后端内置 Swagger UI，可用于查看和调试 Console API。测试环境建议开启，方便确认 API 入参和响应结构；生产环境不建议开启，也不要把 Swagger 页面暴露到公网。

开启方式是在 Helm 部署时给 Console 追加环境变量：

```bash
--set 'console.extraEnv[0].name=ENABLE_SWAGGER' \
--set-string 'console.extraEnv[0].value=true'
```

例如测试环境使用内置 PostgreSQL 安装时，可以追加到安装命令末尾：

```bash
helm install agent-way agent-way-system/agent-way \
  --version 1.3.5 \
  --namespace agent-way-system --create-namespace \
  --set defaultInfraProvider.ingress.service.mode=Public \
  --set modelGateway.masterKey=<模型网关密钥> \
  --set postgres.password=<内置PostgreSQL密码> \
  --set securityGroups.system.id=<系统组件安全组ID> \
  --set securityGroups.agent.id=<Agent实例安全组ID> \
  --set 'console.extraEnv[0].name=ENABLE_SWAGGER' \
  --set-string 'console.extraEnv[0].value=true'
```

开启后，可通过 Console 地址访问：

```text
http://<console-host>/swagger/index.html
```

如果使用端口转发访问 Console：

```bash
kubectl -n agent-way-system port-forward pod/<agent-way-console-pod> 19654:8080
```

然后在浏览器打开：

```text
http://127.0.0.1:19654/swagger/index.html
```

### 3.5 等待组件就绪

```bash
kubectl get pods -n agent-way-system -w
kubectl get pods -n agent-infra -w
```

预期：

- `agent-way-system` 中 Console、Operator、PostgreSQL 等控制面组件进入 `Running`。
- `agent-infra` 中 istiod、Ingress Gateway、Egress Gateway、Model Gateway 等基础设施组件进入 `Running`。

Istio 和 Model Gateway 由 Operator 启动后自动安装，通常需要额外等待几分钟。

---

## 4. 配置 Ingress Gateway CLB 模式

AgentWay 通过 `agent-infra/istio-ingressgateway` 这个 stable Service 暴露 Console 和 Agent 实例入口。chart 1.3.5 默认不声明 `ingress.service`，Operator 此时创建 `type: ClusterIP`，不会创建公网 CLB。本章安装命令显式设置 `Public`，才会创建公网 LoadBalancer；也可以改用 `Private` 并指定子网。

### 4.1 模式说明

| 模式 | 配置值 | 行为 |
|---|---|---|
| 集群内访问（默认） | 不声明 `service` | 创建 ClusterIP，无 CLB 和 EXTERNAL-IP |
| 公网 CLB | `Public` | 创建 LoadBalancer，不设置 TKE 内网 CLB annotation，由 TKE 创建公网 CLB |
| 内网 CLB | `Private` + `privateSubnetId` | 在 Service 上设置 `service.kubernetes.io/qcloud-loadbalancer-internal-subnetid=<子网ID>`，由 TKE 创建内网 CLB |

`privateSubnetId` 必须是当前 TKE 集群 VPC 内可用于内网 CLB 的子网 ID。

### 4.2 新安装时直接使用内网 CLB

如果从一开始就希望 AgentWay 入口使用内网 CLB，把安装命令中的 `mode=Public` 替换为以下参数：

```bash
--set defaultInfraProvider.ingress.service.mode=Private \
--set defaultInfraProvider.ingress.service.privateSubnetId=subnet-xxxxxxxx
```

注意：`defaultInfraProvider.ingress.service.*` 只影响 Operator 首次自举名为 `default` 的 `AgentInfraProvider`。如果 `default` 已经存在，Helm upgrade 不会覆盖已有的 Provider 声明。

### 4.3 已安装集群切换为内网 CLB

对已经存在的默认 Provider，直接 patch `AgentInfraProvider`：

```bash
kubectl patch agentinfraprovider default --type merge -p '{
  "spec": {
    "kubernetes": {
      "ingress": {
        "service": {
          "mode": "Private",
          "privateSubnetId": "subnet-xxxxxxxx"
        }
      }
    }
  }
}'
```

观察 Service 变化：

```bash
kubectl get service istio-ingressgateway -n agent-infra -w
```

内网 CLB 就绪后，`EXTERNAL-IP` 应变为 VPC 内网地址，例如 `10.x.x.x`。

### 4.4 切回公网 CLB

切回公网会改变平台入口暴露范围，并可能带来短暂访问中断。执行前请确认公网访问符合本环境的安全要求，安全组、DNS、TLS 和 Console 登录策略都已就绪。

```bash
kubectl patch agentinfraprovider default --type merge -p '{
  "spec": {
    "kubernetes": {
      "ingress": {
        "service": {
          "mode": "Public"
        }
      }
    }
  }
}'
```

切换 Public / Private 时，Operator 会删除并重建 `istio-ingressgateway` Service，让 TKE 重新创建对应 CLB。这会带来短暂入口中断，底层 CLB 地址也可能变化，请在维护窗口执行。

### 4.5 访问内网 CLB 的限制

内网 CLB 地址通常只能在你的 VPC 内访问。本地办公网如果与 TKE VPC 网络隔离，不能直接访问该地址。

常见访问方式：

- 从 VPC 内机器访问；
- 通过 VPN 或专线访问；
- 本地调试时使用 `kubectl port-forward` 访问控制面服务；
- DNS 使用 Private DNS 或内网 DNS，将平台域名和 Agent 泛域名解析到内网 CLB 地址。

---

## 5. 验证安装

### 5.1 检查组件状态

```bash
kubectl get pods -n agent-way-system
kubectl get pods -n agent-infra
kubectl get agentinfraprovider default -o yaml
kubectl get svc istio-ingressgateway -n agent-infra
```

重点确认：

```yaml
status:
  phase: Ready
```

### 5.2 打开 Console

获取入口地址：

```bash
kubectl get svc istio-ingressgateway -n agent-infra
```

如果使用公网 CLB，浏览器直接打开：

```text
http://<Ingress Gateway 公网地址>/
```

生产环境不要把 Console 以开发默认密码暴露到公网。启用公网 CLB 前，请先确认已经设置强 `console.env.ADMIN_PASSWORD`、限制安全组来源，并按本环境安全要求配置 HTTPS/TLS 和访问控制。

如果使用内网 CLB，访问方需要位于你的 VPC、VPN、专线或跳板网络中。本地调试时也可以临时使用：

```bash
kubectl -n agent-way-system port-forward pod/<agent-way-console-pod> 19654:8080
```

然后打开：

```text
http://127.0.0.1:19654/
```

首次登录：

```text
用户名：admin
密码：安装时通过 console.env.ADMIN_PASSWORD 设置；未设置时为开发默认密码
```

登录后进入 **平台设置**、**模型配置**、**运行环境** 等页面，说明 Console 已可用。

---

## 预期效果

部署完成后，你应该看到：

- `agent-way-system` 中 Console、Operator、PostgreSQL 正常运行
- `agent-infra` 中 Ingress Gateway、Egress Gateway、Model Gateway 正常运行
- `AgentInfraProvider default` 状态为 `Ready`
- Console 页面可以打开并登录

---

## 下一章

完成后，继续：

- [01. 准备 Hermes 需要的平台设置](./01-prepare-hermes-platform-settings.md)
