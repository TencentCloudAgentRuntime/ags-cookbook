# 在 TKE 上运行 Hermes Dashboard

这条主线会带你从 0 开始，在自己的 TKE 集群中部署完整 AgentWay 控制面，创建一个运行在 **Kubernetes provider** 上的 Hermes Dashboard，并逐步扩展到平台设置、出口访问控制、配置复用、凭证注入、审计、限额、持久化、观测和升级。

文档默认以 **Console 页面操作**作为主要路径；由于 Console 背后的配置最终都会落到 AgentWay CRD，每一章也会给出等价的 **Kubernetes API / kubectl** 用法，方便你做自动化和问题定位。

---

## 这条主线能帮你完成什么

按顺序完成本目录下的章节后，你可以做到：

1. 在 TKE 上部署完整 AgentWay 控制面
2. 配置模型网关、系统域名和 Agent 子域名访问模式
3. 通过 Console 创建 Hermes 文件预设、运行时、模板、发布版本和实例
4. 通过 Kubernetes API 声明同等的 `FileInjects`、`AgentProfile`、`AgentTemplate`、`AgentTemplateRevision` 和 `Agent`
5. 控制 Hermes 可以访问哪些外部域名
6. 把 Hermes 配置沉淀为可复用的文件预设、运行时和模板版本
7. 为 Hermes 使用外部站点凭证并查看审计
8. 设置实例数量和 Token 额度
9. 为 `/opt/data` 启用持久化存储
10. 使用 Console API 做批量创建和验证
11. 从 Console 和 Kubernetes 状态中观测 Hermes 实例
12. 基于已发布模板升级单个 Hermes 实例，并验证 PVC 仍挂载同一块盘

---

## 全局前置条件

在开始之前，请准备：

- 一个可用的 TKE 集群
- `kubectl` 和 Helm
- 有权限部署 AgentWay 的集群账号
- 可访问 AgentWay 镜像仓库的网络环境
- 可用的 VPC、子网和安全组
- NAT 网关，用于平台出口访问外部模型服务
- PostgreSQL，生产环境推荐使用腾讯云 PostgreSQL
- 一个 OpenAI-compatible 模型 Provider 的 Base URL、模型名和 API Key
- 一个用于 Agent 访问的系统域名；生产环境建议准备泛域名 DNS 和 TLS

---

## 你将反复填写的参数

| 参数 | 是否必填 | 示例 | 用在什么地方 |
|---|---|---:|---|
| `modelGateway.masterKey` | 是 | `<模型网关密钥>` | 安装 AgentWay / Model Gateway |
| `securityGroups.system.id` | 是 | `sg-xxxxxxxx` | 系统组件安全组 |
| `securityGroups.agent.id` | 是 | `sg-yyyyyyyy` | Agent 实例安全组 |
| `postgres.external.host` | 生产建议 | `10.0.0.10` | 外部 PostgreSQL |
| `privateSubnetId` | 内网 CLB 必填 | `subnet-xxxxxxxx` | Ingress Gateway 内网 CLB |
| 系统域名 | 是 | `agentway.example.com` | Console 和 Agent 访问地址 |
| Agent 泛域名 | 子域名模式必填 | `*.agentway.example.com` | Hermes Dashboard 访问 |
| `MODEL_NAME` | 是 | `glm5` | Hermes 配置文件中的默认模型名，对应模型网关中的网关模型 ID |
| Hermes 镜像 | 是 | `ccr.ccs.tencentyun.com/agentway/hermes:v2026.06.30-r1` | Runtime |

---

## 章节顺序

### 00. 在 TKE 上部署 AgentWay
先把完整控制面、Kubernetes provider、Ingress Gateway、Egress Gateway 和 Model Gateway 准备好。

### 01. 准备 Hermes 需要的平台设置
配置模型网关、系统域名、子域名转发和 DNS。

### 02. 通过 Console 创建 Hermes Dashboard
创建文件预设、运行时、模板、发布版本和实例，让 Hermes 先跑起来。

### 03. 控制 Hermes 的外部访问范围
设置出口访问模式和全局出口规则，限制 Hermes 能访问哪些外部服务。

### 04. 复用 Hermes 配置
把文件、运行时和模板版本沉淀下来，供多个团队或多个实例复用。

### 05. 使用凭证注入和审计 Hermes
为外部站点注册访问凭证，并查看出站流量和工具调用审计。

### 06. 设置实例限额和 Token 额度
控制每个用户可创建的实例数量和模型 Token 使用额度。

### 07. 持久化 Hermes 数据目录
为 `/opt/data` 启用持久化，并验证实例重启后状态仍保留。

### 08. 用 Console API 自动化创建 Hermes
把 Console 页面操作转换成可脚本化的 HTTP API 流程。

### 09. 观测 Hermes 实例和平台资产
从 Console、`kubectl` 和监控看板确认实例、模板、网络规则和资源状态。

### 10. 基于模板升级 Hermes 实例
通过 Console 或 API 对单个实例执行 dryRun 预览和正式升级，并验证 Pod 状态、镜像版本和 PVC 数据。

---

## 为什么按这个顺序阅读

这条主线按实际上手的依赖关系组织：

1. 先有 AgentWay 控制面，否则 Console 和 CRD 都不可用。
2. 再配置模型和访问入口，否则 Hermes 即使启动也不能稳定登录和调用模型。
3. 先创建一个可访问的 Hermes，确认最短链路跑通。
4. 跑通后再收敛外部访问范围，避免一开始把网络问题和应用问题混在一起。
5. 稳定后再讨论复用、凭证、审计、限额、持久化、观测和升级。

---

## 章节入口

- [00. 在 TKE 上部署 AgentWay](./00-deploy-agent-way.md)
- [01. 准备 Hermes 需要的平台设置](./01-prepare-hermes-platform-settings.md)
- [02. 通过 Console 创建 Hermes Dashboard](./02-create-hermes-dashboard-with-console.md)
- [03. 控制 Hermes 的外部访问范围](./03-control-hermes-network-access.md)
- [04. 复用 Hermes 配置](./04-reuse-hermes-configuration.md)
- [05. 使用凭证注入和审计 Hermes](./05-use-credentials-and-audit-hermes.md)
- [06. 设置实例限额和 Token 额度](./06-control-hermes-quotas.md)
- [07. 持久化 Hermes 数据目录](./07-persist-hermes-data-on-tke.md)
- [08. 用 Console API 自动化创建 Hermes](./08-automate-hermes-creation-with-console-api.md)
- [09. 观测 Hermes 实例和平台资产](./09-observe-hermes-assets.md)
- [10. 基于模板升级 Hermes 实例](./10-upgrade-hermes-with-template.md)
