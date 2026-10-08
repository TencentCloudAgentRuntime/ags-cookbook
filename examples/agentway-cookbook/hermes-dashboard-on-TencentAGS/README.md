# 在 Tencent AGS 上启动 Hermes Dashboard

## 本章场景

从客户和交付同学的视角看，这一篇文档主要回答四个问题：

- 我怎么尽快把一个 Hermes Dashboard 跑起来？
- 我需要替换哪些参数，才能让它安全对外提供访问？
- 部署完成后，我应该去哪里拿访问地址并验证结果？

这篇文档解决的就是这个问题：

> 用一份完整 YAML，把 Hermes Dashboard 的运行镜像、少量启动参数、配置文件注入、持久化目录和公网访问入口一次性准备好。

---

## 前置章节

这份 Hermes 示例复用的还是同一套 AgentWay / AGS 底座，所以前置条件和 OpenClaw cookbook 一样：

- [00. 准备集群环境并部署 Operator](../openclaw-browser-on-TencentAGS/00-prepare-cluster-and-deploy-operator.md)
- [01. 准备 Tencent Agent Runtime 基础设施](../openclaw-browser-on-TencentAGS/01-prepare-tencent-agent-runtime.md)

如果你已经在同一个集群里按上面两章部署过 `openclaw-tencent-runtime`，这一章不需要重复部署 provider。

---

## 你需要填写的参数

这一篇大多数内容都可以直接复用。你通常只需要替换下面几个值：

| 参数 | 是否必填 | 示例 | 用途 |
|---|---|---|---|
| `HERMES_IMAGE` | 否 | `ccr.ccs.tencentyun.com/agentway/hermes:v2026.06.30-r1` | 要部署的 Hermes 镜像版本 |
| `HERMES_DASHBOARD_PASSWORD` | 是 | `替换成你的首登密码` | Dashboard 首次登录密码 |
| `HERMES_DASHBOARD_SESSION_SECRET` | 是 | `$(openssl rand -hex 32)` | Dashboard 会话签名密钥 |
| `HERMES_API_SERVER_KEY` | 是 | `$(openssl rand -hex 32)` | Hermes API Server 访问密钥 |
| `HERMES_MODEL_API_KEY` | 否 | `替换成你的模型 API Key` | 通过 `fileInjects` 写入 `/opt/data/config.yaml` 的模型密钥；只想先起 dashboard 时可留空 |

> 建议至少先替换 `HERMES_DASHBOARD_PASSWORD`、`HERMES_DASHBOARD_SESSION_SECRET`、`HERMES_API_SERVER_KEY` 三个值，再对外分享访问地址。
>
> Hermes 本身通过环境变量读取的启动参数仍然放在 `env` 中；模型配置、系统提示词这类文件型配置放在 `fileInjects` 中。客户需要改模型、扩展配置或调整 `SOUL.md` 时，直接编辑 YAML 里的文件内容即可。

---

## 这一步最终会得到什么

执行完本文后，你会得到一个：

- 运行在 Tencent AGS 上的 Hermes Dashboard Agent
- 可直接通过公网 URL 访问的登录入口
- 使用 `/opt/data` 持久化状态目录的 Hermes 实例
- 已带有 dashboard、gateway、健康检查探针的完整运行配置
- 通过 `fileInjects` 注入 `config.yaml` 和 `SOUL.md`，客户可以直接改 manifest 中的文件内容
- 默认预装一组 starter skills（当前示例为 `self-improving`、`github`）
- 可以继续复用同一路径保存配置和状态的部署方式

换句话说，你拿到的不是一个“只会创建对象的 YAML”，而是一份可以直接交付给客户环境使用的 Hermes Dashboard 示例。

---

## 使用 manifest

直接使用：

- `./manifests/hermes-dashboard-agent.yaml`

部署前先把 manifest 中的占位符替换为你自己的值：

| 占位符 | 替换为 |
|---|---|
| `CHANGE_ME_FIRST_BOOT_DASHBOARD_PASSWORD` | Dashboard 首次登录密码 |
| `CHANGE_ME_DASHBOARD_SESSION_SECRET` | Dashboard 会话签名密钥（建议 `openssl rand -hex 32`） |
| `CHANGE_ME_64_HEX_API_KEY` | Hermes API Server 访问密钥（建议 `openssl rand -hex 32`） |
| `CHANGE_ME_MODEL_API_KEY` | 模型 API Key（可留空，先起 dashboard） |

替换完成后执行：

```bash
kubectl apply -f ./hermes-dashboard-on-TencentAGS/manifests/hermes-dashboard-agent.yaml
```

---

## 这一份 YAML 里分别完成了什么

为了方便客户按业务视角理解，我把这份 YAML 拆成三层：

### 1. 让 Hermes Dashboard 本体能跑起来

`AgentProfile` 负责定义运行底座，包括：

- 使用哪一个 Hermes 镜像
- 入口命令是什么
- 主访问端口是多少
- 启动探针怎么做
- 持久化目录挂在哪里

在这个例子里，最关键的是：

- 主访问入口是 `9119`
- 对外路径固定为 `/login`
- `18080 /health` 只用于启动探针
- Hermes 状态目录统一放在 `/opt/data`

这决定的是：

> 这个 Hermes 实例要怎样启动、怎样存活、以及怎样对外暴露入口。

### 2. 按 Hermes 的真实读取方式配置参数

`AgentTemplate` 按 Hermes 的真实读取方式分两类配置：

- Hermes 原生通过环境变量读取或更适合由环境变量承载的参数继续放在 `env` 中，例如 Dashboard 监听、登录密码、session secret、API Server key、模型 API Key、`AGENT_SKILL_DIR`、`GATEWAY_ALLOW_ALL_USERS` 等
- Hermes 原生通过文件读取的内容放在 `fileInjects` 中，例如 `/opt/data/config.yaml` 和 `/opt/data/SOUL.md`；其中 `config.yaml` 通过 `$HERMES_MODEL_API_KEY` 引用模型密钥

### 3. 真正创建一个可访问的 Hermes Agent

`Agent` 对象本身负责把前面两层组合起来，并指定：

- 使用 `openclaw-tencent-runtime` 作为 `sandboxProviderRef`
- 对外使用 `authMode: none`

这里的 `authMode: none` 含义是：

- 不再额外叠加 AGS access token
- 让外部只处理 Hermes 自己的认证体系

这样客户排障时只需要面对 Hermes Dashboard 的登录认证，不需要再额外处理一层 AGS token。

---

## 执行步骤

先将上一节列出的占位符替换为你自己的值，然后 apply：

```bash
kubectl apply -f ./hermes-dashboard-on-TencentAGS/manifests/hermes-dashboard-agent.yaml
```

等待 Agent Running：

```bash
kubectl get agent hermes-dashboard-agent -n default -w
```

查看 dashboard 访问地址：

```bash
kubectl get agent hermes-dashboard-agent -n default -o jsonpath='{.status.accessURL}'
```

---

## 预期效果

部署成功后，你应该看到：

- `status.phase=Running`
- `status.accessURL` 非空
- 打开 `status.accessURL` 后，直接进入 Hermes 的登录页
- `/opt/data` 目录继续承载 Hermes 的持久化状态
- `18080 /health` 正常服务于启动探针

---

## 如何验证

```bash
kubectl get agent hermes-dashboard-agent -n default -o yaml
```

重点看这些字段：

- `status.phase`
- `status.accessURL`
- `status.storageSubPath`
- `status.bootstrapStatus`
- `status.fileInjectStatus`
- `status.skillStatus`

如果这些都正常，你就可以把 `status.accessURL` 复制到浏览器中打开。

如果页面打不开，优先排查：

1. `HERMES_DASHBOARD_BASIC_AUTH_PASSWORD` 是否仍是示例占位符
2. `HERMES_DASHBOARD_BASIC_AUTH_SECRET` 是否仍是示例占位符
3. `API_SERVER_KEY` 是否为空或过短
4. `status.fileInjectStatus` 是否为 `Applied`
5. `status.skillStatus` 是否为 `Applied`
6. `volumeMounts.mountPath` 是否误写成了别的目录
7. `volumeMounts.subpath` 是否被改成了错误路径

## 验证删除重建后保留数据

本示例绑定第 00 章的 `d5afc116` 版本，挂载字段是小写 `subpath`。`hermes-data` 固定使用 `default/hermes-dashboard-agent/hermes-data`，不会随 Agent UID 改变。显式 subpath 使用文件系统中的固定路径，不再拼接 Provider 的 `cfsStorage.path`。

以下步骤会重建示例 Agent，造成短暂不可用，请在测试实例上执行。先按第 00 章启用 connect API 并安装 `kubectl agent` 插件，然后写入独立验收文件：

```bash
kubectl agent exec -n default hermes-dashboard-agent -- bash -lc \
  'printf "%s\n" persistence-check > /opt/data/persistence-check.txt'
kubectl get agent hermes-dashboard-agent -n default \
  -o jsonpath='{.metadata.uid}{" "}{.status.volumeMounts}{"\n"}'
kubectl delete agent hermes-dashboard-agent -n default --wait=true
kubectl apply -f ./hermes-dashboard-on-TencentAGS/manifests/hermes-dashboard-agent.yaml
kubectl wait agent/hermes-dashboard-agent -n default \
  --for=jsonpath='{.status.phase}'=Running --timeout=600s
kubectl get agent hermes-dashboard-agent -n default \
  -o jsonpath='{.metadata.uid}{" "}{.status.volumeMounts}{"\n"}'
kubectl agent exec -n default hermes-dashboard-agent -- bash -lc \
  'test "$(cat /opt/data/persistence-check.txt)" = persistence-check'
```

验收应同时满足：Agent UID 已改变，`status.volumeMounts` 中 `hermes-data` 的 `storageSubPath` 仍为 `default/hermes-dashboard-agent/hermes-data`，最后一条命令退出码为 0。此检查需要真实 AGS/CFS 环境；本仓库的静态校验不能证明删除重建后的数据可读。
