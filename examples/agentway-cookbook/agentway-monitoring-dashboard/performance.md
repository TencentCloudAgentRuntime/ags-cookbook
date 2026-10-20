# AgentWay Exporter 性能与容量估算

本文用于帮助客户在大规模 Agent 场景下评估 `agentway-exporter`、Prometheus 采集量和存储容量。

## 推荐规格

当前 cookbook 中 exporter 默认规格：

| 组件 | requests | limits | 说明 |
|---|---:|---:|---|
| `agentway-exporter` CPU | `1` core | `1` core | 覆盖 2000 Agent + 2000 AgentNetPolicy 场景，并为 scrape 峰值、Barad 同步和后续指标增长预留余量 |
| `agentway-exporter` Memory | `2Gi` | `2Gi` | 覆盖 CR cache、metrics 构建、usage cache 和大规模 label/tag 展开 |

dev 集群实测场景：

| 对象规模 | exporter CPU | exporter Memory |
|---|---:|---:|
| 约 2000 Agent + 约 2000 AgentNetPolicy | `0.09` core | `450Mi` |

> 上述是观测值，不是容量上限。生产环境建议仍使用 `1C/2G`，避免在全量更新、Prometheus 并发 scrape、Barad 同步和 label/tag 增长时出现抖动。

## 估算前提

以下估算只计算 `agentway-exporter` 暴露的业务指标，不包含 Prometheus 自身、Grafana、Kubernetes、node-exporter、kube-state-metrics 等其他 job。

基准场景：

| 项 | 值 |
|---|---:|
| Agent 数 | `2000` |
| AgentNetPolicy 数 | `2000` |
| AgentRollout 数 | `0`，如有 rollout 可按 `metrics.md` 公式额外累加 |
| Prometheus scrape interval | `30s` |
| Agent 资源规格指标 | 有，输出 request/limit CPU 和 memory |
| Agent Barad usage | 有，10 个 sandbox runtime 指标 cache 新鲜可用 |
| Agent 网络策略成功同步时间 | 有 |
| Agent 网络策略失败时间 | 无 |
| Agent condition | 无 |
| AgentNetPolicy condition | 每个策略 1 条，例如 `Ready=True` |
| Barad exporter 级指标 | 开启 |

## Series 数计算

详细公式见 [`metrics.md`](./metrics.md)。基准场景使用下面的简化计算。

### 单 Agent

单 Agent series：

```text
S_agent = 18 + 4 * Res + 10 * Usage + Sync + SyncFail + C_agent
```

代入基准假设：

```text
Res = 1
Usage = 1
Sync = 1
SyncFail = 0
C_agent = 0

S_agent = 18 + 4 + 10 + 1 = 33
```

2000 个 Agent：

```text
2000 * 33 = 66000 series
```

### 单 AgentNetPolicy

单 AgentNetPolicy series：

```text
S_agentnetpolicy = 4 + 2 * C_np
```

代入基准假设：

```text
C_np = 1
S_agentnetpolicy = 4 + 2 = 6
```

2000 个 AgentNetPolicy：

```text
2000 * 6 = 12000 series
```

### Exporter 级指标

Barad 开启时，exporter 级指标通常约：

```text
S_exporter = 10 series
```

### 总 series

```text
S_total = 66000 + 12000 + 10 = 78010 series
```

| 来源 | series |
|---|---:|
| Agent | `66000` |
| AgentNetPolicy | `12000` |
| exporter 自身 | `10` |
| 合计 | `78010` |

> 如果 Agent 有 condition、失败时间戳、更多 rollout，或者开启额外组件采集，series 会继续增长。`agentway_agent_tags` / `agentway_agent_labels` 每个 Agent 各 1 条 active series，但 tag/label key/value 高频变化会造成历史 series churn。

## 采样点数量

30s 采集周期下：

```text
每条 series 每分钟 2 个 sample
每条 series 每小时 120 个 sample
每条 series 每天 2880 个 sample
```

代入 `78010` series：

| 时间窗口 | sample 数 |
|---|---:|
| 每分钟 | `156020` |
| 每小时 | `9361200` |
| 每天 | `224668800` |

## Prometheus 磁盘估算

Prometheus TSDB 压缩后通常可按 `2 ~ 3 bytes/sample` 做粗估；实际值会受 label 长度、series churn、WAL、索引、block compaction、保留时间和是否启用 remote-write 影响。

基于 `224668800 samples/day`：

| 估算项 | 计算 | 结果 |
|---|---:|---:|
| 样本数据，2 bytes/sample | `224668800 * 2` | 约 `0.42 GiB/day` |
| 样本数据，3 bytes/sample | `224668800 * 3` | 约 `0.63 GiB/day` |
| 含 WAL / index / head block 余量 | 约 `1.5x ~ 2x` | 约 `0.7 ~ 1.3 GiB/day` |

建议按下面方式预留 Prometheus 磁盘：

| 保留时间 | 建议预留，单集群仅 exporter 业务指标 |
|---|---:|
| 7 天 | `6 ~ 10 GiB` |
| 15 天 | `12 ~ 20 GiB` |
| 30 天 | `25 ~ 40 GiB` |

> 这是只包含 AgentWay exporter job 的估算。若同一个 Prometheus 还采集 Kubernetes、node、kube-state-metrics、应用指标或 remote-write WAL 堆积，需要单独叠加。

## 大规模场景使用建议

1. `scrape_interval` 建议从 `30s` 起步；如果只关注趋势，可放宽到 `60s`，采样量和磁盘约减半。
2. Grafana 默认应通过变量过滤到单 namespace / 单 Agent 或小范围对象，避免一次绘制 2000 条曲线。
3. Barad usage 拉取建议保持批量和限速：
   - `AGENTWAY_EXPORTER_BARAD_BATCH_SIZE=50`
   - `AGENTWAY_EXPORTER_BARAD_MAX_CONCURRENT_REQUESTS=8`
   - `AGENTWAY_EXPORTER_BARAD_MAX_REQUESTS_PER_SECOND=20`
   - `AGENTWAY_EXPORTER_BARAD_REQUEST_TIMEOUT=10s`
4. 生产环境建议为 Prometheus 配置持久化存储、明确 retention，并定期检查：
   - `prometheus_tsdb_head_series`
   - `prometheus_tsdb_head_samples_appended_total`
   - `prometheus_tsdb_wal_*`
   - Prometheus Pod CPU / memory / disk usage
