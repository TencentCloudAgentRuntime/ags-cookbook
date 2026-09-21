# 10. 基于模板升级 Hermes 实例

## 本章场景

Hermes 实例已经运行，现在需要把单个实例升级到某个已发布模板的当前版本。常见场景是更换 Hermes 镜像、调整启动命令、环境变量、资源规格、文件预设、初始化脚本或 Skill 配置。

升级前先执行 dryRun 预览。预览没有不支持字段后，再正式执行更新。

---

## 前置章节

请先完成：

- [02. 通过 Console 创建 Hermes Dashboard](./02-create-hermes-dashboard-with-console.md)
- [04. 复用 Hermes 配置](./04-reuse-hermes-configuration.md)
- [07. 持久化 Hermes 数据目录](./07-persist-hermes-data-on-tke.md)

---

## 更新边界

本阶段只支持更新单个 Kubernetes provider Agent，不支持批量升级、AGS Agent 更新、跨 provider 迁移或自动回滚。

会跟随模板更新的字段：

- `spec.profile.image`
- `spec.profile.command`
- `spec.profile.imageCredentialsRef`
- `spec.profile.access`
- `spec.profile.startupProbe`
- `spec.profile.env`
- `spec.resources`
- `spec.fileInjects`
- `spec.bootstrapScripts`
- `spec.skillPacks`
- `metadata.labels.agentway.io/template-id`
- `metadata.labels.agentway.io/template-version`
- `metadata.annotations.agentway.io/runtime-capabilities-add`

会保留的实例字段：

- `metadata.name`
- `metadata.namespace`
- 实例显示名
- owner
- `spec.virtualAPIKey`
- `spec.accessToken`
- 既有 PVC

当前明确不支持变更的字段：

- `spec.profile.storage`
- `spec.profile.storageSources`
- `spec.profile.volumeMounts`
- `spec.snapshotRef`
- `spec.volumeSnapshotRef`

如果模板中的 `spec.profile.storage` 和目标实例不同，dryRun 会把它放进 `unsupportedChanges`；正式执行会在 patch 前返回 400，不会改 `Agent`，也不会触发 StatefulSet 存储模板变更。

---

## 通过 Console 操作

1. 先编辑 Hermes 运行时或文件预设，并重新发布模板版本。
2. 打开 **Agent 实例**，找到目标 Hermes 实例。
3. 点击实例行的 **更多 / 更新**。
4. 选择目标模板，Console 会自动执行 dryRun 并显示变更预览。
5. 如果出现 **不支持更新字段**，先调整模板或新建实例迁移数据，不要强行改底层资源。
6. 确认预览符合预期后，点击 **确认更新**。
7. 等待实例状态和 Pod 状态恢复正常。

实例列表会把实例状态和 Pod 原始 STATUS 紧凑展示在同一列，例如 `运行中 Pod: Running`。Pod 重建过程中如果 Kubernetes 返回 `Terminating`、`Pending` 或 `Running`，Console 会直接展示该原始值。

---

## 通过 Console API 操作

先找到目标实例和模板：

```bash
AGENT_ID=<agent-id>
TEMPLATE_ID=<template-id>

curl -s http://<console>/api/instances \
  -H "Authorization: Bearer ${TOKEN}" \
  | jq '.instances[] | {id,name,phase,pod_status,template_id,template_version,access_url}'

curl -s http://<console>/api/templates/published \
  -H "Authorization: Bearer ${TOKEN}" \
  | jq '.templates[] | select(.currentVersion != null) | {id,name,displayName,currentVersion}'
```

执行 dryRun：

```bash
curl -s -X POST http://<console>/api/instances/${AGENT_ID}/update \
  -H "Authorization: Bearer ${TOKEN}" \
  -H 'Content-Type: application/json' \
  -d '{"templateId": '"${TEMPLATE_ID}"', "dryRun": true}' | jq .
```

重点看：

- `changes`：正式执行会写入的字段。
- `unsupportedChanges`：当前不支持更新的字段；非空时不要继续正式执行。
- `changes[].path`：字段路径，例如 `spec.profile.image`。
- `changes[].before` / `changes[].after`：更新前后的值。

正式执行：

```bash
curl -s -X POST http://<console>/api/instances/${AGENT_ID}/update \
  -H "Authorization: Bearer ${TOKEN}" \
  -H 'Content-Type: application/json' \
  -d '{"templateId": '"${TEMPLATE_ID}"'}' | jq .
```

普通用户只能更新自己的实例。管理员可以更新任意用户实例。

---

## 以镜像升级为例

先把 Hermes 运行时镜像从旧版本改为新版本：

```text
镜像：ccr.ccs.tencentyun.com/agentway/hermes:<new-version>
```

然后重新发布模板版本，再对目标实例执行 dryRun。预期 `changes` 至少包含：

```json
{
  "path": "spec.profile.image",
  "before": "ccr.ccs.tencentyun.com/agentway/hermes:<old-version>",
  "after": "ccr.ccs.tencentyun.com/agentway/hermes:<new-version>"
}
```

正式执行后检查底层资源：

```bash
kubectl get agent <agent-id> -n <agent-id> -o jsonpath='{.spec.profile.image}{"\n"}'
kubectl get pod -n <agent-id> -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.status.phase}{" "}{.spec.containers[*].image}{"\n"}{end}'
```

确认 `Agent.spec.profile.image` 和新 Pod 镜像都已经变成目标版本。

---

## 验证 PVC 没有换盘

升级前记录 PVC 和测试文件：

```bash
kubectl get pvc -n <agent-id>
kubectl exec -n <agent-id> <pod-name> -- sh -c 'echo upgrade-check > /opt/data/upgrade-check.txt'
kubectl get pvc -n <agent-id> -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.spec.volumeName}{"\n"}{end}'
```

升级后再次检查：

```bash
kubectl get pvc -n <agent-id> -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.spec.volumeName}{"\n"}{end}'
kubectl exec -n <agent-id> <new-pod-name> -- cat /opt/data/upgrade-check.txt
```

PVC 名称和 `spec.volumeName` 应保持不变，文件内容应仍为 `upgrade-check`。

如果 dryRun 返回 `spec.profile.storage` 位于 `unsupportedChanges`，说明模板试图修改持久化配置。正式执行会失败，应该改回模板存储配置或新建实例后手工迁移数据。

---

## 预期效果

- Console 能预览并执行单个 Hermes 实例升级。
- 镜像、命令、环境变量等支持字段会按模板当前发布版本更新。
- 不支持的存储类字段会提前暴露并阻止正式更新。
- PVC 继续挂载同一块盘，`/opt/data` 数据不丢失。
- 实例列表能看到实例状态和 Pod 原始 STATUS。
