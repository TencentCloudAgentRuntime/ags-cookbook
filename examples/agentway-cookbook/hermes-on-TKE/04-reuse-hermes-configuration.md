# 04. 复用 Hermes 配置

## 本章场景

你已经创建了一个可用的 Hermes Dashboard。现在希望把这套配置沉淀下来，让后续团队可以直接复用，而不是每次重新填写文件、镜像、端口和启动命令。

---

## 前置章节

请先完成：

- [02. 通过 Console 创建 Hermes Dashboard](./02-create-hermes-dashboard-with-console.md)

---

## 为什么这一章这样组织

Hermes on TKE 的复用单元主要有三类：

- **文件预设**：保存 `/opt/data/config.yaml`、`/opt/data/.env` 等文件内容
- **运行时**：保存镜像、命令、端口、探针、资源和权限
- **模板版本**：把文件预设和运行时固化成一个可创建实例的版本

后续创建实例时，只需要选择已发布模板，不需要理解所有底层配置。

---

## 通过 Console 操作

### 1. 复用文件预设

打开 **预设策略 / 文件预设**，找到 `Hermes Dashboard Config`。

当只需要调整模型名或 Dashboard 配置时，可以编辑文件预设，然后进入模板草稿重新引用并发布新版本。

### 2. 复用运行时

打开 **Agent 应用 / 运行环境**，找到 Hermes 运行时。

如果多个 Hermes 模板使用同一镜像、端口和启动命令，可以共用同一个运行时。

### 3. 复用模板版本

打开 **Agent 应用 / 模版管理**，选择 Hermes 模板。

模板发布后，创建实例时看到的是已发布版本。修改草稿不会影响已创建实例，只有重新发布后，新建实例才会使用新版本。

---

## 通过 Kubernetes API 操作

文件预设对应 `FileInjects`，运行时对应 `AgentProfile`，模板对应 `AgentTemplate` 和 `AgentTemplateRevision`。

查看当前复用对象：

```bash
kubectl get fileinjects -n agent-way-system
kubectl get agentprofiles -n agent-way-system
kubectl get agenttemplates -n agent-way-system
kubectl get agenttemplaterevisions -n agent-way-system
```

查看某个模板发布版本：

```bash
kubectl get agenttemplaterevision <revision-name> -n agent-way-system -o yaml
```

---

## 预期效果

完成后：

- Hermes 配置不再散落在多个临时表单中
- 后续创建实例只需要选择模板
- 模板版本成为配置复用和回溯的边界

---

## 如何验证

Console 侧：

- 文件预设、运行时和模板都存在
- 模板显示已发布版本

Kubernetes 侧：

```bash
kubectl get agenttemplates -n agent-way-system
kubectl get agenttemplaterevisions -n agent-way-system
kubectl get agenttemplaterevision <revision-name> -n agent-way-system -o yaml
```

重点确认发布版本中的运行时镜像、文件预设内容和资源规格符合预期。再用同一模板创建第二个测试实例，能进入 `运行中` 并打开 Dashboard，才说明复用配置真正可用。

---

## 下一章

完成后，继续：

- [05. 使用凭证注入和审计 Hermes](./05-use-credentials-and-audit-hermes.md)
