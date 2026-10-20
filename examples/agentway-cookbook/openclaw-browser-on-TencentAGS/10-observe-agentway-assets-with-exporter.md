# 10. AgentWay Exporter 指标采集与看板

`agentway-exporter` 将 AgentWay 资产转换为 Prometheus metrics。首批覆盖 `Agent`、`AgentNetPolicy`、`AgentRollout`，并可通过 AGS Barad/云监控缓存补充沙箱 CPU、Memory、磁盘、文件系统和网络运行时指标。

## 部署示例

当前阶段不交付 Helm/RBAC 产品化模板，dev/验证部署可使用：

```bash
kubectl apply -f ./agentway-monitoring-dashboard/manifests/agentway-exporter.yaml
```

默认示例复用 `agent-way-operator` ServiceAccount。Barad AK/SK 复用 Operator 当前使用的 Secret：

```yaml
env:
  - name: AGENTWAY_EXPORTER_BARAD_SECRET_NAME
    value: tencent-runtime-credentials
  - name: AGENTWAY_EXPORTER_BARAD_SECRET_ID_KEY
    value: secret_id
  - name: AGENTWAY_EXPORTER_BARAD_SECRET_KEY_KEY
    value: secret_key
```

自动化测试和本地运行可通过 `.env` 或进程环境提供 `AGENTWAY_EXPORTER_*` 配置；不要在测试代码中硬编码 AK/SK。

## Prometheus 采集

### Prometheus Operator

```bash
kubectl apply -f ./agentway-monitoring-dashboard/manifests/servicemonitor.yaml
```

### 原生 Prometheus

参考 `./agentway-monitoring-dashboard/manifests/prometheus-scrape-config.yaml`。该示例使用 Kubernetes service discovery，按 Service label 和 endpoint port 发现 exporter：

```yaml
scrape_configs:
  - job_name: agentway-exporter
    scrape_interval: 30s
    scrape_timeout: 10s
    kubernetes_sd_configs:
      - role: endpoints
        namespaces:
          names:
            - agent-way-system
    relabel_configs:
      - source_labels: [__meta_kubernetes_service_label_app_kubernetes_io_name]
        action: keep
        regex: agentway-exporter
      - source_labels: [__meta_kubernetes_endpoint_port_name]
        action: keep
        regex: metrics
      - source_labels: [__meta_kubernetes_namespace]
        target_label: k8s_namespace
      - source_labels: [__meta_kubernetes_service_name]
        target_label: k8s_service
      - source_labels: [__meta_kubernetes_pod_name]
        target_label: k8s_pod
      - target_label: clusterID
        replacement: cls-xxx
```

Prometheus 只 scrape exporter；不要让 Prometheus 直接访问 Barad。exporter 自身不输出集群 label，`clusterID` 由 Prometheus scrape/external label 注入，用于多集群聚合与 Grafana 下拉筛选。

## Grafana

按资产类型导入 3 个 dashboard：`./agentway-monitoring-dashboard/manifests/grafana-agent-dashboard.json`、`./agentway-monitoring-dashboard/manifests/grafana-agentnetpolicy-dashboard.json`、`./agentway-monitoring-dashboard/manifests/grafana-rollout-dashboard.json`。Dashboard datasource 变量默认显示名为 `meta-agentway-cls-sh-public`，导入时可替换为客户自己的 Prometheus datasource。

看板包含：

- Agent phase 分布
- 单 Agent CPU/Mem request、limit、usage
- sandbox alive 与 usage cache 可用性
- AgentNetPolicy phase/condition
- AgentRollout 进度和失败数
- exporter/Barad cache 健康

## 关键指标

| 指标 | 含义 |
|---|---|
| `agentway_agent_phase` | Agent 当前生命周期状态 |
| `agentway_agent_sandbox_alive` | 底层沙箱是否可判定存活 |
| `agentway_agent_resource_requests_cpu_cores` | Agent CPU request，单位 core |
| `agentway_agent_resource_limits_memory_bytes` | Agent memory limit，单位 byte |
| `agentway_agent_cpu_usage_percent` | 来自 runtime metric cache 的 CPU 使用率 |
| `agentway_agent_cpu_usage_cores` | 来自 usage cache 的 CPU 使用量 |
| `agentway_agent_memory_usage_percent` | 来自 runtime metric cache 的 memory 使用率 |
| `agentway_agent_memory_usage_bytes` | 来自 usage cache 的 memory 使用量 |
| `agentway_agent_disk_read_bytes_per_second` | 来自 runtime metric cache 的磁盘读吞吐 |
| `agentway_agent_disk_write_bytes_per_second` | 来自 runtime metric cache 的磁盘写吞吐 |
| `agentway_agent_filesystem_usage_percent` | 来自 runtime metric cache 的文件系统使用率 |
| `agentway_agent_filesystem_used_bytes` | 来自 runtime metric cache 的文件系统已用容量 |
| `agentway_agent_network_receive_bytes_per_second` | 来自 runtime metric cache 的网络接收速率 |
| `agentway_agent_network_transmit_bytes_per_second` | 来自 runtime metric cache 的网络发送速率 |
| `agentway_agent_sandbox_metrics_available` | usage cache 是否新鲜可用 |
| `agentway_agent_skill_applied_count` | 已成功安装/应用的 skill 数量 |
| `agentway_agent_skill_total_count` | 期望安装/管理的 skill 总数 |
| `agentway_agent_asset_phase` | bootstrap/skills/plugins/fileInjects 当前资产阶段 |
| `agentway_agent_network_policy_stale` | Agent 网络策略是否过期，1 表示需重新同步 |
| `agentway_agent_network_policy_last_sync_timestamp_seconds` | Agent 网络策略上一次成功同步时间 |
| `agentway_agent_network_policy_last_failure_timestamp_seconds` | Agent 网络策略上一次同步失败时间 |
| `agentway_agentnetpolicy_condition_last_transition_time_seconds` | 网络策略 condition 最近变化时间 |
| `agentway_agentrollout_failed_agents` | Rollout 失败 Agent 数 |
| `agentway_exporter_runtime_metric_cache_entries` | runtime metric cache 条目数 |

## 验证

```bash
kubectl -n agent-way-system port-forward svc/agentway-exporter 9108:9108
curl -s localhost:9108/metrics | grep -E 'agentway_agent_phase|agentway_agent_network_receive_bytes_per_second|agentway_exporter_runtime_metric_cache_entries'
```

常见 PromQL：

```promql
sum by (phase) (agentway_agent_phase{clusterID="cls-xxx"})
agentway_agent_sandbox_alive{clusterID="cls-xxx"} == 0
agentway_agentrollout_failed_agents{clusterID="cls-xxx"} > 0
agentway_agent_sandbox_metrics_available{clusterID="cls-xxx"} == 0
```

## 常见问题

- **没有 Barad usage 数据**：确认 `AGENTWAY_EXPORTER_BARAD_ENABLED=true`、Operator Secret 可读、Region 与沙箱实际地域一致。Barad 数据周期为 1 分钟，新沙箱建议等待 1-3 分钟。
- **cache stale**：检查 `agentway_agent_sandbox_metrics_cache_age_seconds` 和 exporter 日志；可能是云监控限频、无数据或 AK/SK 权限不足。
- **tag label 缺失**：检查 allowlist/denylist、`maxPerAgent` 和 `maxValueLength` 配置。
- **series 过多**：减少 tag label 数量，避免将用户 ID、请求 ID 等高基数字段放入 Agent tag。
