# Run all-in-one DeepSeek Harness on AGR

This guide runs the DeepSeek Harness Web UI, Agent Host, and command-execution environment in one Sandbox Instance and exposes it through one Deployment. You will:

1. Create a Sandbox Tool from a pinned image.
2. Create a scale-to-zero Deployment that pauses when idle and uses exclusive session affinity.
3. Open the Web UI through `agr deployment proxy`.
4. Connect Tencent Cloud TokenHub in the Web UI and complete a real coding task with a Standard Agent.
5. Let the instance reach `PAUSED`, then resume the same workspace and session with its affinity ID.

The response examples follow actual command output structures with account details, resource IDs, timestamps, and request IDs masked. Do not reuse placeholder values from those responses.

## Prerequisites

- Install `agr`; the current account must be able to create and delete Sandbox Tools, Deployments, and Instances.
- Prepare a CAM role ARN that lets AGR pull the CCR image.
- Keep local port `18080` available.
- Activate Tencent Cloud TokenHub and prepare an API key. See the [official TokenHub API guide](https://cloud.tencent.com/document/product/1823/130078).
- Ensure that `ccr.ccs.tencentyun.com/ags.dev/deepseek-harness:v0.1.1-rc.2-ags.3` is reachable.

The TokenHub API key is never placed in the image, Tool, Deployment, or command line. Enter it manually in the DeepSeek Harness Web UI.

## 1. Set local environment variables

Replace the role ARN and both names. Use a suffix that keeps the names unique.

```bash
export AGR_REGION=ap-shanghai
export AGR_ROLE_ARN='qcs::cam::uin/100000000001:roleName/replace-me'
export DSH_TOOL_NAME='deepseek-harness-all-in-one-your-name'
export DSH_DEPLOYMENT_NAME='deepseek-harness-all-in-one-your-name'

agr status
```

Expect the following shape. `agr status` reports the local default region; every later command explicitly selects `ap-shanghai` through `--region "$AGR_REGION"`.

```text
Region:       <local-default-region>
Domain:       tencentags.com
Output:       text
Config file:  <masked>/.agr/config.toml
Config load:  true

Auth:
  Secret ID:  configured (source: <masked>)
  Secret Key: configured (source: <masked>)
  Token:      not configured
```

## 2. Create the DeepSeek Harness Tool

The Tool uses the pinned image, `2 vCPU / 4 GiB`, and HTTP port `3080`. Its launch arguments bind the container to `0.0.0.0` and trust both the external Deployment hostnames in `ap-shanghai` and the internal instance hostnames used when the gateway forwards requests to the container. See [dockerfiles](./dockerfiles/README.md) for the official-source build.

```bash
agr tool create \
  --region "$AGR_REGION" \
  --tool-name "$DSH_TOOL_NAME" \
  --tool-type custom \
  --persistent \
  --role-arn "$AGR_ROLE_ARN" \
  --network-configuration '{"NetworkMode":"PUBLIC"}' \
  --custom-configuration '{"Image":"ccr.ccs.tencentyun.com/ags.dev/deepseek-harness:v0.1.1-rc.2-ags.3","ImageRegistryType":"personal","Command":["node","--expose-internals","/usr/local/lib/node_modules/@deepseek-ai/dsh/lib/bin.js"],"Args":["web","--host","0.0.0.0","--port","3080","--trusted-host","*.ap-shanghai.agents.tencentags.com","--trusted-host","*.ap-shanghai.internal.tencentags.com","--no-open"],"Ports":[{"Name":"web","Port":3080,"Protocol":"TCP"}],"Resources":{"CPU":"2000m","Memory":"4Gi"},"Probe":{"HttpGet":{"Path":"/","Port":3080,"Scheme":"HTTP"},"ReadyTimeoutMs":30000,"ProbeTimeoutMs":3000,"ProbePeriodMs":5000,"SuccessThreshold":1,"FailureThreshold":6}}' \
  --wait
```

`--wait` waits for a final Tool state. Successful output includes the real Tool ID:

```text
ID:          sdt-********
Name:        deepseek-harness-all-in-one-****
Type:        custom
Status:      ACTIVE
NetworkMode:  PUBLIC
Description:
Tags:        qcs:tag:createdBy=<masked-creator>
Created:     <masked-time>
RoleArn:     qcs::cam::uin/************:roleName/****
```

Copy the real Tool ID from the `ID` line, then set it before the next command:

```bash
export DSH_TOOL_ID='sdt-replace-me'
```

## 3. Create an exclusive-session Deployment

The configuration has three important effects:

- `MinInstanceCount=0` permits scale-to-zero when no session is active.
- `IdleTimeoutSeconds=60` with `PAUSE` pauses the instance 60 seconds after its last Deployment connection closes while preserving workspace state.
- `EXCLUSIVE` dedicates one non-migrating instance to each affinity ID. `MaxInstanceCount=3` therefore also limits simultaneous exclusive sessions to three.

```bash
agr deployment create \
  --region "$AGR_REGION" \
  --deployment-name "$DSH_DEPLOYMENT_NAME" \
  --tool-id "$DSH_TOOL_ID" \
  --scaling-configuration '{"MinInstanceCount":0,"MaxInstanceCount":3,"MaxInstanceRequestConcurrency":200}' \
  --lifecycle-configuration '{"IdleTimeoutSeconds":60,"IdleAction":"PAUSE"}' \
  --affinity-configuration '{"Mode":"EXCLUSIVE","HeaderName":"X-Tencent-Agr-Affinity-Id"}'
```

Successful output includes the real Deployment ID and resolved configuration:

```text
Name:          deepseek-harness-all-in-one-****
ID:            dpl-********
Tool:          sdt-********
Status:        ACTIVE
Tags:          <none>
Created:       <masked-timestamp>
Updated:       <masked-timestamp>
Scaling:
  Min Instances:                0
  Max Instances:                3
  Max Requests per Instance:    200
Lifecycle:
  Idle Action:                  PAUSE
  Idle Timeout:                 1m
Affinity:
  Mode:                         EXCLUSIVE
  Header:                       X-Tencent-Agr-Affinity-Id
```

Copy the real Deployment ID from the `ID` line, set it, and inspect the Deployment once:

```bash
export DSH_DEPLOYMENT_ID='dpl-replace-me'

agr deployment get "$DSH_DEPLOYMENT_ID" --region "$AGR_REGION"
```

## 4. Open the Web UI through a local proxy

The following command occupies the terminal while running. It listens on `127.0.0.1:18080`, acquires short-lived Deployment tokens automatically, and prints the service-provided affinity ID after the first request.

```bash
agr deployment proxy "$DSH_DEPLOYMENT_ID" 18080:3080 --region "$AGR_REGION"
```

Expect output in this form:

```text
<masked-timestamp> Proxy listening on 127.0.0.1:18080 (forwarding to https://3080-dpl-********.ap-shanghai.agents.tencentags.com)
Deployment proxy is recommended only for local debugging.
Forwarding from 127.0.0.1:18080 -> 3080
  Local:  http://127.0.0.1:18080
  Remote: https://3080-dpl-********.ap-shanghai.agents.tencentags.com

Press Ctrl+C to stop.
Affinity ID: <masked-affinity-id>
```

The proxy is for local debugging only. Production clients should acquire a short-lived token through `AcquireDeploymentToken` and call the Deployment data-plane domain directly. An HTTP port uses `https://{port}-{deployment-id}.{region}.agents.{data-plane-domain}`; the default data-plane domain is `tencentags.com`, so this example uses `https://3080-{deployment-id}.ap-shanghai.agents.tencentags.com`.

Keep the proxy running and open <http://127.0.0.1:18080>. A new instance may add cold-start latency before the first page appears. If the first request exceeds the proxy response timeout and shows `Bad Gateway`, refresh after the Instance has started.

As soon as the proxy prints the affinity ID, copy it and set it in another terminal for the resume step:

```bash
export DSH_AFFINITY_ID='replace-with-proxy-output'
```

## 5. Connect TokenHub in the Web UI

If the first-run dialog asks for an official DeepSeek API key, choose “Configure later.” Open “Settings → Models” and add a custom provider:

| Field | Value |
| --- | --- |
| Provider ID | `tokenhub` |
| Display name | `Tencent Cloud TokenHub` |
| Base URL | `https://tokenhub.tencentmaas.com/v1` |
| API protocol | `openai-completions` |
| API Key | Enter the TokenHub API key manually in the page |
| Model ID | `deepseek-v4-flash` |

After creating the provider, create an Agent with the `Standard` preset and select `tokenhub/deepseek-v4-flash`. Do not install an extra plugin or modify the shipped DeepSeek Harness preset.

## 6. Complete a real task

Send the following task to the Agent:

```text
Create a zero-dependency Node.js CLI in /workspace/todo-cli:

- node cli.mjs add <text>: add an item;
- node cli.mjs list: list every item;
- node cli.mjs done <id>: mark one item complete;
- persist data in /workspace/todo-cli/todos.json;
- write tests with node:test;
- add a short README with command examples.

When finished, run node --test and show real add, list, and done results.
```

Verify at least that:

- `/workspace/todo-cli` contains the implementation, tests, and README;
- `node --test` passes;
- the three commands behave as documented;
- no third-party npm dependency was added.

## 7. Observe idle pause

Return to the proxy terminal and press `Ctrl+C`. Do not access the local page again. Wait manually for at least 60 seconds; the state transition is asynchronous and may take slightly longer.

In another terminal, list Instances for the Tool:

```bash
agr instance list --tool-id "$DSH_TOOL_ID" --region "$AGR_REGION"
```

The same Instance should reach `PAUSED`:

```text
ID                    TOOL                                STATUS  TIMEOUT  EXPIRES  MOUNTS  CREATED
<masked-instance-id>  deepseek-harness-all-in-one-****    PAUSED  0s       -        -       <masked-time>
```

If it is still `RUNNING`, keep all connections closed and run the same query later. The guide deliberately uses no polling script.

## 8. Resume the same exclusive session

Ensure that this terminal has the real affinity ID, then resume it explicitly:

```bash
export DSH_AFFINITY_ID='replace-with-proxy-output'

agr deployment proxy "$DSH_DEPLOYMENT_ID" 18080:3080 \
  --region "$AGR_REGION" \
  --affinity-id "$DSH_AFFINITY_ID"
```

The proxy resumes the paused Instance owned by that affinity ID instead of migrating the session. Reopen <http://127.0.0.1:18080> and confirm that both the earlier Agent session and `/workspace/todo-cli` remain available.

Send one incremental task:

```text
Continue in the existing /workspace/todo-cli project. Add a clear-completed command that removes every completed item, update the tests and README, and run node --test again. Do not rewrite the existing implementation.
```

After `clear-completed` passes, the example has demonstrated exclusive affinity routing, `PAUSE` recovery, and workspace continuity together.

## 9. Clean up

After acceptance, press `Ctrl+C` to stop the proxy and delete the Deployment:

```bash
agr deployment delete "$DSH_DEPLOYMENT_ID" --region "$AGR_REGION"
agr instance list --tool-id "$DSH_TOOL_ID" --region "$AGR_REGION"
```

If any Instance is not `STOPPED`, copy each ID, set it first, and delete it:

```bash
export DSH_INSTANCE_ID='replace-with-instance-id'
agr instance delete "$DSH_INSTANCE_ID" --region "$AGR_REGION" --yes --wait
```

Finally, delete the Tool:

```bash
agr tool delete "$DSH_TOOL_ID" --region "$AGR_REGION" --yes --wait
```
