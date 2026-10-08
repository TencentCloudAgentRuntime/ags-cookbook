# 在 Tencent Agent Runtime 上运行 OpenClaw 浏览器

这条主线会带你从 0 开始，创建一个**运行在 Tencent Agent Runtime 上的 OpenClaw 浏览器 Agent**，并逐步扩展到访问控制、外部引用简化和灰度发布。

---

## 这条主线能帮你完成什么

按顺序完成当前版本支持的章节，你可以：

1. 部署 Operator 并准备 AGS Provider
2. 启动带浏览器和角色设定的 OpenClaw，配置真实模型 Key 后验收模型调用
3. 通过 `Agent` CR 名称进入 AGS shell
4. 配置出站网络策略、复用技能/文件配置和 Tags
5. 暂停与恢复实例，对存量 Agent 分批升级技能或镜像
6. 使用 AgentReplicaSet 和 AgentService 创建多副本服务与稳定入口
7. 接入 Console 或 exporter，管理和观测资产

## 版本与能力边界

本目录 operator-only 路径固定使用镜像 `v1.0.15-d5afc116`，配套源码和 CRD 来自完整 SHA `d5afc116883d3ffbf9041b09adda39d640e29eb1`，不是同名 Git tag。

| 内容 | 固定版本状态 |
|---|---|
| `volumeMounts[].subpath`（小写） | 支持；省略时按 UID 隔离，填写时固定到文件系统内指定路径 |
| 第 02 章模型调用 | 需要真实模型 Key；默认创建 3 个 AGS Agent，不预装 Skill |
| 第 03 章 `accessPolicy` / `trustCARefs` | 不支持，仅规划 |
| 第 07/08 章 `agentReplicaSetName` / `agentMetadataStrategicPatch` | 不支持，仅规划；现有 Agent 可用 selector rollout |
| `agentServiceOldBackendDetachTiming` | 不支持，使用固定版本默认切换时序 |
| 第 11 章显式多存储来源 | 不支持，仅规划 |
| 第 12 章 `expireAfter` 自动回收 | 不支持，仅规划，当前版本需显式清理 |

规划材料放在 `planned-examples/*.yaml.txt`，不能作为当前版本可执行步骤。`manifests/` 仅保留与固定 CRD 字段匹配的清单。字段兼容校验不等于真实集群端到端验证；请按各章验收步骤验证运行结果。

---

## 全局前置条件

在开始之前，请准备：

- 一个可用的 Kubernetes 集群，至少预留 16 CPU / 16Gi 给 2 个 Operator Pod（每个 8 CPU / 8Gi），另需系统组件容量
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

### 02. 快速启动一个自带浏览器和角色设定的 OpenClaw
准备 OpenClaw、角色描述和模型配置；默认不预装 Skill，模型调用验收需要真实 Key。

### 03. 保护 OpenClaw 只访问你允许的目标
从域名白名单到审批式访问控制，逐步加固网络边界；如果目标是使用企业私有 CA 的内网 HTTPS 服务，本章将入站策略和 Trust CA 标为当前版本不支持的规划内容。

### 04. 把常用技能、角色和启动配置打包复用
把高频重复内容抽出来，后续创建 OpenClaw 时只需要组合引用。

### 05. 用 Tags 给不同业务线做分账归属
让同一套 OpenClaw 在平台治理里具备明确的业务归属信息，方便做分账和统计。

### 06. 在不删除实例的前提下暂停与恢复你的 OpenClaw
让已经在运行的 OpenClaw 可以临时挂起，并在需要时恢复服务。

### 07. 为存量 OpenClaw 批量增加 Skill
当已有多个 OpenClaw 在运行时，用 selector rollout 分批升级技能或镜像；批量写入 restart-key 的接口不受固定版本支持。

### 08. 使用 AgentReplicaSet 和 AgentService 发布服务型 Agent
让 OpenClaw 从单实例变成具备稳定入口和多副本能力的服务。

### 09. 通过 Console 初始化 AGS Provider 并创建 AGS Agent
在完整控制面中初始化 AGS provider，把 AGS sandbox provider 选入运行时和模板，并用同 namespace 的 AgentNetPolicy 约束 AGS Agent。

### 10. 使用 agentway-exporter 观测 AgentWay 资产
部署 exporter，接入 Prometheus，并查看常用指标。

### 11. 显式多存储来源（规划）
说明未来设计与当前 `subpath` 写法的区别，不提供当前版本部署步骤。

### 12. 限时运行与自动回收（规划）
固定版本不支持 `expireAfter`；说明显式清理方式及未来版本的验收要求。

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

以下命令均从 `examples/agentway-cookbook` 目录执行；只应用当前章节明确支持的文件，不要批量应用整个目录：

```bash
kubectl apply -f ./openclaw-browser-on-TencentAGS/manifests/<文件名>.yaml
```

如果你想在第 02 章创建完 Agent 之后立即进入实例 shell，需要先增量开启 AA/connect 服务，并从 AgentWay 源码构建 `kubectl agent` 插件：

```bash
kubectl apply -f ./openclaw-browser-on-TencentAGS/manifests/00-01-connect.yaml
kubectl rollout status deployment/agent-way-connect -n agent-way-system

# 复用第 00 章按完整 SHA 获取的源码目录。
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
- [02. 快速启动一个自带浏览器和角色设定的 OpenClaw](./02-create-openclaw-browser-agent.md)
- [03. 出站网络策略，以及入站/私有 CA 规划](./03-build-secure-network-access-policy.md)
- [04. 把常用技能、角色和启动配置打包复用](./04-reduce-agent-config-with-external-references.md)
- [05. 用 Tags 给不同业务线做分账归属](./05-use-tags-for-chargeback.md)
- [06. 在不删除实例的前提下暂停与恢复你的 OpenClaw](./06-pause-and-resume-openclaw.md)
- [07. 为存量 OpenClaw 批量增加 Skill](./07-roll-out-existing-agents-gradually.md)
- [08. 使用 AgentReplicaSet 和 AgentService 发布服务型 Agent](./08-publish-openclaw-service-with-agentreplicaset.md)
- [09. 通过 Console 初始化 AGS Provider 并创建 AGS Agent](./09-console-init-ags-provider.md)
- [10. 使用 agentway-exporter 观测 AgentWay 资产](./10-observe-agentway-assets-with-exporter.md)
- [11. 显式多存储来源（规划，当前版本不支持）](./11-use-explicit-agent-storage.md)
- [12. 自动回收（规划，当前版本不支持）](./12-reclaim-timed-openclaw-runtime.md)
