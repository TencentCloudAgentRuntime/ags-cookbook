# 托管 Harness 的变更、发布与回滚

本教程独立创建一个 Harness，依次演示：修改草稿并比较差异、发布新修订、回滚到旧修订、更新 Model Provider 后通过新修订生效，以及发布失败时线上修订不受影响。

开始前，请完成公共[前置条件](../README_zh.md#前置条件)和[配置](../README_zh.md#配置)。

| 对象 | 可以修改 | 何时对新实例生效 |
| --- | --- | --- |
| Harness 草稿 | 是，`harness update` | 创建并发布修订后 |
| Harness Revision | 否，创建后不可变 | 发布完成后 |
| Model Provider | 是，每次修改生成新的提供方修订 | Harness 创建并发布新修订后 |
| 标签和名称 | 是 | 不属于运行配置，无需发布 |

示例输出中的真实信息均已脱敏。

## 1. 设置环境变量并创建 Harness

```bash
set -a
source ../.env
set +a
bash ../scripts/preflight.sh revisions &&

export MODEL_PROVIDER_NAME="harness-revisions-$HARNESS_NAME_SUFFIX" &&
export HARNESS_NAME="harness-revisions-$HARNESS_NAME_SUFFIX" &&

MODEL_PROVIDER_ID=$(python3 ../scripts/resources.py create revisions model-provider \
  --name "$MODEL_PROVIDER_NAME" \
  --tokenhub-api-key-id "$TOKENHUB_API_KEY_ID" \
  --model hy3) && export MODEL_PROVIDER_ID
```

使用已保存的 Model Provider ID 创建 Harness：

```bash
HARNESS_ID=$(python3 ../scripts/resources.py create revisions harness \
  --name "$HARNESS_NAME" \
  --engine pi \
  --engine-version 1.3.0 \
  --model "$MODEL_PROVIDER_ID:hy3" \
  --system-prompt 'You are a helpful assistant.' \
  --role-arn "$AGR_ROLE_ARN" \
  --subnet-id "$HARNESS_SUBNET_ID" \
  --security-group-id "$HARNESS_SECURITY_GROUP_ID" \
  --wait) && export HARNESS_ID
```

修订 1 发布成功后，读取已保存的 Tool ID，后续查询实例时会用到：

```bash
HARNESS_TOOL_ID=$(python3 ../scripts/resources.py get revisions ToolId) && export HARNESS_TOOL_ID
echo "$HARNESS_TOOL_ID"
```

## 2. 修改草稿并比较差异

`harness update` 只修改草稿，线上实例不受影响。系统提示词可以直接写在参数里，也可以用 `@文件` 读取：

```bash
cat > prompt.md <<'EOF'
You are a release-notes assistant.
Always answer with a bullet list of at most three items.
EOF

agr harness update "$HARNESS_ID" --region "$AGR_REGION" --system-prompt @prompt.md
```

查看状态。`status` 会告诉你草稿与线上修订有几处不同，以及下一步该执行什么：

```bash
agr harness status "$HARNESS_ID" --region "$AGR_REGION"
```

```text
Harness:    hns-******** (harness-revisions-****)  ACTIVE
Live:       revision 1 (v1)  PUBLISHED  pi@1.3.0
Draft:      1 change(s) not yet published; see 'agr harness revision diff hns-******** live draft'
Resources:  tool=sdt-******** deployment=dpl-********
Next:       agr harness revision create hns-******** --publish --wait
```

按提示查看具体差异：

```bash
agr harness revision diff "$HARNESS_ID" live draft --region "$AGR_REGION"
```

```text
live (revision 1) -> draft: 1 change(s)
~ SystemPrompt  "You are a helpful assistant." -> "You are a release-notes assistant. ..."
```

`~` 表示修改，`+` 表示新增，`-` 表示删除。`revision diff` 的两个参数可以是修订号，也可以是 `live`（线上修订）、`latest`（最新修订）或 `draft`（草稿）。

只改标签不属于运行配置，不需要发布：

```bash
agr harness update "$HARNESS_ID" --region "$AGR_REGION" --tags env=demo --tags team=agents
```

## 3. 冻结并发布修订 2

`revision create` 把当前草稿冻结成一个新修订；加 `--publish --wait` 会立即发布并等待结果。

```bash
agr harness revision create "$HARNESS_ID" --region "$AGR_REGION" --publish --wait
```

成功输出如下：

```text
Harness:        hns-********
Revision:       2 (v2)
Status:         PUBLISHED
Engine:         pi@1.3.0
Models:         mp-********@1:hy3 (default)
System prompt:  You are a release-notes assistant. ...
Skills:         -
Plugins:        -
MCP servers:    -
Updated:        <masked-time>
Next: agr harness endpoint hns-******** --check   # new instances use this revision
```

`mp-********@1` 表示该修订固定使用 Model Provider 的修订 1。列出全部修订：

```bash
agr harness revision list "$HARNESS_ID" --region "$AGR_REGION"
```

```text
REVISION  NAME  STATUS      ENGINE    UPDATED          REASON
2         v2    PUBLISHED   pi@1.3.0  <masked-time>
1         v1    SUPERSEDED  pi@1.3.0  <masked-time>
```

一个 Harness 同一时刻最多只有一个 `PUBLISHED` 修订；被替换的修订变为 `SUPERSEDED`。

发布只影响之后新建的实例。已经在运行的实例继续使用旧配置，新会话也可能被路由到旧实例。要确认新提示词已生效，可以先删除旧实例，再发送一次 prompt：

```bash
agr instance list --tool-id "$HARNESS_TOOL_ID" --region "$AGR_REGION"
```

复制每个 `RUNNING` 或 `PAUSED` 实例的 ID 并删除，然后在 prompt 中提供版本变更内容，无需准备本地仓库：

```bash
export HARNESS_INSTANCE_ID='replace-with-instance-id'
agr instance delete "$HARNESS_INSTANCE_ID" --region "$AGR_REGION" --yes --wait

agr harness prompt "$HARNESS_ID" --region "$AGR_REGION" 'Write release notes for a todo app: added recurring tasks, fixed missed reminders, and improved startup time.'
```

回复应为不超过三条的列表。

## 4. 回滚到修订 1

没有单独的 rollback 命令：重新发布旧修订即可。

```bash
agr harness revision publish "$HARNESS_ID" 1 --region "$AGR_REGION" --wait
agr harness status "$HARNESS_ID" --region "$AGR_REGION"
```

```text
Harness:    hns-******** (harness-revisions-****)  ACTIVE
Live:       revision 1 (v1)  PUBLISHED  pi@1.3.0
Latest:     revision 2 (v2)  SUPERSEDED  pi@1.3.0
Draft:      1 change(s) not yet published; see 'agr harness revision diff hns-******** live draft'
Resources:  tool=sdt-******** deployment=dpl-********
Next:       agr harness revision create hns-******** --publish --wait
```

回滚不改变草稿，所以草稿仍然包含新提示词，`Next` 也提示可以重新发布它。这里先不执行，第 5 步会把它和模型变更一起发布。对已经是 `PUBLISHED` 的修订再次发布是安全的：CLI 直接返回成功，不发送请求。

```bash
agr harness revision publish "$HARNESS_ID" 1 --region "$AGR_REGION"
```

```text
Revision 1 of hns-******** is already PUBLISHED; nothing to do.
```

使用 `-o json` 时，`Data.AlreadyPublished` 为 `true`。

## 5. 更新 Model Provider

给 Model Provider 增加一个模型。把 `SECOND_MODEL_ID` 换成你的 TokenHub API Key 可以调用的另一个模型 ID。`--model` 会替换整个模型列表，因此要写上已有的 `hy3`：

```bash
export SECOND_MODEL_ID=glm-5.1

agr model-provider update "$MODEL_PROVIDER_ID" --region "$AGR_REGION" --model hy3 --model "$SECOND_MODEL_ID"
agr model-provider revision list "$MODEL_PROVIDER_ID" --region "$AGR_REGION"
```

```text
REVISION  NAME  SOURCE    MODELS                    CREATED
2         v2    TOKENHUB  hy3[TEXT], glm-5.1[TEXT]  <masked-time>
1         v1    TOKENHUB  hy3[TEXT]                 <masked-time>
```

已有的 Harness 修订仍然固定使用提供方修订 1。要使用新模型，先把它加入 Harness 的模型选择并设为默认，再创建新修订。新修订会固定 Model Provider 的最新修订：

```bash
agr harness update "$HARNESS_ID" --region "$AGR_REGION" \
  --model "$MODEL_PROVIDER_ID:hy3" \
  --model "$MODEL_PROVIDER_ID:$SECOND_MODEL_ID" \
  --default-model "$MODEL_PROVIDER_ID:$SECOND_MODEL_ID"

agr harness revision diff "$HARNESS_ID" live draft --region "$AGR_REGION"
```

```text
live (revision 1) -> draft: 3 change(s)
~ DefaultModel.Model  "hy3" -> "glm-5.1"
~ ModelProviders[mp-********].Models  ["hy3"] -> ["hy3","glm-5.1"]
~ SystemPrompt  "You are a helpful assistant." -> "You are a release-notes assistant. ..."
```

发布后再比较修订 1 和最新修订，可以看到提供方修订从 1 变为 2：

```bash
agr harness revision create "$HARNESS_ID" --region "$AGR_REGION" --publish --wait
agr harness revision diff "$HARNESS_ID" 1 latest --region "$AGR_REGION"
```

```text
revision 1 -> latest (revision 3): 5 change(s)
~ DefaultModel.Model  "hy3" -> "glm-5.1"
~ DefaultModel.Revision  1 -> 2
~ ModelProviders[mp-********].Models  ["hy3"] -> ["hy3","glm-5.1"]
~ ModelProviders[mp-********].Revision  1 -> 2
~ SystemPrompt  "You are a helpful assistant." -> "You are a release-notes assistant. ..."
```

只有两个修订之间的比较会展示提供方修订；与草稿比较时会忽略它，因为草稿尚未固定提供方修订。

## 6. 发布失败时线上修订不受影响

Skill 在发布时才会下载并校验。下面故意引用一个不存在的 Skill 版本，观察发布失败后的状态：

```bash
agr harness update "$HARNESS_ID" --region "$AGR_REGION" \
  --skill MARKETPLACE/rec-doesnotexist/rv-doesnotexist

agr harness revision create "$HARNESS_ID" --region "$AGR_REGION" --publish --wait
```

命令以 `WAIT_FAILED` 失败，错误信息包含新修订号和失败原因：

```text
Error: revision 4 was created but publishing failed: harness revision hns-********/4 publish finished with status "PUBLISH_FAILED": Skill preparation failed: ...
Code: WAIT_FAILED
Hint: Read StatusReason with 'agr harness revision get hns-******** 4', fix the cause, then retry with 'agr harness revision publish hns-******** 4 --wait'.
Fix: agr harness revision publish hns-******** 4 --wait
```

线上修订仍然是上一步发布的修订 3，已有实例不受影响：

```bash
agr harness status "$HARNESS_ID" --region "$AGR_REGION"
```

```text
Harness:    hns-******** (harness-revisions-****)  ACTIVE
Live:       revision 3 (v3)  PUBLISHED  pi@1.3.0
Latest:     revision 4 (v4)  PUBLISH_FAILED  pi@1.3.0: Skill preparation failed: ...
Draft:      1 change(s) not yet published; see 'agr harness revision diff hns-******** live draft'
Resources:  tool=sdt-******** deployment=dpl-********
Next:       agr harness revision publish hns-******** 4 --wait
```

`Next` 建议重试修订 4，这适用于失败原因在外部的情况。这里的原因是修订内容本身，重试仍会失败。修订内容不可变，所以修正方法是修改草稿。这里清空 Skill 即可：

```bash
agr harness update "$HARNESS_ID" --region "$AGR_REGION" --skill ''
agr harness status "$HARNESS_ID" --region "$AGR_REGION"
```

草稿重新与线上修订 3 一致：

```text
Harness:    hns-******** (harness-revisions-****)  ACTIVE
Live:       revision 3 (v3)  PUBLISHED  pi@1.3.0
Latest:     revision 4 (v4)  PUBLISH_FAILED  pi@1.3.0: Skill preparation failed: ...
Draft:      same as live revision
Resources:  tool=sdt-******** deployment=dpl-********
Next:       agr harness revision publish hns-******** 4 --wait
```

线上已经是正确的配置，忽略 `Next` 即可；下一次创建并发布新修订后，修订 4 就不再是最新修订。如果失败原因在外部（例如角色缺少 Registry 读权限），修复后直接重试同一个修订即可。

要使用真实的 Skill，先列出工具市场中的 Skill：

```bash
agr harness tool list --region "$AGR_REGION" --type skill
```

复制返回的 `REFERENCE`，然后用 `--skill MARKETPLACE/<record-id>/<version-id>` 引用。Plugin 使用 `--plugin`，与 Skill 不同，Plugin 在保存草稿时就会校验版本是否可读、是否兼容当前引擎。

## 7. 清理资源

删除本场景保存的资源。脚本从 `.state/` 读取 ID 和地域，等待删除完成并回查结果；清理中断后可以重复执行。

```bash
python3 ../scripts/resources.py cleanup revisions --yes
rm -f prompt.md
```

## 常见问题

| 现象 | 原因与处理 |
| --- | --- |
| `harness update` 或 `revision create` 返回 `ResourceInUse` | 同一个 Harness 有修订正在发布。用 `agr harness status` 等待 `PUBLISHING` 结束后再修改 |
| `--wait` 返回 `WAIT_PREEMPTED` | 等待期间另一个修订先发布完成，当前修订变为 `SUPERSEDED`。用 `agr harness status` 确认线上修订，再决定是否重新发布 |
| `--wait` 返回 `WAIT_TIMEOUT` | 本地等待超时，服务端仍在发布。按 `Hint` 继续等待，不要重复创建修订 |
| `model-provider update` 移除模型失败 | 该模型仍被某个 Harness 草稿选择。先用 `harness update --model` 去掉它 |
| `model-provider delete` 返回 `ResourceInUse` | 仍有 Harness 或其保留的修订引用该提供方。先删除 Harness |
| 新发布的提示词没有生效 | 请求仍落在发布前创建的实例上。按第 3 步删除旧实例后重试 |
