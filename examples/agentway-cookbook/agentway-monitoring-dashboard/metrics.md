# AgentWay Exporter 指标列表

本文档描述 `agentway-exporter` 当前暴露的指标、标签、含义和统计口径。它面向客户侧监控接入和 Grafana 面板排障使用。

> 说明：`clusterID` 不是 exporter 自身输出的业务标签，而是由 Prometheus 采集配置注入，例如 `ServiceMonitor.relabelings` 或 `scrape_configs.static_configs.labels`。多集群看板请始终按 `clusterID` 过滤。

---

## 通用标签约定

| 标签 | 出现位置 | 含义 |
|---|---|---|
| `clusterID` | Prometheus 采集后附加 | 集群 ID，用于多集群区分 |
| `namespace` | AgentWay 资产指标 | Kubernetes namespace |
| `agent` | Agent 指标 | Agent CR 名称 |
| `sandbox_id` | sandbox / usage / 网络策略同步指标 | Agent 底层 sandbox 实例 ID；Agent 未分配 sandbox 时为空字符串 |
| `agentnetpolicy` | AgentNetPolicy 指标 | AgentNetPolicy CR 名称 |
| `agentrollout` | AgentRollout 指标 | AgentRollout CR 名称 |
| `template` | AgentRollout 指标 | Rollout 使用的 `spec.templateRef` |
| `phase` | 当前状态标签 | 当前状态对应的序列值恒为 `1`；非当前状态不再输出 0 值 series |
| `type` / `status` | condition 指标 | Kubernetes condition 的类型和状态 |
| `reason` | Agent condition 可选标签 | 仅当 `AGENTWAY_EXPORTER_TAG_LABELS_EXPOSE_CONDITION_REASON` 类配置开启时暴露；默认不建议开启高基数 reason |
| `tag_xxx` | `agentway_agent_tags` | Agent `spec.tags` 的 key 经合法化后生成的标签名 |
| `label_xxx` | `agentway_agent_labels` | Agent Kubernetes metadata label 的 key 经合法化后生成的标签名 |

### kube-state-metrics 风格的 tags / labels

Agent 主状态指标不会直接展开 `tag_xxx` 或 `label_xxx`，避免所有指标都被动态业务维度污染。过滤时使用 metadata gauge 做 join：

```promql
agentway_agent_info{clusterID="cls-xxx"}
  and on(namespace, agent) agentway_agent_labels{label_app="openclaw"}
  and on(namespace, agent) agentway_agent_tags{tag_env="prod"}
```

标签 key 合法化规则：加前缀并把非法字符替换成 `_`。例如：

| 原始 key | 指标标签名 |
|---|---|
| tag `team.name/owner` | `tag_team_name_owner` |
| Kubernetes label `app.kubernetes.io/name` | `label_app_kubernetes_io_name` |

---

## Exporter 自身指标

| 指标 | 类型 | 标签 | 含义 | 统计口径 |
|---|---|---|---|---|
| `agentway_exporter_build_info` | Gauge | `version`, `commit` | exporter 构建信息 | 固定值 `1`。当前实现默认 `version=dev`、`commit=unknown` |
| `agentway_exporter_scrape_build_duration_seconds` | Gauge | 无 | exporter 构建一次 `/metrics` 响应消耗的时间 | 每次 Prometheus scrape 时，统计 collector 从开始收集到生成完指标的耗时，单位秒 |
| `agentway_exporter_cr_cache_objects` | Gauge | `resource` | exporter 当前能从本地 cache/list 看到的 CR 对象数 | 分别 list `agents`、`agentnetpolicies`、`agentrollouts`，值为对象数量 |
| `agentway_exporter_last_successful_cr_sync_timestamp_seconds` | Gauge | `resource` | 最近一次成功读取 CR cache 的时间 | 每次某类 CR list 成功时写当前 Unix 时间戳，单位秒 |
| `agentway_exporter_runtime_metric_cache_entries` | Gauge | 无 | 运行时指标 cache 条目数 | `UsageCache` 中按 `sandbox_id` 缓存的运行时指标样本数量；未启用 Barad/usage cache 时不暴露或为 0 |
| `agentway_exporter_barad_cache_entries` | Gauge | 无 | 兼容别名 | 已废弃，当前与 `agentway_exporter_runtime_metric_cache_entries` 数值相同 |

---

## Agent 基础状态指标

| 指标 | 类型 | 标签 | 含义 | 统计口径 |
|---|---|---|---|---|
| `agentway_agent_info` | Gauge | `namespace`, `agent` | Agent 身份信息 | 每个 Agent 输出一条，值恒为 `1` |
| `agentway_agent_phase` | Gauge | `namespace`, `agent`, `phase` | Agent 生命周期状态 | 仅输出当前 `status.phase` 对应的一条 series，值恒为 `1`；`status.phase` 为空时输出 `phase="Unknown"` |
| `agentway_agent_condition` | Gauge | `namespace`, `agent`, `type`, `status`，可选 `reason` | Agent condition 状态 | 遍历 `status.conditions`；当 condition 的 `status=True` 时值为 `1`，否则为 `0` |
| `agentway_agent_tags` | Gauge | `namespace`, `agent`, 动态 `tag_xxx` | Agent `spec.tags` 元数据 | 每个 Agent 输出一条，值恒为 `1`；tag key 经合法化、去重、数量和长度限制后作为标签 |
| `agentway_agent_labels` | Gauge | `namespace`, `agent`, 动态 `label_xxx` | Agent Kubernetes metadata labels 元数据 | 每个 Agent 输出一条，值恒为 `1`；metadata label key 经合法化、去重、数量和长度限制后作为标签 |

---

## Agent sandbox 与资源使用指标

| 指标 | 类型 | 标签 | 含义 | 统计口径 |
|---|---|---|---|---|
| `agentway_agent_sandbox_alive` | Gauge | `namespace`, `agent`, `sandbox_id` | sandbox 是否被认为存活 | 当 Agent `status.phase=Running` 且 `status.sandboxID` 非空时为 `1`，否则为 `0` |
| `agentway_agent_resource_requests_cpu_cores` | Gauge | `namespace`, `agent`, `sandbox_id` | Agent CPU request | 从 `spec.resources.cpu` 解析，单位 core。当前 request 和 limit 使用同一份 Agent resource 配置 |
| `agentway_agent_resource_limits_cpu_cores` | Gauge | `namespace`, `agent`, `sandbox_id` | Agent CPU limit | 从 `spec.resources.cpu` 解析，单位 core。当前 request 和 limit 使用同一份 Agent resource 配置 |
| `agentway_agent_resource_requests_memory_bytes` | Gauge | `namespace`, `agent`, `sandbox_id` | Agent memory request | 从 `spec.resources.memory` 解析，单位 byte。当前 request 和 limit 使用同一份 Agent resource 配置 |
| `agentway_agent_resource_limits_memory_bytes` | Gauge | `namespace`, `agent`, `sandbox_id` | Agent memory limit | 从 `spec.resources.memory` 解析，单位 byte。当前 request 和 limit 使用同一份 Agent resource 配置 |
| `agentway_agent_cpu_usage_percent` | Gauge | `namespace`, `agent`, `sandbox_id` | sandbox CPU 使用率 | 来自 Barad/云监控 `SandboxCpuUsagePercent`；单位 `%`，多核场景可超过 100%；仅当 cache 中有新鲜样本时输出 |
| `agentway_agent_cpu_usage_cores` | Gauge | `namespace`, `agent`, `sandbox_id` | sandbox CPU 已使用核数 | 来自 Barad/云监控 `SandboxCpuUsedCores`；仅当 cache 中有新鲜样本时输出 |
| `agentway_agent_memory_usage_percent` | Gauge | `namespace`, `agent`, `sandbox_id` | sandbox memory 使用率 | 来自 Barad/云监控 `SandboxMemoryUsagePercent`；单位 `%`；仅当 cache 中有新鲜样本时输出 |
| `agentway_agent_memory_usage_bytes` | Gauge | `namespace`, `agent`, `sandbox_id` | sandbox memory 已使用字节数 | 来自 Barad/云监控 `SandboxMemoryUsedBytes`；仅当 cache 中有新鲜样本时输出 |
| `agentway_agent_disk_read_bytes_per_second` | Gauge | `namespace`, `agent`, `sandbox_id` | 磁盘读速率 | 来自 Barad/云监控 `SandboxDiskReadBytesPerSecond`；单位 Bytes/s；仅当 cache 中有新鲜样本时输出 |
| `agentway_agent_disk_write_bytes_per_second` | Gauge | `namespace`, `agent`, `sandbox_id` | 磁盘写速率 | 来自 Barad/云监控 `SandboxDiskWriteBytesPerSecond`；单位 Bytes/s；仅当 cache 中有新鲜样本时输出 |
| `agentway_agent_filesystem_usage_percent` | Gauge | `namespace`, `agent`, `sandbox_id` | 文件系统使用率 | 来自 Barad/云监控 `SandboxFsUsagePercent`；单位 `%`；仅当 cache 中有新鲜样本时输出 |
| `agentway_agent_filesystem_used_bytes` | Gauge | `namespace`, `agent`, `sandbox_id` | 文件系统已使用字节数 | 来自 Barad/云监控 `SandboxFsUsedBytes`；仅当 cache 中有新鲜样本时输出 |
| `agentway_agent_network_receive_bytes_per_second` | Gauge | `namespace`, `agent`, `sandbox_id` | 网络入方向速率 | 来自 Barad/云监控 `SandboxNetworkRxBytesPerSecond`；单位 Bytes/s；仅当 cache 中有新鲜样本时输出 |
| `agentway_agent_network_transmit_bytes_per_second` | Gauge | `namespace`, `agent`, `sandbox_id` | 网络出方向速率 | 来自 Barad/云监控 `SandboxNetworkTxBytesPerSecond`；单位 Bytes/s；仅当 cache 中有新鲜样本时输出 |
| `agentway_agent_sandbox_metrics_available` | Gauge | `namespace`, `agent`, `sandbox_id` | usage 数据是否新鲜可用 | 当 usage cache 存在该 `sandbox_id` 且样本年龄不超过 `AGENTWAY_EXPORTER_BARAD_CACHE_TTL` 时为 `1`，否则为 `0` |
| `agentway_agent_sandbox_metrics_cache_age_seconds` | Gauge | `namespace`, `agent`, `sandbox_id` | usage cache 年龄 | 当前时间减去 cache 样本 `LastSuccess`；无样本时为 `0`，有过期样本时输出实际年龄，单位秒 |

### CPU / 内存使用率统计

exporter 直接输出 usage 和 limit，不直接输出百分比。Grafana 面板使用 PromQL 计算：

```promql
100 * agentway_agent_cpu_usage_cores
  / clamp_min(agentway_agent_resource_limits_cpu_cores, 0.001)
```

```promql
100 * agentway_agent_memory_usage_bytes
  / clamp_min(agentway_agent_resource_limits_memory_bytes, 1)
```

---

## Agent Skill / Plugin / FileInject / Bootstrap 过程指标

| 指标 | 类型 | 标签 | 含义 | 统计口径 |
|---|---|---|---|---|
| `agentway_agent_skill_applied_count` | Gauge | `namespace`, `agent` | 已成功应用的 Skill 数 | 来自 `status.skillStatus.appliedCount`；无 `skillStatus` 时为 `0` |
| `agentway_agent_skill_total_count` | Gauge | `namespace`, `agent` | 期望/总 Skill 数 | 来自 `status.skillStatus.totalCount`；无 `skillStatus` 时为 `0` |
| `agentway_agent_plugin_applied_count` | Gauge | `namespace`, `agent` | 已成功应用的 Plugin 数 | 来自 `status.pluginStatus.appliedCount`；无 `pluginStatus` 时为 `0` |
| `agentway_agent_plugin_total_count` | Gauge | `namespace`, `agent` | 期望/总 Plugin 数 | 来自 `status.pluginStatus.totalCount`；无 `pluginStatus` 时为 `0` |
| `agentway_agent_fileinject_applied_count` | Gauge | `namespace`, `agent` | 已成功注入的文件数 | 来自 `status.fileInjectStatus.appliedCount`；无 `fileInjectStatus` 时为 `0` |
| `agentway_agent_fileinject_total_count` | Gauge | `namespace`, `agent` | 期望/总文件注入数 | 来自 `status.fileInjectStatus.totalCount`；无 `fileInjectStatus` 时为 `0` |
| `agentway_agent_asset_phase` | Gauge | `namespace`, `agent`, `asset`, `phase` | Agent 子资产处理阶段 | 每个 `asset` 仅输出当前 phase 对应的一条 series，值恒为 `1`。`asset` 枚举：`skills`、`plugins`、`fileInjects`、`bootstrap`；对应 status 不存在时 phase 使用 `None` |

---

## Agent 网络策略同步指标

| 指标 | 类型 | 标签 | 含义 | 统计口径 |
|---|---|---|---|---|
| `agentway_agent_network_policy_stale` | Gauge | `namespace`, `agent`, `sandbox_id` | Agent 网络策略是否需要重新同步 | 来自 `status.networkPolicyStale`；`true` 为 `1`，`false` 为 `0` |
| `agentway_agent_network_policy_last_sync_timestamp_seconds` | Gauge | `namespace`, `agent`, `sandbox_id` | Agent 网络策略最近一次成功同步时间 | 来自 `status.lastNetworkPolicySyncTime`，Unix 时间戳，单位秒；字段为空时不输出该序列 |
| `agentway_agent_network_policy_last_failure_timestamp_seconds` | Gauge | `namespace`, `agent`, `sandbox_id` | Agent 网络策略最近一次失败同步时间 | 来自 `status.lastNetworkPolicySyncFailedTime`，Unix 时间戳，单位秒；字段为空时不输出该序列 |

常用排障 PromQL：

```promql
agentway_agent_network_policy_stale{clusterID="cls-xxx"} == 1
```

```promql
time() - agentway_agent_network_policy_last_sync_timestamp_seconds{clusterID="cls-xxx"}
```

---

## AgentNetPolicy 指标

| 指标 | 类型 | 标签 | 含义 | 统计口径 |
|---|---|---|---|---|
| `agentway_agentnetpolicy_info` | Gauge | `namespace`, `agentnetpolicy` | AgentNetPolicy 身份信息 | 每个 AgentNetPolicy 输出一条，值恒为 `1` |
| `agentway_agentnetpolicy_phase` | Gauge | `namespace`, `agentnetpolicy`, `phase` | AgentNetPolicy 当前阶段 | 仅输出当前 `status.phase` 对应的一条 series，值恒为 `1`；`status.phase` 为空时输出 `phase="Unknown"` |
| `agentway_agentnetpolicy_condition` | Gauge | `namespace`, `agentnetpolicy`, `type`, `status` | AgentNetPolicy condition 状态 | 遍历 `status.conditions`；condition `status=True` 时值为 `1`，否则为 `0` |
| `agentway_agentnetpolicy_condition_last_transition_time_seconds` | Gauge | `namespace`, `agentnetpolicy`, `type`, `status` | AgentNetPolicy condition 最近一次变化时间 | 来自 condition `lastTransitionTime`，Unix 时间戳，单位秒 |
| `agentway_agentnetpolicy_metadata_generation` | Gauge | `namespace`, `agentnetpolicy` | AgentNetPolicy 当前 spec generation | 来自 CR `metadata.generation`；spec 更新时递增，可与 `observed_generation` 对比判断 controller 是否处理到最新 spec |
| `agentway_agentnetpolicy_observed_generation` | Gauge | `namespace`, `agentnetpolicy` | controller 已观测到的 generation | 来自 `status.observedGeneration`；可与 CR `metadata.generation` 对比判断 controller 是否处理到最新 spec |

---

## AgentRollout 指标

| 指标 | 类型 | 标签 | 含义 | 统计口径 |
|---|---|---|---|---|
| `agentway_agentrollout_info` | Gauge | `namespace`, `agentrollout`, `template` | AgentRollout 身份信息 | 每个 AgentRollout 输出一条，值恒为 `1`；`template` 来自 `spec.templateRef` |
| `agentway_agentrollout_phase` | Gauge | `namespace`, `agentrollout`, `template`, `phase` | AgentRollout 当前阶段 | 仅输出当前 `status.phase` 对应的一条 series，值恒为 `1`；`status.phase` 为空时输出 `phase="Unknown"` |
| `agentway_agentrollout_matched_agents` | Gauge | `namespace`, `agentrollout`, `template` | 匹配 rollout selector 的 Agent 数 | 来自 `status.matchedAgents` |
| `agentway_agentrollout_planned_agents` | Gauge | `namespace`, `agentrollout`, `template` | 本次计划处理的 Agent 数 | 来自 `status.plannedAgents` |
| `agentway_agentrollout_updated_agents` | Gauge | `namespace`, `agentrollout`, `template` | 已更新的 Agent 数 | 来自 `status.updatedAgents` |
| `agentway_agentrollout_would_update_agents` | Gauge | `namespace`, `agentrollout`, `template` | dry-run 下预计会更新的 Agent 数 | 来自 `status.wouldUpdateAgents` |
| `agentway_agentrollout_unchanged_agents` | Gauge | `namespace`, `agentrollout`, `template` | 已匹配但无需变更的 Agent 数 | 来自 `status.unchangedAgents` |
| `agentway_agentrollout_ready_agents` | Gauge | `namespace`, `agentrollout`, `template` | 更新后 Ready 的 Agent 数 | 来自 `status.readyAgents` |
| `agentway_agentrollout_available_agents` | Gauge | `namespace`, `agentrollout`, `template` | 更新后 Available 的 Agent 数 | 来自 `status.availableAgents` |
| `agentway_agentrollout_failed_agents` | Gauge | `namespace`, `agentrollout`, `template` | 更新失败的 Agent 数 | 来自 `status.failedAgents` |
| `agentway_agentrollout_dry_run` | Gauge | `namespace`, `agentrollout`, `template` | 是否 dry-run | 来自 `status.dryRun`；`true` 为 `1`，`false` 为 `0` |
| `agentway_agentrollout_paused` | Gauge | `namespace`, `agentrollout`, `template` | rollout 是否暂停 | 来自 `status.paused`；`true` 为 `1`，`false` 为 `0` |
| `agentway_agentrollout_completed` | Gauge | `namespace`, `agentrollout`, `template` | rollout 是否完成 | 来自 `status.completed`；`true` 为 `1`，`false` 为 `0` |
| `agentway_agentrollout_observed_generation` | Gauge | `namespace`, `agentrollout`, `template` | controller 已观测到的 generation | 来自 `status.observedGeneration` |
| `agentway_agentrollout_condition` | Gauge | `namespace`, `agentrollout`, `type`, `status` | AgentRollout condition 状态 | 遍历 `status.conditions`；condition `status=True` 时值为 `1`，否则为 `0` |
| `agentway_agentrollout_condition_last_transition_time_seconds` | Gauge | `namespace`, `agentrollout`, `type`, `status` | AgentRollout condition 最近一次变化时间 | 来自 condition `lastTransitionTime`，Unix 时间戳，单位秒 |

---

## 统计与刷新周期

| 数据类型 | 来源 | 刷新/统计口径 |
|---|---|---|
| Agent / AgentNetPolicy / AgentRollout 状态 | Kubernetes CR status | exporter 每次被 Prometheus scrape 时从 controller-runtime client cache/list 当前对象并生成 gauge |
| tags / labels metadata | Agent spec tags / metadata labels | 每次 scrape 基于当前 Agent 集合计算 tag/label 并输出 kube-state-metrics 风格 gauge |
| sandbox usage | Barad / 云监控 | exporter 后台按 `AGENTWAY_EXPORTER_BARAD_SYNC_INTERVAL` 周期性同步；默认 1 分钟。每次按 sandbox ID 批量查询 `AGENTWAY_EXPORTER_BARAD_QUERY_WINDOW` 窗口内数据并写 cache |
| usage 可用性 | exporter UsageCache | scrape 时判断 cache 样本年龄是否小于等于 `AGENTWAY_EXPORTER_BARAD_CACHE_TTL`；默认 5 分钟 |
| Prometheus 采集 | Prometheus scrape | cookbook 示例默认 `scrape_interval=30s`、`scrape_timeout=10s` |

---

## 常用组合查询

### 找出异常 Agent

```promql
agentway_agent_phase{clusterID="cls-xxx", phase=~"Failed|Unknown|Pending"} == 1
```

### 找出 sandbox usage 数据不可用的 Agent

```promql
agentway_agent_sandbox_metrics_available{clusterID="cls-xxx"} == 0
```

### 找出失败的网络策略

```promql
agentway_agentnetpolicy_phase{clusterID="cls-xxx", phase="Failed"} == 1
```

### 找出失败或退化的 rollout

```promql
agentway_agentrollout_phase{clusterID="cls-xxx", phase=~"Failed|Degraded"} == 1
```

### 查看 rollout 更新进度

```promql
agentway_agentrollout_updated_agents{clusterID="cls-xxx"}
/
clamp_min(agentway_agentrollout_planned_agents{clusterID="cls-xxx"}, 1)
```

---

## Series 数量估算

这里的 series 指 Prometheus 中一组唯一 labelset 对应的一条时间序列。`clusterID` 由 Prometheus 采集侧追加；单集群内按下面公式估算，多集群场景下对每个 `clusterID` 分别计算后求和。

### 变量定义

| 符号 | 含义 |
|---|---|
| `A` | Agent 数量 |
| `N` | AgentNetPolicy 数量 |
| `R` | AgentRollout 数量 |
| `C_agent(i)` | 第 `i` 个 Agent 当前 `status.conditions` 条数 |
| `C_np(i)` | 第 `i` 个 AgentNetPolicy 当前 `status.conditions` 条数 |
| `C_rollout(i)` | 第 `i` 个 AgentRollout 当前 `status.conditions` 条数 |
| `Res(i)` | 第 `i` 个 Agent 是否有可解析的 `spec.resources`；有则为 `1`，否则为 `0` |
| `Usage(i)` | 第 `i` 个 Agent 是否有新鲜 Barad usage cache；有则为 `1`，否则为 `0` |
| `M_runtime` | exporter 拉取并暴露的 Barad runtime 指标数量，当前为 `10` |
| `Sync(i)` | 第 `i` 个 Agent 是否有 `status.lastNetworkPolicySyncTime`；有则为 `1`，否则为 `0` |
| `SyncFail(i)` | 第 `i` 个 Agent 是否有 `status.lastNetworkPolicySyncFailedTime`；有则为 `1`，否则为 `0` |
| `BaradEnabled` | exporter 是否启用了 usage cache；启用为 `1`，否则为 `0` |

### Exporter 自身固定 series

在三个 CR list 都成功时，exporter 自身指标约为：

```text
S_exporter = 2 + 3 + 3 + 2 * BaradEnabled
```

含义：

| 部分 | series 数 |
|---|---:|
| `agentway_exporter_build_info`、`agentway_exporter_scrape_build_duration_seconds` | `2` |
| `agentway_exporter_cr_cache_objects{resource=...}`，resource 为 agents / agentnetpolicies / agentrollouts | `3` |
| `agentway_exporter_last_successful_cr_sync_timestamp_seconds{resource=...}` | `3` |
| `agentway_exporter_runtime_metric_cache_entries` | `BaradEnabled` |
| `agentway_exporter_barad_cache_entries` 兼容别名 | `BaradEnabled` |

所以通常：

```text
S_exporter = 10
```

如果未启用 Barad usage cache，则通常为：

```text
S_exporter = 8
```

### 单个 Agent 的 series 数

单个 Agent 的 series 由下面几部分组成：

| 指标组 | series 数 | 说明 |
|---|---:|---|
| `agentway_agent_info` | `1` | 每个 Agent 一条 |
| `agentway_agent_tags` | `1` | 每个 Agent 一条；tag key/value 作为 label，不是每个 tag 一条 |
| `agentway_agent_labels` | `1` | 每个 Agent 一条；Kubernetes label key/value 作为 label，不是每个 label 一条 |
| `agentway_agent_phase` | `1` | 仅当前 Agent phase 一条 |
| `agentway_agent_sandbox_alive` | `1` | 每个 Agent 一条 |
| resource request/limit | `4 * Res(i)` | CPU request、CPU limit、memory request、memory limit |
| runtime usage | `M_runtime * Usage(i)` | 仅 cache 新鲜可用时输出当前 10 个 Barad runtime 指标 |
| `agentway_agent_sandbox_metrics_available` | `1` | 每个 Agent 一条 |
| `agentway_agent_sandbox_metrics_cache_age_seconds` | `1` | 每个 Agent 一条 |
| skill applied/total | `2` | applied、total |
| skill asset phase | `1` | 仅当前 phase 一条 |
| plugin applied/total | `2` | applied、total |
| plugin asset phase | `1` | 仅当前 phase 一条 |
| fileInject applied/total | `2` | applied、total |
| fileInject asset phase | `1` | 仅当前 phase 一条 |
| bootstrap asset phase | `1` | 仅当前 phase 一条 |
| `agentway_agent_network_policy_stale` | `1` | 每个 Agent 一条 |
| network policy sync timestamp | `Sync(i)` | 有成功同步时间才输出 |
| network policy failure timestamp | `SyncFail(i)` | 有失败同步时间才输出 |
| `agentway_agent_condition` | `C_agent(i)` | 每个现有 condition 一条 |

因此单个 Agent 的计算公式是：

```text
S_agent(i) = 18
           + 4 * Res(i)
           + M_runtime * Usage(i)
           + Sync(i)
           + SyncFail(i)
           + C_agent(i)
```

常见情况：Agent 有 resources、没有新鲜 usage、没有网络策略同步时间、没有 condition：

```text
S_agent(i) = 18 + 4 = 22
```

如果 Agent 有 resources、有新鲜 usage、有成功同步时间、有失败同步时间、有 3 条 condition：

```text
S_agent(i) = 18 + 4 + 2 + 1 + 1 + 3 = 29
```

> 注意：`agentway_agent_tags` 和 `agentway_agent_labels` 各自仍然只是一条 active series / Agent。但如果 tag 或 label 的 key/value 高频变化，会产生历史 series churn，增加 Prometheus 长期存储压力。

### 单个 AgentNetPolicy 的 series 数

单个 AgentNetPolicy 的指标包括：

| 指标组 | series 数 | 说明 |
|---|---:|---|
| `agentway_agentnetpolicy_info` | `1` | 每个策略一条 |
| `agentway_agentnetpolicy_phase` | `1` | 仅当前 phase 一条 |
| `agentway_agentnetpolicy_metadata_generation` | `1` | 每个策略一条 |
| `agentway_agentnetpolicy_observed_generation` | `1` | 每个策略一条 |
| `agentway_agentnetpolicy_condition` | `C_np(i)` | 每个 condition 一条 |
| `agentway_agentnetpolicy_condition_last_transition_time_seconds` | `C_np(i)` | 每个 condition 一条 |

公式：

```text
S_agentnetpolicy(i) = 4 + 2 * C_np(i)
```

例如策略有 2 条 condition：

```text
S_agentnetpolicy(i) = 4 + 2 * 2 = 8
```

### 单个 AgentRollout 的 series 数

单个 AgentRollout 的指标包括：

| 指标组 | series 数 | 说明 |
|---|---:|---|
| `agentway_agentrollout_info` | `1` | 每个 rollout 一条 |
| `agentway_agentrollout_phase` | `1` | 仅当前 phase 一条 |
| rollout 计数 / bool / generation 指标 | `12` | matched、planned、updated、would_update、unchanged、ready、available、failed、dry_run、paused、completed、observed_generation |
| `agentway_agentrollout_condition` | `C_rollout(i)` | 每个 condition 一条 |
| `agentway_agentrollout_condition_last_transition_time_seconds` | `C_rollout(i)` | 每个 condition 一条 |

公式：

```text
S_agentrollout(i) = 14 + 2 * C_rollout(i)
```

例如 rollout 有 3 条 condition：

```text
S_agentrollout(i) = 14 + 2 * 3 = 20
```

### 单集群总 active series 公式

单集群总 active series 约为：

```text
S_total = S_exporter
        + Σ S_agent(i), i=1..A
        + Σ S_agentnetpolicy(i), i=1..N
        + Σ S_agentrollout(i), i=1..R
```

展开后：

```text
S_total = S_exporter
        + Σ [18 + 4*Res(i) + 2*Usage(i) + Sync(i) + SyncFail(i) + C_agent(i)]
        + Σ [3 + 2*C_np(i)]
        + Σ [14 + 2*C_rollout(i)]
```

如果采用常见估算：

- Barad enabled，因此 `S_exporter=9`
- 所有 Agent 都配置了 resources，因此 `Res=1`
- 暂不考虑新鲜 usage、网络策略时间戳和 conditions
- 每个 AgentNetPolicy / AgentRollout 暂不考虑 conditions

则简化为：

```text
S_total ≈ 9 + 22*A + 3*N + 14*R
```

如果要更贴近日常运行，假设：

- 每个 Agent 有 resources：`Res=1`
- 每个 Running Agent 都有新鲜 usage：`Usage=1`
- 每个 Agent 有成功网络策略同步时间：`Sync=1`
- 每个 Agent 平均 3 条 condition
- 每个 AgentNetPolicy 平均 2 条 condition
- 每个 AgentRollout 平均 3 条 condition

则可以估算为：

```text
S_total ≈ 9 + 28*A + 7*N + 20*R
```

### 例子

如果一个集群里有：

- `A=1000` 个 Agent
- `N=200` 个 AgentNetPolicy
- `R=50` 个 AgentRollout
- 使用上面的“日常运行估算”

则：

```text
S_total ≈ 9 + 28*1000 + 7*200 + 20*50
        = 9 + 28000 + 1400 + 1000
        = 30409
```

也就是说，单集群大约 3.0 万条 active series。

### 哪些因素最影响 series 数量

| 因素 | 影响 |
|---|---|
| Agent 数量 `A` | 最大影响项。每个 Agent 通常约 22-28 条 active series |
| Agent condition 数量 | 每多 1 条 Agent condition，就多 1 条 series / Agent |
| AgentNetPolicy condition 数量 | 每多 1 条 condition，就多 2 条 series / AgentNetPolicy |
| AgentRollout condition 数量 | 每多 1 条 condition，就多 2 条 series / AgentRollout |
| Barad usage 是否新鲜可用 | 每个有新鲜 usage 的 Agent 多 `M_runtime` 条 runtime usage series，当前为 10 条 |
| tag / label key/value 是否频繁变化 | 不显著增加单次 active series 数，但会增加历史 series churn 和存储压力 |

---
