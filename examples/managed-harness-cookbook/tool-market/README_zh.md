# 从工具市场为托管 Harness 添加官方 MCP、Skill 和 Plugin

工具市场提供平台发布的官方 MCP Server、Skill 和 Plugin。本教程独立创建一个 Harness，先浏览工具市场，再分别添加一个无需凭据的 MCP、一个需要用户自己 API Key 的 MCP，最后说明 Skill 和 Plugin 的引用规则以及常见限制。

开始前，请完成公共[前置条件](../README_zh.md#前置条件)和[配置](../README_zh.md#配置)。示例输出中的真实信息均已脱敏。

## 工具市场是什么

工具市场不是一个单独的资源，而是 Agent Registry 中的官方 Registry。查询时使用固定的虚拟 Registry ID `MARKETPLACE`，服务端会映射到当前地域的官方 Registry。不同地域上架的工具可能不同。

| 市场中的类型 | `--type` | 写入 Harness 的字段 | 引用参数 |
| --- | --- | --- | --- |
| `MCP` | `mcp` | `MCPServers` | `--mcp <name>=MARKETPLACE/<record-id>/<version-id>` |
| `AGENT_SKILLS` | `skill` | `Skills` | `--skill MARKETPLACE/<record-id>/<version-id>` |
| `PLUGIN` | `plugin` | `Plugins` | `--plugin MARKETPLACE/<record-id>/<version-id>` |

其他类型（例如 A2A）不能被 Harness 引用。

## 引用工具市场时的限制

| 限制 | 说明 |
| --- | --- |
| 固定版本 | 引用必须写明 `VersionId`，不支持 `latest` 或 `stable` 标签。工具发布新版本后，Harness 不会自动升级；需要把引用改成新版本，再创建并发布新修订。 |
| 版本状态 | 只有已审批（`APPROVED`）且内容就绪（`READY`）的版本可用。`agr harness tool list` 只列出每个工具的 `stable` 版本。 |
| 访问身份 | 平台在保存和发布时都使用创建 Harness 时的初始化角色（`--role-arn`）读取 Registry，而不是当前调用者。 |
| Plugin 兼容性 | Plugin 版本必须声明与 Harness **完全一致**的引擎和版本（例如 `pi` + `1.3.0`）。保存草稿时就会校验；修改引擎或引擎版本时，会重新校验已选的全部 Plugin。 |
| Skill 校验时机 | Skill 保存时不校验，发布时才下载。版本不可读，或两个 Skill 的 `SKILL.md` 名称相同，都会让修订进入 `PUBLISH_FAILED`。Skill 适用于所有引擎。 |
| MCP 传输 | 只使用 MCP 声明中的第一个 `streamable-http` 远端；只有 `sse`、stdio 或本地包的 MCP 无法使用。MCP 适用于所有引擎。 |
| MCP 请求头 | 市场声明了必填请求头但没有默认值时（通常是 API Key），必须用 `--mcp-header` 显式提供，否则保存时被拒绝。同名请求头不区分大小写，你提供的值会覆盖市场的默认值。 |
| MCP 凭据 | 托管凭据只会替换你自己写在 `--mcp-header` 中的 `${credential}`，不会自动填进市场声明的请求头。每个 MCP 只能绑定一个凭据。 |
| MCP 名称 | pi 和 dsh 只接受 1～32 个字母、数字、`_` 或 `-`。CLI 在本地校验；用 `--mcp-servers` JSON 绕过时，不合规的名称要等到实例启动才失败。 |
| 下架 | 已引用的版本被下架后，新的发布会失败；已运行的实例不受影响。Skill 和 Plugin 的下载链接无法再刷新，链接过期后新建的实例可能启动失败。 |

## 1. 设置环境变量并创建 Harness

```bash
set -a
source ../.env
set +a
bash ../scripts/preflight.sh tool-market &&

export MODEL_PROVIDER_NAME="harness-market-$HARNESS_NAME_SUFFIX" &&
export HARNESS_NAME="harness-market-$HARNESS_NAME_SUFFIX" &&

MODEL_PROVIDER_ID=$(python3 ../scripts/resources.py create tool-market model-provider \
  --name "$MODEL_PROVIDER_NAME" \
  --tokenhub-api-key-id "$TOKENHUB_API_KEY_ID" \
  --model hy3) && export MODEL_PROVIDER_ID
```

使用已保存的 Model Provider ID 创建 Harness：

```bash
HARNESS_ID=$(python3 ../scripts/resources.py create tool-market harness \
  --name "$HARNESS_NAME" \
  --engine pi \
  --engine-version 1.3.0 \
  --model "$MODEL_PROVIDER_ID:hy3" \
  --role-arn "$AGR_ROLE_ARN" \
  --subnet-id "$HARNESS_SUBNET_ID" \
  --security-group-id "$HARNESS_SECURITY_GROUP_ID" \
  --wait) && export HARNESS_ID
```

修订 1 发布成功后，读取已保存的 Tool ID：

```bash
HARNESS_TOOL_ID=$(python3 ../scripts/resources.py get tool-market ToolId) && export HARNESS_TOOL_ID
```

## 2. 浏览工具市场

```bash
agr harness tool list --region "$AGR_REGION" --type mcp
```

预期输出格式如下，实际工具以当前地域为准：

```text
TYPE  NAME             REFERENCE                             VERSION     AUTH      ENGINES
mcp   GitHub           MARKETPLACE/rec-********/rv-********  <version>   required  all
mcp   DeepWiki         MARKETPLACE/rec-********/rv-********  <version>   none      all
mcp   Microsoft Learn  MARKETPLACE/rec-********/rv-********  <version>   none      all
...
```

- `REFERENCE` 就是要传给 Harness 的固定版本引用。
- `AUTH` 为 `required` 表示需要你自己的 API Key 或 Token。
- `ENGINES` 只对 Plugin 有意义；MCP 和 Skill 显示 `all`。

按关键词搜索，或只看当前 Harness 能用的 Plugin：

```bash
agr harness tool list --region "$AGR_REGION" --search github
agr harness tool list --region "$AGR_REGION" --type plugin --compatible-with "$HARNESS_ID"
```

`--compatible-with` 会读取 Harness 当前草稿的引擎和版本。与 `--type plugin` 一起使用时，服务端只返回声明支持该引擎版本的 Plugin；不加 `--type` 时返回全部工具，并用 `USABLE` 列标出该 Harness 能否使用。

## 3. 添加无需凭据的 MCP

查看 DeepWiki 的详情。把 `rec-replace-me` 换成上一步列表中 DeepWiki 的 Record ID：

```bash
export DEEPWIKI_RECORD_ID='rec-replace-me'

agr harness tool get "$DEEPWIKI_RECORD_ID" --region "$AGR_REGION"
```

```text
Name:         DeepWiki
Type:         mcp
Reference:    MARKETPLACE/rec-********/rv-********
Version:      <version>
Publisher:    Cognition
Description:  读取公开代码仓库的知识文档、了解项目架构并进行基于仓库内容的问答……
Endpoint:     https://mcp.deepwiki.com/mcp
Credentials:  not required

Add to a harness (on update the list replaces the current one; repeat the items to keep):
  agr harness update <harness-id> --mcp deepwiki=MARKETPLACE/rec-********/rv-********
```

复制 `Reference`，添加到 Harness 并发布：

```bash
export DEEPWIKI_REF='MARKETPLACE/rec-replace-me/rv-replace-me'

agr harness update "$HARNESS_ID" --region "$AGR_REGION" --mcp "deepwiki=$DEEPWIKI_REF"
agr harness revision create "$HARNESS_ID" --region "$AGR_REGION" --publish --wait
```

保存时服务端会读取该 MCP 版本，检查类型、状态、远端和必填请求头，不合规会直接拒绝。发布完成后，删除旧实例再试用新工具（发布只影响之后新建的实例）：

```bash
agr instance list --tool-id "$HARNESS_TOOL_ID" --region "$AGR_REGION"
export HARNESS_INSTANCE_ID='replace-with-instance-id'
agr instance delete "$HARNESS_INSTANCE_ID" --region "$AGR_REGION" --yes --wait

agr harness prompt "$HARNESS_ID" --region "$AGR_REGION" \
  'Use the deepwiki tool to summarize the architecture of the facebook/react repository in three bullets.'
```

回复过程中会出现以 `⋯` 开头的工具调用进度行。

要确认 MCP 确实被调用，可使用 `-o json`，检查 `Data.ToolCalls` 中是否有名为 `mcp__deepwiki__...`、状态为 `completed` 的调用。使用 `-o ndjson` 时，还可以在 `tool_call_update` 事件中查看工具的实际返回结果。

## 4. 添加需要 API Key 的 MCP

很多官方 MCP 需要用户自己的 API Key。以 GitHub 为例：

```bash
export GITHUB_RECORD_ID='rec-replace-me'

agr harness tool get "$GITHUB_RECORD_ID" --region "$AGR_REGION"
```

```text
Name:         GitHub
Type:         mcp
Reference:    MARKETPLACE/rec-********/rv-********
Version:      <version>
Publisher:    GitHub
Description:  访问 GitHub 代码仓库、Issue、Pull Request 和研发协作信息……
Endpoint:     https://api.githubcopilot.com/mcp/
Credentials:  required (get one at https://github.com/settings/personal-access-tokens)
Header:       Authorization: Bearer {access_token}  (you must set it)

Add to a harness (on update the list replaces the current one; repeat the items to keep):
  agr harness update <harness-id> --mcp github=MARKETPLACE/rec-********/rv-******** --mcp-credential github=<credential-provider-id>/<user-id>/<scope> --mcp-header 'github:Authorization=Bearer ${credential}'
Store the secret first: 'agr credential provider create --type SecretMultiUser', then 'agr credential secret set'.
```

市场声明的请求头是 `Bearer {access_token}`，其中的变量没有默认值，必须由你提供。推荐用托管凭据保存 Token，Harness 里只保存凭据引用。

**第一步：创建凭据提供商并保存 Token。**

```bash
GITHUB_CREDENTIAL_PROVIDER_ID=$(python3 ../scripts/resources.py create tool-market credential-provider --name "harness-market-github-$HARNESS_NAME_SUFFIX" --type SecretMultiUser) && export GITHUB_CREDENTIAL_PROVIDER_ID
```

Provider ID 已保存到 `GITHUB_CREDENTIAL_PROVIDER_ID`，接下来保存 Token。用户 ID 和 scope 由应用定义；本示例的 Harness 引用和清理脚本统一使用 `harness-market` 和 `github`：

```bash
agr credential secret set --region "$AGR_REGION" \
  --credential-provider-id "$GITHUB_CREDENTIAL_PROVIDER_ID" \
  --user-id harness-market --scope github \
  --secret 'github_pat_replace-me'
```

**第二步：添加 MCP。** `--mcp` 会替换全部 MCP，因此要同时写上第 3 步的 DeepWiki：

```bash
export GITHUB_REF='MARKETPLACE/rec-replace-me/rv-replace-me'

agr harness update "$HARNESS_ID" --region "$AGR_REGION" \
  --mcp "deepwiki=$DEEPWIKI_REF" \
  --mcp "github=$GITHUB_REF" \
  --mcp-credential "github=$GITHUB_CREDENTIAL_PROVIDER_ID/harness-market/github" \
  --mcp-header 'github:Authorization=Bearer ${credential}'

agr harness revision diff "$HARNESS_ID" live draft --region "$AGR_REGION"
agr harness revision create "$HARNESS_ID" --region "$AGR_REGION" --publish --wait
```

`${credential}` 必须写在单引号里，避免被 shell 展开。平台在实例访问 MCP 时读取密钥并替换 `${credential}`，密钥不会写进 Harness 或修订。

关于请求头和凭据，还需要注意：

- 只写 `--mcp github=...` 而不提供 `Authorization`，保存时会报 `Registry MCP header "Authorization" is required and has no value or default`。
- 只写 `--mcp-credential` 而没有任何 `--mcp-header` 使用 `${credential}`，凭据永远不会被读取，CLI 会直接拒绝（`UNUSED_MCP_CREDENTIAL`）。
- 有的 MCP 需要多个密钥请求头（例如同时需要 SecretId 和 SecretKey）。一个 MCP 只能绑定一个凭据，所以其余请求头只能用明文 `--mcp-header` 提供，**明文值会保存在 Harness 配置中**，有 Harness 读取权限的人都能看到。这类工具请使用权限最小的子账号密钥。

## 5. 添加 Skill 和 Plugin

Skill 和 Plugin 的引用方式相同，只是写入不同字段：

```bash
agr harness tool list --region "$AGR_REGION" --type skill
agr harness tool list --region "$AGR_REGION" --type plugin --compatible-with "$HARNESS_ID"
```

如果当前地域的工具市场还没有上架 Skill 或 Plugin，命令会输出 `No tools found`。有可用工具时，复制 `REFERENCE` 后添加：

```bash
agr harness update "$HARNESS_ID" --region "$AGR_REGION" \
  --skill MARKETPLACE/rec-replace-me/rv-replace-me \
  --plugin MARKETPLACE/rec-replace-me/rv-replace-me
agr harness revision create "$HARNESS_ID" --region "$AGR_REGION" --publish --wait
```

两者的校验时机不同：

- **Plugin** 在 `harness update` 时就会校验。引擎不兼容时报 `InvalidParameter`，消息为 `Plugin must reference a version that declares the selected Harness Engine version`。以后修改 `--engine` 或 `--engine-version`，也会重新校验已选的 Plugin。
- **Skill** 在 `harness update` 时不校验，要到发布时才下载。失败时修订进入 `PUBLISH_FAILED`，原因可用 `agr harness revision get <harness-id> <revision>` 查看；线上修订不受影响。处理方法见 [revisions](../revisions/README_zh.md#6-发布失败时线上修订不受影响)。

`--skill` 和 `--plugin` 同样会替换整个列表，更新时要写上想保留的项。

## 6. 升级到工具的新版本

引用固定在某个 `VersionId`。工具发布新版本后，先查看 `stable` 版本，再把引用改成新版本：

```bash
agr harness tool get "$GITHUB_RECORD_ID" --region "$AGR_REGION" -o json --jq '.Data.Tool.Reference'
```

如果输出与当前 `GITHUB_REF` 不同，用新的引用重复第 4 步的 `harness update`，再发布新修订。也可以用 `agr harness tool get <record-id>/<version-id>` 查看某个指定版本。

## 7. 清理资源

删除本场景保存的资源。脚本从 `.state/` 读取 ID 和地域，等待删除完成并回查结果；清理中断后可以重复执行。如果执行了第 4 步，也会删除托管密钥，将凭据提供者设为 `DISABLED` 后再删除。

```bash
python3 ../scripts/resources.py cleanup tool-market --yes
```

## 常见问题

| 现象 | 原因与处理 |
| --- | --- |
| `harness tool list` 返回 `ResourceUnavailable` | 当前地域还没有开放工具市场。换一个地域，或改用私有 Registry |
| 保存时报 `Registry MCP header "X" is required and has no value or default` | 该 MCP 需要你提供请求头 X。按第 4 步加 `--mcp-header` 和 `--mcp-credential` |
| 保存时报 `Registry MCP descriptors have no supported streamable-http remote` | 该 MCP 没有 streamable-http 远端，Harness 无法使用 |
| 保存时报 `Registry source type does not match the selected use` | 引用的类型用错了位置，例如把 Skill 写进了 `--mcp`。按 `harness tool get` 显示的 `Type` 选择参数 |
| 保存时报 `Plugin must reference a version that declares the selected Harness Engine version` | Plugin 不兼容 Harness 的引擎版本，或该版本不可用。用 `--compatible-with` 选择兼容版本 |
| 保存时报 `... is not readable with InitializeConfiguration.SandboxTool.RoleArn` | 初始化角色无法读取 Registry。检查角色权限 |
| 发布失败，原因为 `Skill preparation failed` | Skill 版本不可读或与其他 Skill 同名。修改草稿后创建新修订 |
| 实例启动时报 MCP 名称不合法 | 通过 `--mcp-servers` 写入了含 `.` 等字符的名称。改用 `--mcp`，名称只用字母、数字、`_` 和 `-` |
| MCP 调用返回 401 | Token 无效，或 `--mcp-credential` 的 user-id/scope 与 `credential secret set` 时不一致 |
