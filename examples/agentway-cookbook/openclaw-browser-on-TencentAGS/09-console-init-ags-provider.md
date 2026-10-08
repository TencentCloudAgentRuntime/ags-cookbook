# 09. 通过 Console 初始化 AGS Provider 并创建 AGS Agent

本章适用于部署了完整 AgentWay 控制面的客户。你可以在 Console 中完成 AGS provider 初始化，然后在运行时和模板中选择 AGS 沙箱提供方，让后续创建的 Agent 运行在 Tencent Agent Runtime 上。

## 前置章节

- 已完成完整控制面部署，并能登录 Console。
- 已准备 Tencent Cloud `SecretId` / `SecretKey`、`roleArn` 和 AGS `region`。
- 如需持久化存储，已准备 COS bucket。

## 需要填写的参数

| 参数 | 是否必填 | 示例 | 说明 |
|---|---|---|---|
| `region` | 是 | `ap-guangzhou` | AGS 资源所在地域 |
| `SecretId` | 是 | `AKIDxxxxxxxx` | 腾讯云访问密钥 ID |
| `SecretKey` | 是 | `xxxxxxxx` | 腾讯云访问密钥 Key |
| `roleArn` | 是 | `qcs::cam::uin/<uin>:roleName/<role-name>` | AGS/COS/TCR 访问所需 CAM role |
| `cosBucketName` | 否 | `agent-bucket-1250000000` | AGS 持久化存储使用的 COS bucket |

## 在 Console 初始化 AGS Provider

1. 使用管理员账号登录 Console。
2. 打开左侧「沙箱」页面。
3. 点击「初始化 AGS」或「更新 AGS 配置」。
4. 填写 `region`、`SecretId`、`SecretKey`、`roleArn`，按需填写 COS bucket。
5. 提交后刷新列表，确认能看到内置 `K8s` 和 `ags` 两个 provider 选项。

初始化完成后，控制面会维护以下资源：

- `AgentSandboxProvider/ags`：作为运行时、模板和 Agent 的 AGS sandbox provider 引用目标。
- `Secret/ags-aksk`：保存 AGS 访问凭证，位于控制面 namespace。
- active `AgentInfraProvider` 不会被 Console AGS 初始化修改；平台共享 ingress、egress、model router 仍由原 Kubernetes active provider 管理。

## 验证 Provider 资源

```bash
kubectl get agentinfraprovider default -o yaml
kubectl get agentsandboxprovider ags -o yaml
kubectl get secret ags-aksk -n agent-way-system
```

`AgentSandboxProvider/ags` 应包含：

```yaml
spec:
  tencentAgentRuntime:
    region: ap-guangzhou
    accessSecretRef:
      name: ags-aksk
    roleArn: qcs::cam::uin/<uin>:roleName/<role-name>
```

`AgentInfraProvider/default` 或你部署时指定的 active provider 应保持原有 Kubernetes shared infra 配置，不需要也不应因为启用 AGS sandbox 而写入 AGS 凭证。

## 在运行时中选择 AGS Provider

1. 打开「运行环境」页面。
2. 新建或编辑运行时。
3. 在「Sandbox Provider」中选择 `ags`。
4. 保存运行时。

保存后，运行时记录中的 `sandboxProviderRef` 应为 `ags`。使用该运行时创建或更新模板时，模板草稿会继承该 provider。

## 在模板中选择 AGS Provider

1. 打开「模板管理」页面。
2. 创建模板或编辑草稿。
3. 展开「运行时配置」面板。
4. 在「Sandbox Provider」中选择 `ags`，或从运行时库导入一个已选择 `ags` 的运行时。
5. 保存草稿并发布版本。

之后用户从该模板创建 Agent 时，Agent 会带上：

```yaml
spec:
  sandboxProviderRef: ags
```

## 配置 AGS Agent 网络策略

AGS Agent 的网络策略由 Agent 所在 namespace 的 `AgentNetPolicy` CR 决定，不使用 `agent-infra/global`。

示例：

```yaml
apiVersion: agent.agentway.io/v1alpha1
kind: AgentNetPolicy
metadata:
  name: openclaw-egress
  namespace: default
spec:
  selector:
    matchLabels:
      app: openclaw-browser
  defaultDecision: deny
  rules:
    - name: allow-openai
      protocol: https
      host: api.openai.com
      port: 443
      action: allow
```

创建 Agent 时，确保 Agent 与 `AgentNetPolicy` 位于同一 namespace，并让 labels 或 `spec.netPolicyRef` 指向该策略。

## 预期效果

完成本章后：

- Console 可展示 `K8s` 默认 provider 和 `ags` provider。
- 运行时和模板可选择 `ags`。
- 基于该模板创建的新 Agent 会通过 AGS sandbox provider 运行。
- AGS Agent 的网络策略只受同 namespace `AgentNetPolicy` 影响，不会被全局 Kubernetes egress policy 意外覆盖。
