# 07. 持久化 Hermes 数据目录

## 本章场景

Hermes Dashboard 的配置、会话和运行状态会使用 `/opt/data`。开箱验证阶段可以先不启用持久化；生产环境如果需要在重启后保留状态，可以为 `/opt/data` 配置持久化存储。

---

## 前置章节

请先完成：

- [02. 通过 Console 创建 Hermes Dashboard](./02-create-hermes-dashboard-with-console.md)

---

## 使用建议

第一次创建 Hermes 时，建议先不启用持久化，确认 Dashboard 本体可以正常运行。

确认运行链路没问题后，再启用：

```text
挂载路径：/opt/data
容量（GiB）：按数据保留需求填写，例如 20
```

这样能把“应用配置问题”和“存储挂载权限问题”分开排查。

---

## 通过 Console 操作

打开 **Agent 应用 / 运行环境**，编辑 Hermes 运行时。

在存储配置中填写：

```text
启用持久化存储：开启
挂载路径：/opt/data
容量（GiB）：20
```

保存后，回到模板草稿并重新发布版本。新创建的实例会使用新的持久化配置。

生产环境启用前请确认 StorageClass、容量配额、费用、扩容策略和备份策略。删除实例时，PVC / PV 的保留或清理行为取决于平台和存储配置，需要提前确认。

---

## 通过 Kubernetes API 操作

运行时的持久化配置对应 `AgentProfile.spec.storage`：

```yaml
apiVersion: agent.agentway.io/v1alpha1
kind: AgentProfile
metadata:
  name: hermes-dashboard-runtime
  namespace: agent-way-system
spec:
  image: ccr.ccs.tencentyun.com/agentway/hermes:v2026.06.30-r1
  storage:
    mountPath: /opt/data
    sizeGi: 20
```

直接创建 inline `Agent` 时，也可以写在 `spec.profile.storage`：

```yaml
spec:
  profile:
    storage:
      mountPath: /opt/data
      sizeGi: 20
```

---

## 预期效果

- 新实例启动后 `/opt/data` 使用持久化存储
- 重启实例后，Dashboard 配置和状态仍保留

---

## 如何验证

在实例运行后执行：

```bash
kubectl get agentprofile hermes-dashboard-runtime -n agent-way-system -o yaml
kubectl get agent <agent-id> -n <agent-id> -o jsonpath='{.spec.profile.storage.mountPath}{" "}{.spec.profile.storage.sizeGi}{"\n"}'
kubectl get pvc -n <agent-id>

kubectl exec -n <agent-id> <pod-name> -- sh -c 'echo ok > /opt/data/persist-check.txt'
kubectl delete pod -n <agent-id> <pod-name>
kubectl exec -n <agent-id> <new-pod-name> -- cat /opt/data/persist-check.txt
```

如果能看到 `ok`，说明 `/opt/data` 已跨 Pod 重建保留。

---

## 下一章

完成后，继续：

- [08. 用 Console API 自动化创建 Hermes](./08-automate-hermes-creation-with-console-api.md)
