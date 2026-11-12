# Managed Harness Cookbook

本目录通过可独立运行的示例介绍如何使用 `agr` 管理托管 Harness。托管 Harness 由平台提供 Agent 运行时镜像（Harness Engine），你只需选择引擎、模型、系统提示词，以及来自工具市场或私有 Registry 的 Skill、Plugin 和 MCP；平台在首次发布时自动创建 Sandbox Tool 和 Deployment，并通过 [ACP](https://agentclientprotocol.com) 对外提供对话入口。

与 [Deployment Cookbook](../deployment-cookbook/README_zh.md) 的区别：Deployment Cookbook 自己构建镜像、创建 Tool 和 Deployment；本目录不构建任何镜像，底层 Tool 和 Deployment 由 Harness 管理。

## 核心概念

| 资源 | 说明 | 命令 |
| --- | --- | --- |
| Model Provider | 一个模型服务来源（TokenHub 或 OpenAI 兼容服务）及其登记的模型。每次修改都生成一个不可变修订 | `agr model-provider`（别名 `agr mp`） |
| Harness | 可编辑的**草稿**：引擎与版本、模型、系统提示词、Skill、Plugin、MCP、Session Space | `agr harness` |
| Harness Revision | 草稿的**不可变快照**，同时固定当时每个 Model Provider 的修订。发布的对象是修订 | `agr harness revision` |
| Sandbox Tool / Deployment | 首次发布时平台自动创建的运行资源，之后的发布复用这两个资源 | `agr harness get` 可见其 ID |

一次配置变更的完整链路是：**改草稿（`update`）→ 冻结成修订（`revision create`）→ 发布（`publish`）**。发布只影响之后新建的实例，不重启已有实例，也不中断已有会话。

## 前置条件

- 已安装 **preview 通道**的 `agr`，并完成凭证初始化。`harness` 与 `model-provider` 命令只在 preview 版本中提供。从 [GitHub Releases](https://github.com/TencentCloudAgentRuntime/ags-cli/releases) 下载带 `-preview` 后缀的版本，或从源码安装：

  ```bash
  go install -tags=preview github.com/TencentCloudAgentRuntime/ags-cli/cmd/agr@<preview-tag>
  agr version   # channel: preview
  agr status
  agr doctor
  ```

  `go install` 必须带 `-tags=preview`，否则安装的是 stable 版本，不包含这些命令。

- 按官方[自定义沙箱角色与权限指南](https://cloud.tencent.com/document/product/1814/129691)创建 Agent Runtime CAM 角色，并向 CLI 使用的身份授予该角色的 `cam:PassRole` 权限。平台用这个角色创建 Sandbox Tool，并在后台读取 Agent Registry 与 TokenHub。
- CLI 使用的身份具备 Harness、Model Provider 的读写权限，以及底层 Sandbox Tool、Deployment 的创建、查询、删除和 `AcquireDeploymentToken` 权限。后续发布和删除仍以 Harness 创建者的身份管理底层资源。
- 在目标地域准备一个 **VPC 子网和安全组**。托管 Harness 只支持 VPC 网络；实例访问模型服务、Registry 和 MCP 需要出网能力，请确认子网所在 VPC 已配置 NAT 网关或其他公网出口。
- 一个 **TokenHub API Key 的 ApiKeyId**（形如 `ak-...`）。Model Provider 只保存 ApiKeyId，密钥值在发布时由平台读取，不写入任何资源。

所有示例都在 `ap-chongqing` 运行，每条命令显式指定 region。示例输出中的账号、资源 ID、时间和请求 ID 均已脱敏。

每个示例都会创建独立资源。请从命令输出中复制 ID，并在下一步按提示设置环境变量；完成后执行清理章节。

在本目录运行 `make run` 可列出可选场景。该命令只输出导航信息，不会创建云资源。

## 示例

| 示例 | 说明 |
| --- | --- |
| [simple](./simple/README_zh.md) | 登记 TokenHub 模型，创建 Harness 并等待首个修订发布，检查 ACP 入口，对话一次，最后清理全部资源。 |
| [revisions](./revisions/README_zh.md) | 修改草稿、比较差异、发布新修订、回滚到旧修订；更新 Model Provider 后通过新修订生效，并观察发布失败时线上修订不受影响。 |
| [connect](./connect/README_zh.md) | 四种接入方式：`prompt` 多轮对话、`acp` 接入编辑器、`proxy` 本地代理、`endpoint` 拿真实地址用 `curl` 走一遍 ACP Streamable HTTP。 |
| [tool-market](./tool-market/README_zh.md) | 从工具市场浏览并添加官方 MCP、Skill 和 Plugin：无需凭据的 MCP、使用托管凭据的 MCP、固定版本与升级，以及引用工具市场时的全部限制。 |
| [scaling-session](./scaling-session/README_zh.md) | 通过初始化配置设置资源规格、按需启动和空闲策略；用 Session Space 让会话跨实例保留，并说明哪些底层配置可以直接用 Deployment 命令调整。 |

每个场景目录中的 `README.md` 是英文版，`README_zh.md` 是中文版。

## 给 Agent 和脚本的约定

- 所有命令都支持 `-o json`，输出统一信封：`Status`、`Data`、`Failure{Code,Kind,Message,Hint,Fix,Details}`。按 `Failure.Code` 分支，不要匹配 `Message`。
- `agr harness status <harness-id> -o json --jq '.Data.Next'` 返回建议的下一条命令；没有待处理事项时为空字符串。
- `agr schema harness.create -o json` 查看参数、副作用与失败码；`--dry-run` 打印最终请求但不发送。
- 无 TTY 时，`harness delete` 和 `model-provider delete` 不加 `--yes` 会立即返回 `CONFIRMATION_REQUIRED`，不会挂起等待输入。
- `harness create` 和 `model-provider create` 不幂等，CLI 也不会自动重试。超时后先用 `agr harness list --name <name>` 核实，再决定是否重新创建。
