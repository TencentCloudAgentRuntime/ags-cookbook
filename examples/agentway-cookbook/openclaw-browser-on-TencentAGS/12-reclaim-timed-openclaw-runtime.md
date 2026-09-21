# 12. 为 OpenClaw 设置 AGS 原生运行时回收

## 本章解决什么问题

有些 OpenClaw 只用于一次性任务、评审或临时演示。为它设置 `expireAfter` 后，Tencent Agent Runtime（AGS）会在到期时回收 SandboxInstance；AgentWay Operator 随后删除对应的 `Agent` CR 与该 Agent 专属的 SandboxTool，避免控制面对象和 Tool 配额残留。

本章只使用 Kubernetes YAML，不需要 Console、Backend 或 Agent Connect。

## 前置条件

- 已完成 [00. 准备集群环境并部署 Operator](./00-prepare-cluster-and-deploy-operator.md)。
- 已完成 [01. 准备 Tencent Agent Runtime 基础设施](./01-prepare-tencent-agent-runtime.md)，并有可用的 AGS `sandboxProviderRef`。
- 仅 AGS Provider 支持本能力；不要给 Kubernetes 或 Cube Provider 配置 `expireAfter`。

## 创建限时 Agent

复制并修改 [`manifests/12-timed-openclaw-agent.yaml`](./manifests/12-timed-openclaw-agent.yaml) 中的三个值：

- `metadata.namespace`
- `spec.sandboxProviderRef`
- `spec.profile.image`

示例使用两小时：

```yaml
spec:
  expireAfter: 2h
```

先做一次 server-side dry-run：

```bash
kubectl apply --dry-run=server -f ./openclaw-browser-on-TencentAGS/manifests/12-timed-openclaw-agent.yaml
```

确认无误后创建：

```bash
kubectl apply -f ./openclaw-browser-on-TencentAGS/manifests/12-timed-openclaw-agent.yaml
kubectl get agent timed-openclaw-browser -n default -w
```

AgentWay 不校验时间字符串的单位或范围，而是原样传给 AGS。因此如果值不被 AGS 接受，创建请求本身可能成功，但 Agent 会在异步 reconcile 中进入失败状态。请用下面的命令查看原因：

```bash
kubectl describe agent timed-openclaw-browser -n default
```

## 观察到期时间与回收

Agent 运行后，`status.expiresAt` 是 AGS 返回的权威到期时间，不是 Operator 根据 `expireAfter` 自行推算的结果：

```bash
kubectl get agent timed-openclaw-browser -n default \
  -o jsonpath='{.status.phase}{"\\n"}{.status.expiresAt}{"\\n"}'
```

到期时 AGS 先停止 SandboxInstance。Operator 观察并确认到期后，将 Agent 置为 `Expiring`，再删除 Agent CR 和该 Agent 专属 SandboxTool。这个过程是最终一致的；不要仅因到期瞬间 CR 尚未消失就手动重建相同 Agent。

## 修改时长

对于正在运行的限时 Agent，如果只把非空 `expireAfter` 改为另一个非空值，Operator 会调用 AGS 的 Timeout 热更新，保持原 SandboxInstance 和 SandboxTool：

```bash
kubectl patch agent timed-openclaw-browser -n default --type merge \
  -p '{"spec":{"expireAfter":"4h"}}'
```

等待 `status.expiresAt` 刷新后再以该字段判断新 deadline。若同时修改镜像、资源或其他运行时字段，仍走既有的 spec reconcile，可能发生运行环境替换。

删除 `expireAfter` 或改为空字符串表示永久语义。这是从限时到永久的 spec 变化，按既有 reconcile 收敛；如需无中断服务，请先按自己的发布策略创建替代 Agent。

## 数据保留边界

自动回收只处理运行基座和其控制面伴生资源：

- AGS 回收 SandboxInstance。
- Operator 删除 Agent CR 和该 Agent 专属 SandboxTool。

自动回收不会删除 COS bucket/prefix、CFS filesystem/directory、卷快照或共享 CFS prep tool。对已挂载的 COS/CFS，实例退出后的挂载释放由 AGS 管理；其中的业务数据仍由你按自己的生命周期策略保留或清理。

如果你不再需要该 Agent 且不想等待到期，可正常删除 CR：

```bash
kubectl delete agent timed-openclaw-browser -n default
```
