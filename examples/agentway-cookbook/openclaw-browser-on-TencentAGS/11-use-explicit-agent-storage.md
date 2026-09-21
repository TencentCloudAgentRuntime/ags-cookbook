# 11. 显式声明 Agent 挂载多种不同类型存储或共享存储目录

## 本章场景

> 注意：本章示例依赖支持 `storageSources`、`storageSource`、`subPath` 和 `subPathExpr` 的 AgentWay Operator / CRD 版本。
> 本方案不引入独立的 `AgentVolume` CRD，也不引入独立的 `StorageSource` CRD；共享目录通过多个 Agent 解析到相同 backend source 和相同 `subPath` 表达。

第 01 章仍然使用 `AgentSandboxProvider.spec.tencentAgentRuntime.cfsStorage` 作为默认存储 backend，第 02 章通过 `AgentProfile.spec.volumeMounts` 声明挂载路径。

这种写法适合快速启动，但有一个主要限制：

- 一个 Agent 的多个持久化目录只能共享同一种 provider 默认存储类型。

本章重点覆盖两个典型用户场景：

- **多个 Agent 复用同一个 COS bucket 或 CFS 文件系统，但各自挂载到隔离目录。** 团队统一使用一个 bucket 或 CFS filesystem 存放 Agent 数据，在 `storageSources[]` 中声明 storage source，再由 `volumeMounts[]` 通过 `storageSource` 引用它，最终落到各自显式声明的 `subPath` 中。
- **多个 Agent 实例共同挂载同一个存储目录做数据共享。** 多个 Agent 使用同一个 `AgentProfile`，或使用等价的 storage source root 配置，并设置相同 `subPath`，最终解析到完全相同的 backend 目录，挂载后看到相同内容。

新设计希望解决默认存储粒度过粗的问题，并给共享目录约定一个显式写法：

- 在现有 `volumeMounts[]` 中直接声明每个目录绑定的存储来源。
- 使用 `storageSources[]` 定义可复用 storage source，并通过 `volumeMounts[].storageSource` 引用。
- 使用 `subPath` 明确最终 backend 子目录；相同 root + 相同 `subPath` 表示按约定共享，相同 root + 不同 `subPath` 表示隔离。
- 使用 `subPathExpr` 引用 downward API 注入的 Agent 元数据 env，按 namespace/name/uid 自动生成每个 Agent 的隔离目录。
- 未设置 `storageSource` 时继续沿用 SandboxProvider 默认存储，保持现有行为兼容。

---

## 前置章节

请先完成：

- [00. 准备集群环境并部署 Operator](./00-prepare-cluster-and-deploy-operator.md)
- [01. 准备 Tencent Agent Runtime 基础设施](./01-prepare-tencent-agent-runtime.md)
- [02. 快速启动一个自带浏览器、技能和角色设定的 OpenClaw](./02-create-openclaw-browser-agent.md)

---

## 使用 manifest

本章两个主要场景各有一份可直接应用的 manifest：

```bash
# 方式二：使用 storageSource + 不同 subPath/subPathExpr，为 Agent 准备隔离目录。
kubectl apply -f ./openclaw-browser-on-TencentAGS/manifests/11-01-storage-source-agent-storage.yaml

# RollingUpgrade：分批更新存量 Agent 的 storageSources 和 volumeMounts。
kubectl apply -f ./openclaw-browser-on-TencentAGS/manifests/11-02-rolling-upgrade-storage-source-rollout.yaml
```

这两份 manifest 复用第 01 章创建的 `openclaw-tencent-runtime` provider。应用前请把示例里的 CFS filesystem ID、COS bucket 和 path 改成你的环境配置。

---

## 三种存储挂载方式

### 方式一：沿用 SandboxProvider 默认存储

这是当前已支持的兼容写法。`volumeMounts[]` 只声明目录名和容器内路径，不声明 `storageSource`。

```yaml
apiVersion: agent.agentway.io/v1alpha1
kind: AgentProfile
metadata:
  name: openclaw-browser-profile
  namespace: default
spec:
  image: ccr.ccs.tencentyun.com/yaominxia/sandbox-openclaw-browser:v1.12
  command: ["/init"]
  volumeMounts:
    - name: openclaw-data
      mountPath: /openclaw
```

Operator 会继续读取 `AgentSandboxProvider.spec.tencentAgentRuntime.cfsStorage` 或 `cosStorage` 作为默认 backend。

适合：

- 快速启动。
- 所有持久化目录都使用同一种默认存储。
- 不需要在 profile 中显式声明每个目录的存储来源。

### 方式二：使用 storageSources + storageSource 声明隔离目录

当某个目录需要指定具体 storage backend，或者一个 Agent 内不同目录需要不同 backend 时，可以先在 `AgentProfile.spec.storageSources[]` 中声明可复用存储来源，再在对应 `volumeMounts[]` item 中通过 `storageSource` 引用名称。

```yaml
apiVersion: agent.agentway.io/v1alpha1
kind: AgentProfile
metadata:
  name: openclaw-browser-profile
  namespace: default
spec:
  image: ccr.ccs.tencentyun.com/yaominxia/sandbox-openclaw-browser:v1.12
  command: ["/init"]
  storageSources:
    - name: workspace
      type: cfs
      cfs:
        filesystemId: cfs-xxxxxxxx
        path: /agents/openclaw
    - name: artifacts
      type: cos
      cos:
        bucketName: your-bucketName
        bucketPath: /agents/openclaw
  volumeMounts:
    - name: workspace1
      mountPath: /openclaw/.openclaw/workspace
      storageSource: workspace
      subPathExpr: "$(AGENT_NAMESPACE)/$(AGENT_NAME)/$(AGENT_UID)/workspace"
    - name: workspace2
      mountPath: /openclaw/.openclaw/another-workspace
      storageSource: workspace
      subPath: workspace-b
    - name: artifacts
      mountPath: /openclaw/.openclaw/artifacts
      storageSource: artifacts
  env:
    - key: AGENT_NAMESPACE
      valueFrom:
        fieldRef:
          fieldPath: metadata.namespace
    - key: AGENT_NAME
      valueFrom:
        fieldRef:
          fieldPath: metadata.name
    - key: AGENT_UID
      valueFrom:
        fieldRef:
          fieldPath: metadata.uid
```

预期行为：

- `workspace1` 和 `workspace2` 都引用 `workspace` 存储来源，因此都使用 CFS。
- `workspace1` 使用 `subPathExpr`，Operator 会先用 downward API env 展开成类似 `default/openclaw-storage-source-demo/<agent-uid>/workspace` 的相对路径，再拼接到 CFS root。
- `workspace2` 使用静态 `subPath`，最终 backend 目录是 `/agents/openclaw/workspace-b`。
- `artifacts` 引用 `artifacts` 存储来源，因此使用 COS。
- 如果某个 mount 没有显式设置 `subPath`，Operator 会按空 `subPath` 处理，最终 backend path 就是 storage source root。

`subPathExpr` 使用与 Kubernetes `volumeMounts.subPathExpr` 一致的 `$(VAR_NAME)` 引用语法。当前可通过 Agent downward API 注入的常用字段包括：

| env | fieldPath |
|---|---|
| `AGENT_NAMESPACE` | `metadata.namespace` |
| `AGENT_NAME` | `metadata.name` |
| `AGENT_UID` | `metadata.uid` |

`subPath` 和 `subPathExpr` 互斥，同一个 mount 只能选择其中一个。需要所有 Agent 共享同一个目录时，用静态 `subPath`；需要按每个 Agent 自动隔离目录时，用 `subPathExpr`。

当 `volumeMounts[].subPath` 显式填写时，Operator 会把它拼接到 `storageSources[].cfs.path` 或 `storageSources[].cos.bucketPath` 这个 root 下。例如 `workspace2` 的最终 CFS path 为：

```text
/agents/openclaw/workspace-b
```

如果未显式设置 `subPath`，Operator 不会额外追加任何目录；最终路径就是 path-based storage source root。例如未设置 `subPath` 的 `workspace1` 最终路径为：

```text
/agents/openclaw
```

适合：

- 一个 Agent 内不同目录需要不同存储类型。
- 希望存储来源由平台或管理员统一配置。
- 希望通过显式 `subPath` 管理每个 Agent 或每个 mount 的隔离目录。

### 方式三：相同 backend root + 相同 subPath 共享目录

当某个目录要被多个 Agent 共享时，不需要创建独立 CRD。让这些 Agent 使用同一个 `AgentProfile` 中的同名 `storageSource`，或使用等价的 storage source root 配置，并设置同一个 `subPath` 即可。

```yaml
apiVersion: agent.agentway.io/v1alpha1
kind: AgentProfile
metadata:
  name: openclaw-browser-shared-profile
  namespace: default
spec:
  image: ccr.ccs.tencentyun.com/yaominxia/sandbox-openclaw-browser:v1.12
  command: ["/init"]
  storageSources:
    - name: workspace
      type: cfs
      cfs:
        filesystemId: cfs-xxxxxxxx
        path: /agents/openclaw
  volumeMounts:
    - name: shared-workspace
      mountPath: /openclaw/.openclaw/workspace
      storageSource: workspace
      subPath: shared-workspace
---
apiVersion: agent.agentway.io/v1alpha1
kind: Agent
metadata:
  name: openclaw-shared-volume-a
  namespace: default
spec:
  sandboxProviderRef: openclaw-tencent-runtime
  profileRef: openclaw-browser-shared-profile
---
apiVersion: agent.agentway.io/v1alpha1
kind: Agent
metadata:
  name: openclaw-shared-volume-b
  namespace: default
spec:
  sandboxProviderRef: openclaw-tencent-runtime
  profileRef: openclaw-browser-shared-profile
```

预期行为：

- 两个 Agent 都将 `/openclaw/.openclaw/workspace` 挂载到同一个 CFS path：`/agents/openclaw/shared-workspace`。
- 两个 Agent 会看到相同数据内容；这是基于相同 backend path 的显式约定，不是平台托管的共享存储对象。
- 删除任意一个 Agent 不会删除底层 CFS 目录或 COS prefix。
- 是否能并发读写由底层存储能力决定；CFS 适合这种共享目录场景。

适合：

- 多个 Agent 共享数据集、公共素材或团队目录。
- 存储生命周期不应被单个 Agent 控制。
- 客户已经通过存储目录权限和命名规范管理共享数据。

---

## 字段选择建议

| 场景 | 推荐字段 |
|---|---|
| 快速启动，全部目录使用默认 CFS/COS | 只写 `name` + `mountPath` |
| 指定某个目录使用特定 backend | `storageSources[]` + `storageSource` |
| 每个 Agent 或每个 mount 隔离 | 使用不同的显式 `subPath` |
| 按 Agent namespace/name/uid 自动隔离 | downward API env + `subPathExpr` |
| 多个 Agent 共享目录 | 使用相同 backend root + 相同 `subPath` |

`storageSource` 的值引用 `storageSources[].name`。不写 `storageSource` 时，才会走现有 SandboxProvider 默认存储。

对 CFS/COS 这类 path-based source，`subPath` 或展开后的 `subPathExpr` 是 storage source root 下的相对路径。不要写绝对路径，也不要使用 `..` 逃逸 root。Operator 应拒绝这类非法配置。对 CBS 这类非路径型 source，是否允许 `subPath` / `subPathExpr` 取决于后续挂载实现。

---

## 排障建议

本方案不要求新增 `Agent.status.volumeMounts[]`。每条 mount 的最终来源可以直接从 `AgentProfile.spec.storageSources[]`、`volumeMounts[].storageSource`、`volumeMounts[].subPath` 和展开后的 `volumeMounts[].subPathExpr` 推导。

排障时可以优先看：

- `volumeMounts[].storageSource` 是否引用了存在的 `storageSources[].name`。
- CFS/COS source root 与显式 `subPath` 或展开后的 `subPathExpr` 拼接后是否为预期 backend path。
- `Agent.spec.env` / `AgentProfile.spec.env` 中用于 `subPathExpr` 的变量是否已通过 `value` 或 `valueFrom.fieldRef` 定义。
- Agent condition/event 中是否有 storage source 不存在、source type 不支持或 `subPath` / `subPathExpr` 非法的错误。
