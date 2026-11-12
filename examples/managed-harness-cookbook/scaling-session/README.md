# Scaling, idle policy, and session persistence for a managed harness

This tutorial creates its own harness. At create time it sets the instance size, on-demand start, and idle pause through the initialization configuration; it then enables a session space and continues the same session on a new instance after the old one is deleted; finally it adjusts scaling directly with Deployment commands.

Complete the shared [Managed Harness Cookbook prerequisites](../README.md#prerequisites) before starting. Scaling and idle parameters mean exactly the same as for Deployments; see [Deployment scaling](../../deployment-cookbook/httpbin/scaling/README.md) and [Deployment lifecycle](../../deployment-cookbook/httpbin/lifecycle/README.md) for details.

## Who owns which settings

| Setting | Where it is set | How to change it later |
| --- | --- | --- |
| Engine, models, prompt, Skills, Plugins, MCP, session space | Harness draft | `harness update`, then create and publish a revision |
| Role, VPC network | Initialization configuration of `harness create` | Cannot be changed through the harness |
| Instance resources, storage mounts, logs | Initialization configuration of `harness create` | Change the underlying Tool with `agr tool update` |
| Scaling, idle policy, session affinity | Initialization configuration of `harness create` | Change the underlying Deployment with `agr deployment update` |

The initialization configuration is used only when the first publish creates the Tool and the Deployment. Later publishes update only the harness-managed image, startup arguments, and managed environment variables; they do not overwrite network, mount, scaling, or other changes you make through Tool or Deployment commands.

Defaults when the initialization configuration omits a value:

| Field | Default |
| --- | --- |
| `SandboxTool.CustomConfiguration.Resources` | `CPU: "2"`, `Memory: "2Gi"` |
| `Deployment.ScalingConfiguration` | `MinInstanceCount: 1`, `MaxInstanceCount: 1`, `MaxInstanceRequestConcurrency: 200` |
| `Deployment.LifecycleConfiguration` | `IdleTimeoutSeconds: 300`, `IdleAction: STOP` |
| `Deployment.AffinityConfiguration` | `Mode: BEST_EFFORT`, `HeaderName: X-Tencent-Agr-Affinity-Id` |

Sample output masks real values.

## 1. Set environment variables and create a session space

```bash
export AGR_REGION=ap-chongqing
export AGR_ROLE_ARN='qcs::cam::uin/100000000001:roleName/replace-me'
export HARNESS_SUBNET_ID='subnet-replace-me'
export HARNESS_SECURITY_GROUP_ID='sg-replace-me'
export TOKENHUB_API_KEY_ID='ak-replace-me'
export MODEL_PROVIDER_NAME='harness-scaling-your-name'
export HARNESS_NAME='harness-scaling-your-name'
export SESSION_SPACE_NAME='harness-scaling-your-name'

agr status
```

A session space stores conversation history in the cloud. The harness reaches it with the initialization role, so make sure that role can read and write the chosen session space.

```bash
agr session space create \
  --region "$AGR_REGION" \
  --name "$SESSION_SPACE_NAME" \
  -o json --jq '.Data.SessionSpace.SpaceId'
```

Copy the SpaceId:

```bash
export SESSION_SPACE_ID='space-replace-me'
```

## 2. Register the model and create the harness

```bash
agr model-provider create \
  --region "$AGR_REGION" \
  --name "$MODEL_PROVIDER_NAME" \
  --tokenhub-api-key-id "$TOKENHUB_API_KEY_ID" \
  --model hy3
```

```bash
export MODEL_PROVIDER_ID='mp-replace-me'
```

Write the initialization configuration to a file. The role and VPC still come from `--role-arn`, `--subnet-id`, and `--security-group-id`; the CLI merges them into this object. The following sets instances to 1 CPU and 2Gi, allows scaling to zero with at most two instances, and pauses an instance after 60 idle seconds:

```bash
cat > init.json <<'EOF'
{
  "SandboxTool": {
    "CustomConfiguration": {
      "Resources": {"CPU": "1", "Memory": "2Gi"}
    }
  },
  "Deployment": {
    "ScalingConfiguration": {
      "MinInstanceCount": 0,
      "MaxInstanceCount": 2,
      "MaxInstanceRequestConcurrency": 50
    },
    "LifecycleConfiguration": {
      "IdleTimeoutSeconds": 60,
      "IdleAction": "PAUSE"
    }
  }
}
EOF
```

The omitted `AffinityConfiguration` uses the default. Create the harness with the session space enabled:

```bash
agr harness create \
  --region "$AGR_REGION" \
  --name "$HARNESS_NAME" \
  --engine pi \
  --engine-version 1.3.0 \
  --model "$MODEL_PROVIDER_ID:hy3" \
  --session-space-id "$SESSION_SPACE_ID" \
  --role-arn "$AGR_ROLE_ARN" \
  --subnet-id "$HARNESS_SUBNET_ID" \
  --security-group-id "$HARNESS_SECURITY_GROUP_ID" \
  --initialize-configuration @init.json \
  --wait
```

The successful output includes an extra `Session space` line. As in the simple tutorial, the upper part is the record from create time, so the Tool and Deployment are still `-`:

```text
Harness:        hns-********
Name:           harness-scaling-****
Status:         ACTIVE
Engine:         pi@1.3.0
Models:         mp-********:hy3 (default)
System prompt:  -
Skills:         -
Plugins:        -
MCP servers:    -
Session space:  space-********
Sandbox tool:   -
Deployment:     -
Tags:           -
Updated:        <masked-time>

Revision 1 is PUBLISHED.
Next: agr harness endpoint hns-******** --check
```

Copy the harness ID and read the underlying Tool and Deployment:

```bash
export HARNESS_ID='hns-replace-me'

agr harness get "$HARNESS_ID" --region "$AGR_REGION" -o json \
  --jq '.Data.Harness.ResourceInfo'
```

```json
{"DeploymentId":"dpl-********","ToolId":"sdt-********"}
```

```bash
export HARNESS_TOOL_ID='sdt-replace-me'
export HARNESS_DEPLOYMENT_ID='dpl-replace-me'
```

## 3. Confirm the initialization configuration

The underlying Deployment is an ordinary AGS Deployment and can be queried directly:

```bash
agr deployment get "$HARNESS_DEPLOYMENT_ID" --region "$AGR_REGION"
```

```text
Name:          hns-********-********
ID:            dpl-********
Tool:          sdt-********
Status:        ACTIVE
Tags:          <none>
Created:       <masked-time>
Scaling:
  Min Instances:                0
  Max Instances:                2
  Max Requests per Instance:    50
Lifecycle:
  Idle Action:                  PAUSE
  Idle Timeout:                 1m
Affinity:
  Mode:                         BEST_EFFORT
  Header:                       X-Tencent-Agr-Affinity-Id
```

`MinInstanceCount` is `0`, so there may be no instance yet:

```bash
agr instance list --tool-id "$HARNESS_TOOL_ID" --region "$AGR_REGION"
```

## 4. On-demand start and idle pause

The first request starts an instance and may be slower than later ones. Record the `SessionId` and `AffinityId` of this session for the next steps:

```bash
agr harness prompt "$HARNESS_ID" --region "$AGR_REGION" -o json \
  --jq '.Data | {AffinityId, Reply, SessionId}' \
  'Remember the code word "maple". Reply only with "OK".'
```

```json
{"AffinityId":"<masked-affinity-id>","Reply":"OK","SessionId":"<masked-session-id>"}
```

```bash
export HARNESS_SESSION_ID='replace-with-session-id'
export HARNESS_AFFINITY_ID='replace-with-affinity-id'

agr instance list --tool-id "$HARNESS_TOOL_ID" --region "$AGR_REGION"
```

One `RUNNING` instance appears. Stop sending requests for at least 60 seconds and query again; the instance moves to `PAUSED`. Reclamation is asynchronous and may take slightly longer than the configured timeout:

```text
ID                    TOOL                   STATUS  TIMEOUT  EXPIRES  MOUNTS  CREATED
<masked-instance-id>  hns-********-********  PAUSED  0s       -        -       <masked-time>
```

Continue with the same affinity value, and the Deployment resumes this instance. Pausing keeps memory and disk, so the instance remembers the conversation even without a session space:

```bash
agr harness prompt "$HARNESS_ID" --region "$AGR_REGION" \
  --session-id "$HARNESS_SESSION_ID" \
  --affinity-id "$HARNESS_AFFINITY_ID" \
  'What was the code word?'
```

The reply should contain `maple`.

## 5. Continue the session on a new instance

Deleting an instance discards its local session files. With a session space, pi syncs session entries to the cloud, and a new instance restores them through `session/load`.

Find and delete the current instance:

```bash
agr instance list --tool-id "$HARNESS_TOOL_ID" --region "$AGR_REGION"
export HARNESS_INSTANCE_ID='replace-with-instance-id'
agr instance delete "$HARNESS_INSTANCE_ID" --region "$AGR_REGION" --yes --wait
```

The old affinity value points at the deleted instance, so this time pass only `--session-id` and **not** `--affinity-id`. The Deployment starts a new instance, which loads the same session from the session space:

```bash
agr harness prompt "$HARNESS_ID" --region "$AGR_REGION" \
  --session-id "$HARNESS_SESSION_ID" \
  'What was the code word?'
```

The reply should still contain `maple`. The session history is visible in the session space. A managed harness always uses its harness ID as the session UserId:

```bash
agr session list --region "$AGR_REGION" --space-id "$SESSION_SPACE_ID" --user-ids "$HARNESS_ID"
```

Things to know about session spaces:

- All sessions of one harness share one UserId and are not separated by the chat users of your application. If you need per-user isolation, map users to SessionIds in your application.
- A session supports only one writing process at a time. Do not send turns to the same SessionId from two instances at once.
- Only the conversation history is restored; workspace files inside the instance are not migrated. Restore with the same `--cwd` used to create the session (default `/workspace`).
- Only the `pi` and `dsh` engines are supported. Remove the session space with `agr harness update <harness-id> --session-space-id ''`, then publish a new revision.

See the [Session Cookbook](../../session-cookbook/README.md) for implementation details.

## 6. Adjust the underlying Deployment directly

The initialization configuration cannot be changed through the harness, but you can adjust the underlying Deployment directly. The following sets the minimum instance count to 1 to keep one warm instance and remove cold-start latency. `--scaling-configuration` replaces the whole scaling object, so provide all three fields:

```bash
agr deployment update "$HARNESS_DEPLOYMENT_ID" \
  --region "$AGR_REGION" \
  --scaling-configuration '{
    "MinInstanceCount": 1,
    "MaxInstanceCount": 2,
    "MaxInstanceRequestConcurrency": 50
  }'

agr deployment get "$HARNESS_DEPLOYMENT_ID" --region "$AGR_REGION"
```

```text
Scaling:
  Min Instances:                1
  Max Instances:                2
  Max Requests per Instance:    50
```

Publishing a new harness revision later does not overwrite this change. Verify it yourself:

```bash
agr harness update "$HARNESS_ID" --region "$AGR_REGION" --system-prompt 'You are a helpful assistant.'
agr harness revision create "$HARNESS_ID" --region "$AGR_REGION" --publish --wait
agr deployment get "$HARNESS_DEPLOYMENT_ID" --region "$AGR_REGION"
```

`Min Instances` is still `1`.

Do not use `agr tool update` to change the harness-managed image, startup arguments, or platform-reserved environment variables; the next publish restores them from the revision. Environment variables you add yourself are kept.

## 7. Clean up

```bash
agr harness delete "$HARNESS_ID" --region "$AGR_REGION" --yes --wait
agr instance list --tool-id "$HARNESS_TOOL_ID" --region "$AGR_REGION"
```

Copy each instance ID currently in `RUNNING` or `PAUSED`, and delete them one by one:

```bash
export HARNESS_INSTANCE_ID='replace-with-instance-id'
agr instance delete "$HARNESS_INSTANCE_ID" --region "$AGR_REGION" --yes --wait
```

Delete the Tool and the model provider. Sessions in the session space are not deleted with the harness; delete the sessions first, then the space:

```bash
agr tool delete "$HARNESS_TOOL_ID" --region "$AGR_REGION" --yes --wait
agr model-provider delete "$MODEL_PROVIDER_ID" --region "$AGR_REGION" --yes

agr session list --region "$AGR_REGION" --space-id "$SESSION_SPACE_ID" --user-ids "$HARNESS_ID"
```

This tutorial creates one session. If the list shows others, set `HARNESS_SESSION_ID` to each of their IDs and run the delete command again. A space can be deleted only after it has no sessions. Finally, delete the space and the local file:

```bash
agr session delete --region "$AGR_REGION" --space-id "$SESSION_SPACE_ID" \
  --user-id "$HARNESS_ID" --session-id "$HARNESS_SESSION_ID"
agr session space delete --region "$AGR_REGION" --space-id "$SESSION_SPACE_ID"
rm -f init.json
```

## Common issues

| Symptom | Cause and fix |
| --- | --- |
| Create fails with `ROLE_ARN_CONFLICT` or `NETWORK_CONFLICT` | The role or network in `init.json` differs from the command-line flags. Set it in one place only |
| Create fails with `INVALID_NETWORK_MODE` | Managed harnesses support VPC only. Remove `NetworkMode` from `init.json` or set it to `VPC` |
| The first prompt is slow or returns `ACP_UNAVAILABLE` | `MinInstanceCount` is `0`, so an instance must start first. Retry shortly, or keep one warm instance as in step 6 |
| A new instance forgets the conversation after the old one is deleted | The initialization role lacks session space permission, or `--cwd` differs from the one used to create the session. Check with `agr session list` that the session was written to the cloud |
| `session space delete` fails | The space still has sessions. Delete all sessions first |
