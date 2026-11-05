# DeepSeek Harness + AWV：鹈鹕骑车

[English](README.md)

用户在 Harness 页面提交需求，主 Agent 自动创建 Code、Review 任务，必要时修复，评审通过后发布网页。各阶段顺序挂载同一 AWV 工作区，验证不同 Pod、不同节点以及 Pod 重建后继续使用同一份文件。

本例通过 Kubernetes Job 和 Helm 运行，需自备 Kubernetes 与 AWV，不通过 AGS/E2B SDK 创建沙箱。[架构与能力边界](docs/architecture.md)说明内部流程和持久化范围。

## 前提条件

- 已安装 AWV 的 Kubernetes 集群，至少一个 Ready 的 **linux/amd64** 节点和可用 AWV StorageClass；本例不负责安装 AWV。
- 具有创建 Namespace、部署应用的权限；`make verify` 另需执行相应 RBAC 检查的权限。
- 集群能为作品创建 LoadBalancer Service；Harness 页面默认通过本机端口转发访问。
- 本地安装 Node.js >=22、pnpm **11.19.0**、支持 amd64 构建的 Docker、kubectl、Helm 3 和 jq。
- 可推送且集群可拉取的镜像仓库，以及 OpenAI Chat Completions 兼容模型；原示例使用 Token Hub 的 `deepseek/deepseek-flash`。
- 构建环境可下载依赖与 Chrome；Controller、Worker 可访问模型接口。

本地脚本面向 macOS 和 Linux，集群镜像固定为 amd64。原有集群测试不代表已验证 Mac 本机执行。

## 配置与安装依赖

```bash
cd examples/dsh-awv-pelican
cp .env.example .env
make setup
```

先通过本机 Node 包管理工具安装 pnpm 11.19.0。`make setup` 安装各目录锁定的依赖，TypeScript 测试通过 tsx 直接运行；插件的 JavaScript 包仅在镜像构建时生成。

按 `.env.example` 填写参数。文件由 dotenv 加载，进程环境变量优先；填写字面值，不使用 Shell 命令替换，也不需要 `source .env`。

| 参数 | 用途 |
| --- | --- |
| `KUBECONFIG` | 目标集群配置的绝对路径 |
| `NAMESPACE` | 独立演示命名空间，默认 `dsh-awv` |
| `REGISTRY`、`IMAGE_TAG` | 可写镜像仓库路径与版本，本例不假设已有可用演示镜像 |
| `STORAGE_CLASS` | 集群中已有的 AWV StorageClass，默认 `awv-btrfs` |
| `OPENAI_BASE_URL`、`OPENAI_API_TYPE` | 模型接口地址与类型 |
| `DSH_MODEL` | 主 Agent 模型；Code、Review 可通过 `DSH_CODE_MODEL`、`DSH_REVIEW_MODEL` 覆盖 |
| `MODEL_SECRET` | 当前 Namespace 中的模型 Secret 名称 |
| `IMAGE_PULL_SECRET`、`DOCKER_CONFIG_FILE` | 私有镜像拉取 Secret 及 Docker 认证 JSON；公共镜像可留空 |
| `CODE_NODE`、`REVIEW_NODE`、`SITE_NODE` | 跨节点验证时填写三个不同的 Ready amd64 节点，普通演示可留空 |
| `CONTROLLER_NODE` | 可选的 Controller 节点 |
| `OUTPUT_DIR` | 可选的产物绝对路径，默认当前示例下不纳入 Git 的 `.local/` |

模型 Key 通过当前进程环境变量 `OPENAI_API_KEY` 提供，可由密钥管理工具或终端隐藏输入设置。安装脚本据此创建 Kubernetes Secret；不要写入 `.env`、镜像或工作区。Mac Docker 配置若只包含系统钥匙串认证助手，需导出 Kubernetes 可用的认证 JSON，不能直接复制助手配置。

## 构建和运行

先用 Docker 登录 `REGISTRY`，再执行：

```bash
make preflight
make build
make run
make verify
make access
```

`make build` 构建并推送 **linux/amd64** 的 Controller、Worker 镜像，将 Digest 保存到 `.local/images.env` 或指定的 `OUTPUT_DIR`。`make run` 按 Digest 部署 Controller、命名空间级 RBAC、模型 Secret 和 AWV PVC，不自动提交模型任务。

`make access` 显示 Controller 最近的日志，并将 Web 转发到 `http://127.0.0.1:3080`。保留该终端，在浏览器中打开日志里带 `?token=` 的登录链接，然后提交 [创建提示词](examples/prompts/create-pelican.md)。预期工具调用如下：

```text
code_agent → review_agent → 必要时 code_agent 修复、review_agent 复审 → publish_site
```

最终回复应包含评审结果和作品的 LoadBalancer 地址。Agent 报错或评审未通过时不得发布。页面保存在 AWV PVC `pelican-workspace`；Controller 不挂载这个卷。

也可以从仓库根目录运行：

```bash
make example-setup EXAMPLE=dsh-awv-pelican
make example-run EXAMPLE=dsh-awv-pelican
```

远程开放 Harness 页面时，需通过 Helm 显式配置 Service 和 `controller.trustedHosts`，host 不包含协议和路径。它只处理 Host 校验，不提供 TLS 或网络隔离。优先使用本机端口转发，修改访问方式前阅读[架构说明](docs/architecture.md)。

## 验证

```bash
make check  # 类型、Shell、Harness YAML 语法、Helm lint 和渲染校验
make test   # Provider 单元测试，不访问集群或模型
make e2e    # 两轮真实模型任务及展示 Pod 重建验证
```

E2E 会覆盖演示页面、注入移动端布局缺陷并产生模型调用费用，只能在专用演示 Namespace 和 PVC 上运行。日志、HTML、任务耗时等保存在忽略目录。跨节点验证必须显式填写三个不同节点；未填写时不能据执行成功认定跨节点通过。[验证说明](docs/validation.md)区分历史证据与本次验收。

当前固定 Harness `0.1.5-rc.2` 能完成真实浏览器导航、截图、DOM/布局、交互及控制台检查，但截图图像块未传入模型上下文，不能称为模型已完成截图识图。AWV 只保存文件，不保存进程、浏览器或模型上下文；Controller 重建后不会自动恢复 Harness 会话。

## 常见问题

| 现象 | 检查项 |
| --- | --- |
| 找不到 `images.env` | 使用同一 `OUTPUT_DIR` 完成 `make build` 后再部署 |
| PVC 或 Job Pending | StorageClass、AWV、节点资源、镜像拉取、节点选择与卷挂载事件 |
| Mac 构建镜像无法运行 | 确认镜像为 linux/amd64，检查拉取 Secret 的认证 JSON |
| Web 页面可打开但接口返回 403 | 保留登录 token；远程访问需配置 `controller.trustedHosts` |
| 工作区被锁定 | 检查运行中的 Job、展示 Pod 和 Lease；确认无活动任务后才处理过期 Lease |
| 评审失败或发布被拒绝 | 查看 Review 的 `blocking_issues` 以及状态中的 generation 和 review 字段 |
| 作品没有公网地址 | 检查集群 LoadBalancer 能力、配额和 Service 事件 |
| 跨节点挂载慢 | 查看旧节点卸载与新节点挂载事件，不强制解绑活动卷 |

```bash
make status
# 用 .env 中的实际值替换占位符：
kubectl --kubeconfig <path> -n <namespace> get events --sort-by=.lastTimestamp
kubectl --kubeconfig <path> -n <namespace> logs job/<job-name>
```

## 清理

```bash
make clean
```

默认仅删除计算资源，保留 PVC 和凭证 Secret。确认不再需要数据及凭证后，再单独删除演示 PVC 或 Namespace。删除后的数据恢复取决于 StorageClass 回收策略与备份。
