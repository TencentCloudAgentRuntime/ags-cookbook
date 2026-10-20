# AgentWay 客户 Cookbook

这套 Cookbook 是给**客户和交付同学**使用的操作手册。

目标不是解释某一个 CRD 的字段，而是让你按**实际场景**一步一步操作，最终把 AgentWay 的能力真正用起来。

你只需要：
1. 按章节顺序阅读
2. 按说明替换少量必须填写的参数
3. 使用章节指定的方式操作，可能是 Console 表单、完整 YAML 或命令行
4. 按验证步骤确认结果符合预期

请先阅读[版本与能力边界](./openclaw-browser-on-TencentAGS/README.md#版本与能力边界)。operator-only 路径固定使用 `v1.0.15-d5afc116` 镜像与 `d5afc116883d3ffbf9041b09adda39d640e29eb1` 的 CRD；不支持的内容隔离为 `planned-examples/*.yaml.txt`，不能执行。

第 02 章默认创建 3 个 AGS Agent，每个 2 CPU / 4Gi，不预装 Skill，模型调用验收需要真实 Key。Operator 另需至少 16 CPU / 16Gi 可调度余量及系统组件容量。`make setup` / `make run` 和静态校验均不能代替真实 TKE/AGS 端到端验收。

---

## 这套 Cookbook 解决什么问题

AgentWay 的多个 CRD 需要协同工作。只阅读单个对象的 YAML 字段示例时，使用者仍需自行梳理对象关系和操作顺序，不适合第一次上手。

这套 Cookbook 按**客户场景**组织相关能力：
- 先准备集群和 Operator
- 再准备 Tencent Agent Runtime 基础设施
- 然后快速启动一个自带浏览器和角色设定的 OpenClaw
- 再逐步增加访问控制、把常用配置打包复用、学习如何暂停恢复实例，并对存量实例做灰度变更

---

## 目录

```text
agentway-cookbook/
├── README.md
├── agentway-monitoring-dashboard/
│   ├── README.md
│   ├── images/
│   ├── manifests/
│   ├── metrics.md
│   └── performance.md
├── hermes-on-TKE/
│   ├── README.md
│   ├── 00-deploy-agent-way.md
│   ├── 01-prepare-hermes-platform-settings.md
│   ├── 02-create-hermes-dashboard-with-console.md
│   ├── 03-control-hermes-network-access.md
│   ├── 04-reuse-hermes-configuration.md
│   ├── 05-use-credentials-and-audit-hermes.md
│   ├── 06-control-hermes-quotas.md
│   ├── 07-persist-hermes-data-on-tke.md
│   ├── 08-automate-hermes-creation-with-console-api.md
│   ├── 09-observe-hermes-assets.md
│   ├── 10-upgrade-hermes-with-template.md
│   └── images/
├── hermes-dashboard-on-TencentAGS/
│   ├── README.md
│   └── manifests/
└── openclaw-browser-on-TencentAGS/
    ├── README.md
    ├── 00-prepare-cluster-and-deploy-operator.md
    ├── 01-prepare-tencent-agent-runtime.md
    ├── 02-create-openclaw-browser-agent.md
    ├── 03-build-secure-network-access-policy.md
    ├── 04-reduce-agent-config-with-external-references.md
    ├── 05-use-tags-for-chargeback.md
    ├── 06-pause-and-resume-openclaw.md
    ├── 07-roll-out-existing-agents-gradually.md
    ├── 08-publish-openclaw-service-with-agentreplicaset.md
    ├── 09-console-init-ags-provider.md
    ├── 10-observe-agentway-assets-with-exporter.md
    ├── 11-use-explicit-agent-storage.md
    ├── 12-reclaim-timed-openclaw-runtime.md
    └── planned-examples/  # 不可执行的规划材料（*.yaml.txt）
```

---

## 推荐阅读顺序

如果你第一次接触 AgentWay，请按下面顺序操作：

1. [`00-prepare-cluster-and-deploy-operator.md`](./openclaw-browser-on-TencentAGS/00-prepare-cluster-and-deploy-operator.md)
2. [`01-prepare-tencent-agent-runtime.md`](./openclaw-browser-on-TencentAGS/01-prepare-tencent-agent-runtime.md)
3. [`02-create-openclaw-browser-agent.md`](./openclaw-browser-on-TencentAGS/02-create-openclaw-browser-agent.md) —— 快速启动一个自带浏览器和角色设定的 OpenClaw，并通过 `Agent` 名称直接进入它的 AGS shell
4. [`03-build-secure-network-access-policy.md`](./openclaw-browser-on-TencentAGS/03-build-secure-network-access-policy.md) —— 保护 OpenClaw 只访问你允许的目标
5. [`04-reduce-agent-config-with-external-references.md`](./openclaw-browser-on-TencentAGS/04-reduce-agent-config-with-external-references.md) —— 把常用技能、角色和启动配置打包复用
6. [`05-use-tags-for-chargeback.md`](./openclaw-browser-on-TencentAGS/05-use-tags-for-chargeback.md) —— 用 Tags 给不同业务线做分账归属
7. [`06-pause-and-resume-openclaw.md`](./openclaw-browser-on-TencentAGS/06-pause-and-resume-openclaw.md) —— 在不删除实例的前提下暂停与恢复你的 OpenClaw
8. [`07-roll-out-existing-agents-gradually.md`](./openclaw-browser-on-TencentAGS/07-roll-out-existing-agents-gradually.md) —— 为存量 OpenClaw 批量增加 Skill
9. [`08-publish-openclaw-service-with-agentreplicaset.md`](./openclaw-browser-on-TencentAGS/08-publish-openclaw-service-with-agentreplicaset.md) —— 将 OpenClaw 发布为具备稳定入口、多副本和 Affinity ID 运行时亲和能力的服务型 Agent
10. [`09-console-init-ags-provider.md`](./openclaw-browser-on-TencentAGS/09-console-init-ags-provider.md) —— 通过 Console 初始化 AGS Provider 并创建 AGS Agent
11. [`10-observe-agentway-assets-with-exporter.md`](./openclaw-browser-on-TencentAGS/10-observe-agentway-assets-with-exporter.md) —— 使用 agentway-exporter 观测 AgentWay 资产
12. [`11-use-explicit-agent-storage.md`](./openclaw-browser-on-TencentAGS/11-use-explicit-agent-storage.md) —— 显式多存储来源规划，当前版本不支持

如果你要在同一套 Tencent Agent Runtime 底座上启动 Hermes Dashboard，请阅读：

- [`hermes-dashboard-on-TencentAGS/README.md`](./hermes-dashboard-on-TencentAGS/README.md) —— 使用我们提供的正式 Hermes AGS 镜像启动一个可公网访问的 Dashboard Agent

如果你要给已经部署好的 AgentWay 搭建监控面板，请阅读：

- [`agentway-monitoring-dashboard/README.md`](./agentway-monitoring-dashboard/README.md) —— 部署 agentway-exporter、配置 Prometheus 采集、导入 Grafana 面板

如果你要让 AgentService 多副本的连续请求尽量命中同一运行实例，并安全执行滚动升级，请阅读：

- [第 08 章“使用 Affinity ID 维持多副本亲和”](./openclaw-browser-on-TencentAGS/08-publish-openclaw-service-with-agentreplicaset.md#场景六使用-affinity-id-维持多副本亲和) —— 保存并回传最新 Affinity ID，在原实例退出后切换到其他可用实例

如果你要在 TKE 上通过 AgentWay 运行 Hermes Agent，请阅读：

- [`hermes-on-TKE/README.md`](./hermes-on-TKE/README.md) —— 在 TKE 上部署完整 AgentWay 控制面，通过 Console 和 Kubernetes API 创建、运维、升级和观测 Hermes Dashboard

---

## 阅读这套 Cookbook 时要记住什么

- 每一章都是一个**完整场景**
- 每一章都会写清楚：
  - 本章场景
  - 前置章节
  - 需要你填写的参数
  - 具体操作步骤
  - 预期效果
  - 验证方式
- 文档里会提供对应场景的 Console 操作、完整 CRD YAML 或命令行步骤
- 你通常只需要替换少量参数，比如：
  - `SecretId`
  - `SecretKey`
  - `roleArn`
  - `bucketName`
  - 域名或 webhook 地址

---

## 从哪里开始

如果你要创建一个运行在 Tencent Agent Runtime 上、带浏览器的 OpenClaw，请从这里开始：

- [`openclaw-browser-on-TencentAGS/README.md`](./openclaw-browser-on-TencentAGS/README.md)

如果你要启动一个可公网访问的 Hermes Dashboard，请从这里开始：

- [`./hermes-dashboard-on-TencentAGS/README.md`](./hermes-dashboard-on-TencentAGS/README.md)

如果你要给 AgentWay 搭建监控面板，请从这里开始：

- [`./agentway-monitoring-dashboard/README.md`](./agentway-monitoring-dashboard/README.md)

如果你要为 AgentService 多副本使用 Affinity ID，请从这里开始：

- [第 08 章“使用 Affinity ID 维持多副本亲和”](./openclaw-browser-on-TencentAGS/08-publish-openclaw-service-with-agentreplicaset.md#场景六使用-affinity-id-维持多副本亲和)
