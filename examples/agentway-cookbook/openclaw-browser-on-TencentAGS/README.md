# 在 Tencent Agent Runtime 上运行 OpenClaw 浏览器

这条主线会带你从 0 开始，创建一个**运行在 Tencent Agent Runtime 上的 OpenClaw 浏览器 Agent**，并逐步扩展到访问控制、外部引用简化和灰度发布。

---

## 这条主线能帮你完成什么

按顺序完成本目录下的章节后，你可以做到：

1. 准备好 Kubernetes 集群并部署 AgentWay Operator
2. 让平台具备把 Agent 放到 Tencent Agent Runtime 上运行的能力
3. 快速启动一个自带浏览器、技能和角色设定的 OpenClaw
4. 通过 `Agent` CR 名称直接进入对应 AGS 实例的 shell 做验证或排障
5. 保护 OpenClaw 只访问你允许的目标
6. 把常用技能、角色和启动配置打包复用
7. 用 Tags 给不同业务线做分账归属
8. 在不删除实例的前提下暂停与恢复 OpenClaw
9. 为已经在运行的 OpenClaw 批量增加 Skill，或按批触发运行态重启
10. 将 OpenClaw 发布为具备稳定入口和多副本能力的服务型 Agent
11. 在完整控制面 Console 中初始化 AGS Provider，并在运行时/模板中选择 AGS 沙箱
12. 将 OpenClaw 发布为具备稳定入口和多副本能力的服务型 Agent
13. 使用 agentway-exporter 观测 AgentWay 资产
14. 了解新的显式存储挂载模型（提案中）
15. 为临时 OpenClaw 配置 AGS 原生运行时回收

---

## 全局前置条件

在开始之前，请准备：

- 一个可用的 Kubernetes 集群
- `kubectl` 命令行
- 有权限部署 Operator 的集群账号
- Tencent Agent Runtime 所需凭证
- Tencent CFS 文件系统
- 一个可用的 `roleArn`

---

## 你将反复填写的参数

| 参数 | 是否必填 | 示例 | 谁提供 | 用在什么地方 |
|---|---|---:|---|---|
| `SecretId` | 是 | `AKIDxxxxxxxx` | 腾讯云账号管理员 | Tencent Agent Runtime 鉴权 Secret |
| `SecretKey` | 是 | `xxxxxxxx` | 腾讯云账号管理员 | Tencent Agent Runtime 鉴权 Secret |
| `region` | 是 | `ap-shanghai` | 云资源管理员 | Provider 资源 |
| `roleArn` | 是 | `qcs::cam::uin/...:roleName/...` | 云资源管理员 | Tencent Agent Runtime / 镜像拉取 |
| `filesystemId` | 是 | `cfs-xxxxxxxx` | 云资源管理员 | CFS 文件系统 |
| `path` | 否 | `/` | 客户/交付 | CFS 根路径 |
| `webhook URL` | 第 3 章必填 | `http://10.10.10.10:8080/webhook` | 安全策略服务提供方 | Agent 网络访问控制 |

---

## 章节顺序

### 00. 准备集群环境并部署 Operator
先把平台跑起来。

### 01. 准备 Tencent Agent Runtime 基础设施
让后续的 Agent 可以真正运行到 Tencent Agent Runtime 上。

### 02. 快速启动一个自带浏览器、技能和角色设定的 OpenClaw
让业务负责人可以一次性把 OpenClaw 本体、常用 Skill、角色描述和模型配置准备好。

### 03. 保护 OpenClaw 只访问你允许的目标
从域名白名单到审批式访问控制，逐步加固网络边界；如果目标是使用企业私有 CA 的内网 HTTPS 服务，本章也介绍 Trust CA 配置形态（提案中）。

### 04. 把常用技能、角色和启动配置打包复用
把高频重复内容抽出来，后续创建 OpenClaw 时只需要组合引用。

### 05. 用 Tags 给不同业务线做分账归属
让同一套 OpenClaw 在平台治理里具备明确的业务归属信息，方便做分账和统计。

### 06. 在不删除实例的前提下暂停与恢复你的 OpenClaw
让已经在运行的 OpenClaw 可以临时挂起，并在需要时恢复服务。

### 07. 为存量 OpenClaw 批量增加 Skill
当已有多个 OpenClaw 在运行时，用 rollout 分批给它们升级能力；也可以用 `restart-key` 按批触发运行态重启。

### 08. 使用 AgentReplicaSet 和 AgentService 发布服务型 Agent
让 OpenClaw 从单实例变成具备稳定入口和多副本能力的服务。

### 09. 通过 Console 初始化 AGS Provider 并创建 AGS Agent
在完整控制面中初始化 AGS provider，把 AGS sandbox provider 选入运行时和模板，并用同 namespace 的 AgentNetPolicy 约束 AGS Agent。

### 10. 使用 agentway-exporter 观测 AgentWay 资产
部署 exporter，接入 Prometheus，并查看常用指标。

### 11. 显式声明 OpenClaw 的存储挂载
了解如何通过 `storageSources[]` 和 `volumeMounts[].storageSource/subPath/subPathExpr` 声明显式存储来源，并按静态 `subPath` 共享目录，或按 downward API env 生成每个 Agent 的隔离目录。

### 12. 为临时 OpenClaw 配置 AGS 原生运行时回收
只通过 Agent CR 的 `spec.expireAfter` 创建限时 AGS 运行环境，并理解 `status.expiresAt`、自动回收和数据保留边界。

---

## 为什么按这个顺序阅读

这条主线不是随意排列的，而是按客户真正上手时的依赖关系组织的：

1. 你必须先有 Kubernetes 集群和 Operator，否则后面的 CRD 没有人接管。
2. 你必须再准备 Tencent Agent Runtime 基础设施，否则 Agent 虽然能创建对象，但没有可用的远端运行环境。
3. 只有在平台和运行环境都准备好之后，创建 OpenClaw 浏览器 Agent 才有实际意义。
4. Agent 先跑起来之后，你才更容易理解“网络访问控制”是在约束什么对象，以及为什么访问内网 HTTPS 服务时还需要配置上游 Trust CA。
5. 当你已经能成功创建 Agent 后，才有必要讨论如何通过外部引用减少重复配置。
6. 当你已经能稳定创建和复用 OpenClaw 后，就可以开始给它们补上用于分账归属的 Tags。
7. 当 OpenClaw 已经开始承载真实业务时，暂停/恢复会成为日常运维动作。
8. 只有当你已经有存量 Agent 在运行时，灰度发布这个话题才真正成立。
9. 当基础运行链路已经稳定后，可以把单个 OpenClaw 发布为服务型 Agent，验证稳定入口、多副本和 RollingUpgrade 入口不变。
10. 当你使用完整控制面时，可以通过 Console 初始化 AGS provider，并在运行时/模板中选择 AGS 沙箱。
11. 当 AgentWay 已承载真实资产后，再接入 exporter 做资产观测。

---

## manifest 文件在哪里

本目录下所有可以直接执行的 YAML 都放在隔壁目录：

- [`./manifests/`](./manifests/)

以下命令均从 `examples/agentway-cookbook` 目录执行。文档里展示的 YAML 不只是示意，也可以直接使用这些文件：

```bash
kubectl apply -f ./openclaw-browser-on-TencentAGS/manifests/<文件名>.yaml
```

如果你想在第 02 章创建完 Agent 之后立即进入实例 shell，需要先增量开启 AA/connect 服务，并从 AgentWay 源码构建 `kubectl agent` 插件：

```bash
kubectl apply -f ./openclaw-browser-on-TencentAGS/manifests/00-01-connect.yaml
kubectl rollout status deployment/agent-way-connect -n agent-way-system

git clone --depth 1 --branch v1.0.15-d5afc116 \
  https://github.com/TencentCloudAgentRuntime/agentway.git agentway-v1.0.15-d5afc116
cd agentway-v1.0.15-d5afc116/operator
go build -o ./bin/kubectl-agent ./cmd/kubectl-agent
mkdir -p "$HOME/.local/bin"
install -m 755 ./bin/kubectl-agent "$HOME/.local/bin/kubectl-agent"
export PATH="$HOME/.local/bin:$PATH"

kubectl agent exec -n default openclaw-browser-agent
```

该插件会自动通过 `kubectl proxy` 连接 `connect.agentway.io/v1alpha1` 聚合 API；你只需要提供 `Agent` 的 namespace 和 name，不需要手动查找 sandbox ID，也不需要本地直连 AGS 数据面。

---

## 章节入口

- [00. 准备集群环境并部署 Operator](./00-prepare-cluster-and-deploy-operator.md)
- [01. 准备 Tencent Agent Runtime 基础设施](./01-prepare-tencent-agent-runtime.md)
- [02. 快速启动一个自带浏览器、技能和角色设定的 OpenClaw](./02-create-openclaw-browser-agent.md)
- [03. 保护 OpenClaw 只访问你允许的目标，或访问使用私有 CA 的内网 HTTPS 服务](./03-build-secure-network-access-policy.md)
- [04. 把常用技能、角色和启动配置打包复用](./04-reduce-agent-config-with-external-references.md)
- [05. 用 Tags 给不同业务线做分账归属](./05-use-tags-for-chargeback.md)
- [06. 在不删除实例的前提下暂停与恢复你的 OpenClaw](./06-pause-and-resume-openclaw.md)
- [07. 为存量 OpenClaw 批量增加 Skill](./07-roll-out-existing-agents-gradually.md)
- [08. 使用 AgentReplicaSet 和 AgentService 发布服务型 Agent](./08-publish-openclaw-service-with-agentreplicaset.md)
- [09. 通过 Console 初始化 AGS Provider 并创建 AGS Agent](./09-console-init-ags-provider.md)
- [10. 使用 agentway-exporter 观测 AgentWay 资产](./10-observe-agentway-assets-with-exporter.md)
- [11. 显式声明 OpenClaw 的存储挂载（提案中）](./11-use-explicit-agent-storage.md)
- [12. 为 OpenClaw 设置 AGS 原生运行时回收](./12-reclaim-timed-openclaw-runtime.md)
