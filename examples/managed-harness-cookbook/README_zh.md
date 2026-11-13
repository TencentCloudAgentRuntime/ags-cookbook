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

**发布后，新会话仍可能落到旧实例。** 验证新修订时，按 [revisions](./revisions/README_zh.md#3-冻结并发布修订-2) 删除旧实例，再发送 prompt。只换一个 SessionId 不能保证使用新修订。

## 前置条件

- 已安装 **preview 通道**的 `agr`，完成凭证初始化，并包含 [CLI PR #171](https://github.com/TencentCloudAgentRuntime/ags-cli/pull/171) 中的托管 Harness 命令。较旧的 preview 构建可能尚未包含这些命令。从 [GitHub Releases](https://github.com/TencentCloudAgentRuntime/ags-cli/releases) 下载包含这些命令且带 `-preview` 后缀的版本，或从源码安装：

  ```bash
  go install -tags=preview 'github.com/TencentCloudAgentRuntime/ags-cli/cmd/agr@<preview-tag>'
  agr version   # channel: preview
  agr harness --help
  agr harness web --help
  agr model-provider --help
  agr status
  agr doctor
  ```

  将 `<preview-tag>` 替换为目标 preview release 的 tag。`go install` 必须带 `-tags=preview`，否则安装的是 stable 版本，不包含这些命令。

  如果尚无包含这些命令的 release，使用 Go 1.25 或更新版本在单独目录构建 CLI PR，并在所有示例中使用该二进制：

  ```bash
  git clone https://github.com/TencentCloudAgentRuntime/ags-cli.git
  git -C ags-cli fetch origin pull/171/head
  git -C ags-cli switch --detach FETCH_HEAD
  (cd ags-cli && go build -tags preview -o ./build/agr ./cmd/agr)
  export PATH="$PWD/ags-cli/build:$PATH"
  agr version   # channel: preview
  agr harness --help
  agr harness web --help
  agr model-provider --help
  ```

- 按官方[自定义沙箱角色与权限指南](https://cloud.tencent.com/document/product/1814/129691)创建 Agent Runtime CAM 角色，并向 CLI 使用的身份授予该角色的 `cam:PassRole` 权限。平台用这个角色创建 Sandbox Tool，并在后台读取 Agent Registry 与 TokenHub。
- CLI 使用的身份具备 Harness、Model Provider 的读写权限，以及底层 Sandbox Tool、Deployment 的创建、查询、删除和 `AcquireDeploymentToken` 权限。后续发布和删除仍以 Harness 创建者的身份管理底层资源。
- 在目标地域准备一个 **VPC 子网和安全组**。托管 Harness 只支持 VPC 网络；实例访问模型服务、Registry 和 MCP 需要出网能力，请确认子网所在 VPC 已配置 NAT 网关或其他公网出口。
- 一个 **TokenHub API Key 的 ApiKeyId**（形如 `ak-...`）。Model Provider 只保存 ApiKeyId；Harness、ModelProvider 及其修订不包含密钥值。平台在发布时读取密钥，并将其作为字面值写入底层 Sandbox Tool 的 `NetworkPolicy` 请求头注入规则。有权查询该 Tool 的身份可以读取密钥，因此 Tool 的读取权限也意味着对该密钥的访问权限。

所有示例都在 `ap-chongqing` 运行，每条命令显式指定 region。示例输出中的账号、资源 ID、时间和请求 ID 均已脱敏。

每个示例都会创建独立资源。创建命令通过 `scripts/resources.py` 调用 `agr`，提取返回的 ID，与地域、控制面 endpoint 一起保存到 `.state/<scenario>.json`；其余步骤直接使用 `agr`。完成后执行清理章节。

在本目录运行 `make run` 可列出可选场景。该命令只输出导航信息，不会创建云资源。

## 配置

辅助脚本需要 Python 3 和 Bash。在本目录准备一次公共配置：

```bash
make setup
```

参考 [.env.example](./.env.example) 编辑 `.env`，填写地域、角色 ARN、子网、安全组、TokenHub ApiKeyId 和唯一的名称后缀。所有场景都加载这个文件。

需要自定义控制面 endpoint 时，在 `.env` 中设置 `AGR_CLOUD_ENDPOINT`，或使用已有的 `agr` 配置；教程进行期间应保持配置一致。脚本通过 `agr config show` 读取有效 endpoint（包括 CLI 默认值），在创建资源前保存为 `CloudEndpoint`。创建命令不接受单独传入 `--cloud-endpoint` 或 `--config`，同一个未清理的场景也不能混用不同 endpoint。

然后检查要运行的场景：

```bash
make preflight SCENARIO=simple
```

预检会检查必填配置、preview CLI 命令并运行 `agr doctor`。`connect` 还会检查 CLI 是否包含 `harness web`，并要求安装 `curl`。缺少 `npx` 或 Node.js 22.13 及更新版本时只会警告：只有可选的 acpx 示例需要它们，仍可继续使用其他接入方式。预检不会创建云资源。如果预检失败，先修复提示的问题，再继续后续步骤。

创建脚本会输出 ID，供 shell 变量接收，并将其保存，供后续步骤使用。如果等待失败前服务已返回 ID，这个 ID 也会保留用于清理。在新终端中将同一个 preview CLI 加入 `PATH` 后，可以这样恢复变量：

```bash
set -a
source .env
set +a
HARNESS_ID=$(python3 scripts/resources.py get simple HarnessId) && export HARNESS_ID
```

也可以脱离教程，使用已记录的地域、endpoint 和 ID 单独清理：

```bash
python3 scripts/resources.py cleanup simple --dry-run
make cleanup SCENARIO=simple
```

`make cleanup` 会加载已有的 `.env`。两个清理入口都会显式传入已记录的 endpoint，即使换到新终端或修改了 CLI 配置，也会查询原 endpoint。清理会等待删除完成并回查资源是否已不存在，可以重复执行。

旧状态文件如果没有 `CloudEndpoint`，脚本会在查询或删除资源前报错停止。请先核实创建时使用的 endpoint，再将其补入状态文件；不要假定当前 CLI endpoint 就是原值。只有确认原 endpoint 上的资源已不存在后，才能移除旧状态文件。

如果网络中断导致创建结果未知，先按 `Pending` 中记录的资源名称，在已记录的 endpoint 上用 `agr list/get` 核实，手动完成这部分清理后再移除状态文件。不要直接重试结果未知的创建。

## 示例

| 示例 | 说明 |
| --- | --- |
| [simple](./simple/README_zh.md) | 登记 TokenHub 模型，创建 Harness 并等待首个修订发布，检查 ACP 入口，对话一次，最后清理全部资源。 |
| [revisions](./revisions/README_zh.md) | 修改草稿、比较差异、发布新修订、回滚到旧修订；更新 Model Provider 后通过新修订生效，并观察发布失败时线上修订不受影响。 |
| [connect](./connect/README_zh.md) | DSH Harness 的五种接入方式：`prompt` 多轮对话、`acp` 接入编辑器、`proxy` 本地代理、`endpoint` 获取真实 ACP 地址、`web` 打开原生浏览器控制台，并用 `curl` 走一遍 ACP Streamable HTTP。 |
| [tool-market](./tool-market/README_zh.md) | 从工具市场浏览并添加官方 MCP、Skill 和 Plugin：无需凭据的 MCP、使用托管凭据的 MCP、固定版本与升级，以及引用工具市场时的全部限制。 |
| [scaling-session](./scaling-session/README_zh.md) | 通过初始化配置设置资源规格、按需启动和空闲策略；用 Session Space 让会话跨实例保留，并说明哪些底层配置可以直接用 Deployment 命令调整。 |

每个场景目录中的 `README.md` 是英文版，`README_zh.md` 是中文版。

## 给 Agent 和脚本的约定

- 支持 `-o json` 的命令输出统一信封：`Status`、`Data`、`Failure{Code,Kind,Message,Hint,Fix,Details}`。用 `Failure.Kind` 判断 `not_found` 等错误类别，用 `Failure.Code` 区分具体错误，不要匹配 `Message`。`harness acp` 使用 stdio 上的原始 ACP 消息，应显式加 `-o text`，包括默认输出已配置为 JSON 的情况。
- `agr harness status <harness-id> -o json --jq '.Data.Next'` 返回建议的下一条命令；没有待处理事项时为空字符串。
- `agr schema harness.create -o json` 查看参数、副作用与失败码；`--dry-run` 打印最终请求但不发送。
- 无 TTY 时，`harness delete` 和 `model-provider delete` 不加 `--yes` 会立即返回 `CONFIRMATION_REQUIRED`，不会挂起等待输入。
- `harness create` 和 `model-provider create` 不幂等，CLI 也不会自动重试。超时后先用 `agr harness list --name <name>` 核实，再决定是否重新创建。
- 接入 Session Space 后，同一个 Harness 的所有会话都使用 Harness ID 作为 UserId。应用需要记录会话归属并校验访问权限，这不会自动隔离应用里的不同用户。
- MCP 凭据引用在 Harness 配置中固定了提供商、UserId 和 scope。使用该 MCP 的所有会话共用这份凭据，切换 SessionId 不会自动换成当前应用用户的凭据。详见 [tool-market](./tool-market/README_zh.md#4-添加需要-api-key-的-mcp)。
- 应用应按 SessionId 串行发送请求。会话持久化不负责协调并发写入，不要让两个实例同时向同一个会话发送对话轮次。
