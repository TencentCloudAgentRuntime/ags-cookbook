# 09. 观测 Hermes 实例和平台资产

## 本章场景

Hermes 已经投入使用。现在你需要确认它的运行状态、访问入口、模板版本、出口规则和资源状态是否健康。

---

## 前置章节

请先完成：

- [02. 通过 Console 创建 Hermes Dashboard](./02-create-hermes-dashboard-with-console.md)
- [03. 控制 Hermes 的外部访问范围](./03-control-hermes-network-access.md)

---

## 通过 Console 观测

打开 **Agent 实例**，重点看：

- 实例状态是否为 `运行中`
- 访问地址是否存在
- 模板和版本是否符合预期
- 健康状态是否正常

打开 **安全防护 / 网络策略**，重点看：

- 当前出口模式
- Hermes 需要访问的域名规则是否启用

打开 **Agent Infra / 模型网关**，重点看：

- 模型配置是否为 `已配置`
- Hermes 使用的模型名是否存在

---

## 通过 Kubernetes API 观测

查看实例：

```bash
kubectl get agent <agent-id> -n <agent-id> -o yaml
```

重点字段：

```yaml
status:
  phase: Running
  accessURL: ...
  fileInjectStatus:
    phase: Applied
  serviceHealth:
    ready: true
```

查看 Pod：

```bash
kubectl get pod -n <agent-id>
kubectl logs -n <agent-id> <pod-name> --tail=100
```

日志可能包含 token、API Key、访问 URL 或用户输入。定位问题时先脱敏，不要把完整日志直接贴到共享文档或聊天记录中。

查看全局出口规则：

```bash
kubectl get agentnetpolicy global -n agent-infra -o yaml
```

查看模板和版本：

```bash
kubectl get agenttemplates -n agent-way-system
kubectl get agenttemplaterevisions -n agent-way-system
```

---

## 接入监控面板

如果已经部署 Prometheus / Grafana，可以继续使用：

- [AgentWay 监控面板](../agentway-monitoring-dashboard/README.md)

这里可以看到 Agent 状态、网络策略状态、Rollout 状态和 exporter 自身健康。

Hermes on TKE 主线建议至少看这些查询：

```promql
agentway_agent_phase{namespace="<agent-id>"}
agentway_agent_asset_phase{namespace="<agent-id>", asset="fileInjects"}
agentway_agent_network_policy_stale{namespace="<agent-id>"}
agentway_agentnetpolicy_phase{namespace="agent-infra", agentnetpolicy="global"}
agentway_agent_cpu_usage_percent{namespace="<agent-id>"}
agentway_agent_memory_usage_percent{namespace="<agent-id>"}
```

如果暂时没有接入监控，也可以先用本章的 `kubectl` 完成主线验证。

---

## 预期效果

- Console 能看到 Hermes 实例为 `运行中`
- Kubernetes 中 `Agent.status` 显示文件注入和健康检查正常
- 出口规则和模型配置能对应到 Hermes 使用场景

---

## 如何验证

```bash
kubectl get agent -A
kubectl get agentnetpolicy global -n agent-infra
kubectl get pods -n agent-way-system
kubectl get pods -n agent-infra
```

如果这些资源都处于预期状态，Hermes on TKE 主线已经完成。

---

## 下一章

如果需要升级已运行实例，继续：

- [10. 基于模板升级 Hermes 实例](./10-upgrade-hermes-with-template.md)
