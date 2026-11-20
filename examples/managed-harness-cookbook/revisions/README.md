# Change, publish, and roll back a managed harness

This tutorial creates its own harness and walks through editing the draft and comparing it, publishing a new revision, rolling back to an earlier revision, picking up a model provider update through a new revision, and confirming that a failed publish leaves the live revision untouched.

Complete the shared [prerequisites](../README.md#prerequisites) and [configuration](../README.md#configuration) before starting.

| Object | Editable | When new instances pick it up |
| --- | --- | --- |
| Harness draft | Yes, `harness update` | After a revision is created and published |
| Harness revision | No, immutable once created | When publishing finishes |
| Model provider | Yes; every change creates a new provider revision | After the harness creates and publishes a new revision |
| Tags and name | Yes | Not runtime configuration; no publish needed |

Use a separate harness as a test environment before publishing to the production harness. There are no revision aliases or percentage-based traffic splits; publishing changes the revision used by new instances of that harness.

Sample output masks real values.

## 1. Set environment variables and create the harness

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

Create the harness with the saved model provider ID:

```bash
HARNESS_ID=$(python3 ../scripts/resources.py create revisions harness \
  --name "$HARNESS_NAME" \
  --engine pi \
  --engine-version 1.3.0 \
  --model "$MODEL_PROVIDER_ID:hy3" \
  --system-prompt 'When the entire user message is REVISION, reply exactly AGR_COOKBOOK_REV1. Do not use tools for this probe.' \
  --role-arn "$AGR_ROLE_ARN" \
  --subnet-id "$HARNESS_SUBNET_ID" \
  --security-group-id "$HARNESS_SECURITY_GROUP_ID" \
  --wait) && export HARNESS_ID
```

After revision 1 is published, read the saved Tool ID for the later instance checks:

```bash
HARNESS_TOOL_ID=$(python3 ../scripts/resources.py get revisions ToolId) && export HARNESS_TOOL_ID
echo "$HARNESS_TOOL_ID"
```

Probe v1 with the fixed request `REVISION`. The check requires a completed turn with the revision-specific marker and records the only running instance for the dedicated harness. Keep this shell open to reuse the function.

```bash
probe_revision() {
  local expected_marker=$1 reply instance_id
  reply=$(agr harness prompt "$HARNESS_ID" --region "$AGR_REGION" -o json \
    --jq '.Data | select(.StopReason == "end_turn") | .Reply' 'REVISION') || return 1
  if [ "$reply" != "$expected_marker" ]; then
    echo "Expected revision marker $expected_marker" >&2
    return 1
  fi
  instance_id=$(agr instance list --tool-id "$HARNESS_TOOL_ID" --region "$AGR_REGION" \
    --all -o json --jq '[.Data.Items[] | select(.Status == "RUNNING")] | if length == 1 then .[0].InstanceId else empty end') || return 1
  if [ -z "$instance_id" ]; then
    echo 'Expected exactly one RUNNING instance for this harness' >&2
    return 1
  fi
  printf '%s\n' "$instance_id"
}
V1_INSTANCE_ID=$(probe_revision AGR_COOKBOOK_REV1) && printf '%s\n' "$V1_INSTANCE_ID"
```

## 2. Edit the draft and compare

All MCP header values (including `${credential}` templates) are masked as `[REDACTED]` in `revision diff` (text and JSON) and `harness status -o json`. Changes are computed from the original values, so a header change can still be reported even when both displayed values are masked; `harness get` and `revision get` still return the stored values. See [MCP headers and credentials](../tool-market/README.md#4-add-an-mcp-server-that-needs-an-api-key) for storage and access permissions.

`harness update` changes only the draft; live instances are unaffected. The system prompt can be passed inline or read with `@file`:

```bash
cat > prompt.md <<'EOF'
When the entire user message is REVISION, reply exactly AGR_COOKBOOK_REV2. Do not use tools for this probe.
EOF

agr harness update "$HARNESS_ID" --region "$AGR_REGION" --system-prompt @prompt.md
```

Check the status. `status` reports how many fields differ between the draft and the live revision, and what to run next:

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

Show the exact difference:

```bash
agr harness revision diff "$HARNESS_ID" live draft --region "$AGR_REGION"
```

```text
live (revision 1) -> draft: 1 change(s)
~ SystemPrompt  "When the entire user message is REVISION, reply exactly AGR_COOKBOOK_REV1. ..." -> "When the entire user message is REVISION, reply exactly AGR_COOKBOOK_REV2. ..."
```

`~` marks a change, `+` an addition and `-` a removal. Each side of `revision diff` can be a revision number, `live` (the published revision), `latest` (the newest revision), or `draft`.

Tags are not runtime configuration and need no publish:

```bash
agr harness update "$HARNESS_ID" --region "$AGR_REGION" --tags env=demo --tags team=agents
```

## 3. Freeze and publish revision 2

`revision create` freezes the current draft into a new revision; `--publish --wait` publishes it immediately and waits for the outcome.

```bash
agr harness revision create "$HARNESS_ID" --region "$AGR_REGION" --publish --wait
```

Successful output:

```text
Harness:        hns-********
Revision:       2 (v2)
Status:         PUBLISHED
Engine:         pi@1.3.0
Models:         mp-********@1:hy3 (default)
System prompt:  When the entire user message is REVISION, reply exactly AGR_COOKBOOK_REV2. ...
Skills:         -
Plugins:        -
MCP servers:    -
Updated:        <masked-time>
Next: agr harness endpoint hns-******** --check   # new instances use this revision
```

`mp-********@1` means this revision is pinned to revision 1 of the model provider. List all revisions:

```bash
agr harness revision list "$HARNESS_ID" --region "$AGR_REGION"
```

```text
REVISION  NAME  STATUS      ENGINE    UPDATED          REASON
2         v2    PUBLISHED   pi@1.3.0  <masked-time>
1         v1    SUPERSEDED  pi@1.3.0  <masked-time>
```

A harness has at most one `PUBLISHED` revision at a time; the replaced revision becomes `SUPERSEDED`.

Publishing affects new instances. An old instance can still receive a new session, so stop the recorded v1 instance first. Send the same `REVISION` request and assert that v2 returns its own marker on a different running instance.

```bash
test -n "${V1_INSTANCE_ID:-}" &&
agr instance delete "$V1_INSTANCE_ID" --region "$AGR_REGION" --yes --wait --ignore-not-found &&
V2_INSTANCE_ID=$(probe_revision AGR_COOKBOOK_REV2) &&
test "$V2_INSTANCE_ID" != "$V1_INSTANCE_ID" &&
printf 'Verified AGR_COOKBOOK_REV2 on a new instance %s\n' "$V2_INSTANCE_ID"
```

## 4. Roll back to revision 1

There is no separate rollback command: republish the earlier revision.

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

Stop the recorded v2 instance and verify rollback with the same request. Expect the v1 marker on a running instance whose ID differs from both earlier instances.

```bash
test -n "${V2_INSTANCE_ID:-}" &&
agr instance delete "$V2_INSTANCE_ID" --region "$AGR_REGION" --yes --wait --ignore-not-found &&
ROLLBACK_INSTANCE_ID=$(probe_revision AGR_COOKBOOK_REV1) &&
test "$ROLLBACK_INSTANCE_ID" != "$V1_INSTANCE_ID" &&
test "$ROLLBACK_INSTANCE_ID" != "$V2_INSTANCE_ID" &&
printf 'Verified AGR_COOKBOOK_REV1 on a new instance %s\n' "$ROLLBACK_INSTANCE_ID"
```

Rolling back does not change the draft, so the draft still contains the new prompt and `Next` suggests publishing it. Skip that for now; step 5 publishes it together with a model change. Publishing a revision that is already `PUBLISHED` is safe: the CLI returns success without sending a request.

```bash
agr harness revision publish "$HARNESS_ID" 1 --region "$AGR_REGION"
```

```text
Revision 1 of hns-******** is already PUBLISHED; nothing to do.
```

With `-o json`, `Data.AlreadyPublished` is `true`.

## 5. Update the model provider

Add a model to the provider. Replace `SECOND_MODEL_ID` with another model ID your TokenHub API key can call. `--model` replaces the whole model list, so include the existing `hy3`:

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

Existing harness revisions stay pinned to provider revision 1. To use the new model, add it to the harness model selection, make it the default, and create a new revision. The new revision pins the latest provider revision:

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
~ SystemPrompt  "When the entire user message is REVISION, reply exactly AGR_COOKBOOK_REV1. ..." -> "When the entire user message is REVISION, reply exactly AGR_COOKBOOK_REV2. ..."
```

After publishing, compare revision 1 with the latest revision to see the provider revision move from 1 to 2:

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
~ SystemPrompt  "When the entire user message is REVISION, reply exactly AGR_COOKBOOK_REV1. ..." -> "When the entire user message is REVISION, reply exactly AGR_COOKBOOK_REV2. ..."
```

Only a comparison between two revisions shows provider revisions. A comparison with the draft ignores them, because the draft is not pinned to a provider revision yet.

## 6. A failed publish leaves the live revision untouched

Skills are downloaded and validated only at publish time. The following step deliberately references a Skill version that does not exist and observes the state after the publish fails:

```bash
agr harness update "$HARNESS_ID" --region "$AGR_REGION" \
  --skill MARKETPLACE/rec-doesnotexist/rv-doesnotexist

agr harness revision create "$HARNESS_ID" --region "$AGR_REGION" --publish --wait
```

The command fails with `WAIT_FAILED`. The error contains the new revision number and the reason:

```text
Error: revision 4 was created but publishing failed: harness revision hns-********/4 publish finished with status "PUBLISH_FAILED": Skill preparation failed: ...
Code: WAIT_FAILED
Hint: Read StatusReason with 'agr harness revision get hns-******** 4', fix the cause, then retry with 'agr harness revision publish hns-******** 4 --wait'.
Fix: agr harness revision publish hns-******** 4 --wait
```

The live revision is still revision 3 from the previous step, and existing instances are unaffected:

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

`Next` suggests retrying revision 4, which is right when the cause is external. Here the cause is the revision content itself, so a retry would fail again. Revision contents are immutable, so the fix is to edit the draft. Here, clear the Skill:

```bash
agr harness update "$HARNESS_ID" --region "$AGR_REGION" --skill ''
agr harness status "$HARNESS_ID" --region "$AGR_REGION"
```

The draft matches live revision 3 again:

```text
Harness:    hns-******** (harness-revisions-****)  ACTIVE
Live:       revision 3 (v3)  PUBLISHED  pi@1.3.0
Latest:     revision 4 (v4)  PUBLISH_FAILED  pi@1.3.0: Skill preparation failed: ...
Draft:      same as live revision
Resources:  tool=sdt-******** deployment=dpl-********
Next:       agr harness revision publish hns-******** 4 --wait
```

The live configuration is already correct, so ignore `Next`; once you create and publish another revision, revision 4 is no longer the latest. When the cause is external, such as the role lacking Registry read permission, fix it and retry the same revision.

To use a real Skill, list Skills in the tool market:

```bash
agr harness tool list --region "$AGR_REGION" --type skill
```

Copy the returned `REFERENCE` and pass it with `--skill MARKETPLACE/<record-id>/<version-id>`. Plugins use `--plugin`; unlike Skills, a Plugin is validated when the draft is saved, including whether the version is readable and compatible with the current engine.

## 7. Clean up

Delete the resources saved for this scenario. The helper reads the IDs, region and endpoint from `.state/`, waits for deletion, and verifies the result. You can run it again after an interrupted cleanup.

```bash
python3 ../scripts/resources.py cleanup revisions --yes
rm -f prompt.md
```

## Common issues

| Symptom | Cause and fix |
| --- | --- |
| `harness update` or `revision create` returns `ResourceInUse` | A revision of this harness is publishing. Wait with `agr harness status` until `PUBLISHING` ends |
| `--wait` returns `WAIT_PREEMPTED` | Another revision finished publishing first, and this one became `SUPERSEDED`. Check the live revision with `agr harness status` before republishing |
| `--wait` returns `WAIT_TIMEOUT` | The local wait timed out while the service is still publishing. Keep waiting as `Hint` suggests; do not create another revision |
| `model-provider update` fails to remove a model | A harness draft still selects that model. Remove it with `harness update --model` first |
| `model-provider delete` returns `ResourceInUse` | A harness or one of its kept revisions still references the provider. Delete the harness first |
| A newly published prompt has no effect | The request still lands on an instance created before the publish. Delete old instances as in step 3 and retry |
| A revision reaches `PUBLISH_FAILED` or its instances fail to start | Read `harness revision get` for the publish reason. Once a Tool exists, inspect its operational events as shown in [simple](../simple/README.md#common-issues) |
