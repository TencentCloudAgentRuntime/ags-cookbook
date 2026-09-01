# Run stateless DeepSeek Harness Brain with persistent Hands on AGS

English | [中文](./README_zh.md)

This example separates reasoning from command execution:

```text
client -> AGS Brain Deployment (2+ interchangeable replicas)
                     |  DSH session log, workspace binding, turn lease
                     v
                  MySQL 8
                     |
                     |  E2B 2.29.1 protocol, envd :49983, affinity header
                     v
          AGS Hands Deployment (EXCLUSIVE + PAUSE)
                     |
                     v
              retained /workspace
```

Brain contains DeepSeek Harness (DSH), the TokenHub model adapter, and the HTTP API. It keeps no authoritative session or workspace state on local disk. Hands contains only `envd` and ordinary command-line tools; it has no DSH, MySQL client, SQLite database, COS SDK, or COS mount. AGS retains the Hands `/workspace` across `PAUSE` and resume.

This is intentionally a single-user cookbook, not a public multi-tenant service. `BRAIN_WORKSPACE_USER_ID` is configured by the operator and cannot be overridden by an HTTP client. Put the Brain Deployment behind the AGS Deployment-token gateway; the Brain process itself does not implement end-user authentication.

## Durable contracts

| Concern | Contract |
| --- | --- |
| DSH session | MySQL is authoritative through `SessionPersistence`; Brain resumes and disposes the live Agent on every turn. |
| Workspace | MySQL maps a server-side identity to one opaque AGS affinity ID. The affinity is never returned by the Brain API. |
| Concurrent turns | One MySQL lease per session. A second request receives `409 SESSION_BUSY`; requests are not queued. |
| Stale replicas | Every DSH append locks and validates the current turn generation in the same MySQL transaction. Every new Hands operation validates the lease and a monotonic marker under `/workspace/.ags`. |
| Allocation uncertainty | A `PENDING` binding fails closed. Recovery is explicit; Brain never silently allocates a second workspace. |
| Hands storage | `/workspace` is retained by the AGS Hands Sandbox. No COS mount is required. |

## Prerequisites

- `agr` v0.6.6 or later, `pnpm` 11.19.0, and Podman or Docker.
- A CCR repository and a CAM role that lets AGS pull both images.
- A MySQL 8 database named `dsh-cookbook`. Every Brain replica must be able to reach it and use the same credentials.
- Tencent Cloud credentials that may call [`AcquireDeploymentToken`](https://cloud.tencent.com/document/api/1814/136842) for the Hands Deployment.
- A Tencent Cloud TokenHub API key for `deepseek-v4-flash`.

The reference configuration deliberately opens a normal non-TLS MySQL connection because that is the requested cookbook deployment. Restrict the database account to `dsh-cookbook` and to the minimum required network scope. TLS setup is outside this example.

## 1. Prepare and verify MySQL

Create the database once:

```sql
CREATE DATABASE `dsh-cookbook`
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
```

Copy the example environment file and fill in real values locally:

```bash
cp .env.example .env
pnpm install --frozen-lockfile
pnpm migrate
pnpm test:mysql
```

Brain also runs the checksum-verified migrations at startup under a MySQL advisory lock. A checksum mismatch or migration-lock timeout keeps `/readyz` unavailable.

## 2. Build and publish the two images

```bash
make build

export CCR_REGISTRY='ccr.ccs.tencentyun.com/replace-me'
export BRAIN_IMAGE="$CCR_REGISTRY/dsh-brain:0.1.0"
export HANDS_IMAGE="$CCR_REGISTRY/dsh-hands:0.1.0"

podman tag ags-cookbook/dsh-brain:local "$BRAIN_IMAGE"
podman tag ags-cookbook/dsh-hands:local "$HANDS_IMAGE"
podman push "$BRAIN_IMAGE"
podman push "$HANDS_IMAGE"
```

The source pins and reproducibility checks are documented in [dockerfiles](./dockerfiles/README.md). Personal CCR Tools require a `tag@sha256:digest` image reference; a digest-only reference is rejected.

## 3. Create the persistent Hands Deployment

Set names and the image-pull role:

```bash
export AGR_REGION=ap-shanghai
export AGR_ROLE_ARN='qcs::cam::uin/100000000001:roleName/replace-me'
export HANDS_TOOL_NAME='dsh-hands-your-name'
export HANDS_DEPLOYMENT_NAME='dsh-hands-your-name'
```

Create the Tool. Hands needs no database or object-storage environment variables.

```bash
agr tool create \
  --region "$AGR_REGION" \
  --tool-name "$HANDS_TOOL_NAME" \
  --tool-type custom \
  --persistent \
  --role-arn "$AGR_ROLE_ARN" \
  --network-configuration '{"NetworkMode":"PUBLIC"}' \
  --custom-configuration '{
    "Image": "replace-with-hands-image-tag@sha256:digest",
    "ImageRegistryType": "personal",
    "Command": ["/usr/bin/envd"],
    "Args": ["-port", "49983"],
    "Ports": [{"Name":"envd","Port":49983,"Protocol":"TCP"}],
    "Resources": {"CPU":"2000m","Memory":"4Gi"},
    "Probe": {
      "HttpGet": {"Path":"/health","Port":49983,"Scheme":"HTTP"},
      "ReadyTimeoutMs":30000,
      "ProbeTimeoutMs":3000,
      "ProbePeriodMs":5000,
      "SuccessThreshold":1,
      "FailureThreshold":6
    }
  }' \
  --wait
```

Copy the Tool ID and create an exclusive, pause-on-idle Deployment:

```bash
export HANDS_TOOL_ID='sdt-replace-me'

agr deployment create \
  --region "$AGR_REGION" \
  --deployment-name "$HANDS_DEPLOYMENT_NAME" \
  --tool-id "$HANDS_TOOL_ID" \
  --scaling-configuration '{
    "MinInstanceCount":0,
    "MaxInstanceCount":20,
    "MaxInstanceRequestConcurrency":200
  }' \
  --lifecycle-configuration '{
    "IdleTimeoutSeconds":300,
    "IdleAction":"PAUSE"
  }' \
  --affinity-configuration '{
    "Mode":"EXCLUSIVE",
    "HeaderName":"X-Tencent-Agr-Affinity-Id"
  }'

export HANDS_DEPLOYMENT_ID='dpl-replace-me'
```

`MaxInstanceCount` is also the maximum number of simultaneously active exclusive workspaces. Size it for the expected number of active users or sessions. `MaxInstanceRequestConcurrency` is HTTP/RPC request capacity inside that one exclusive workspace; E2B uses multiple Files and Commands requests, so it must not be reduced to one. MySQL's turn lease, not this request-capacity field, enforces one writer.

## 4. Create the stateless Brain Deployment

Brain needs the variables listed in `.env.example`. The essential platform condition is simple: every Brain replica must reach the same MySQL endpoint. Inject secrets through your deployment secret workflow; do not commit `.env` or paste real credentials into this repository.

The following command shows the complete Tool shape. Every `replace-me` value is a placeholder; use your platform secret-injection workflow for real passwords and keys instead of leaving them in shell history.

```bash
export BRAIN_TOOL_NAME='dsh-brain-your-name'

agr tool create \
  --region "$AGR_REGION" \
  --tool-name "$BRAIN_TOOL_NAME" \
  --tool-type custom \
  --persistent \
  --role-arn "$AGR_ROLE_ARN" \
  --network-configuration '{"NetworkMode":"PUBLIC"}' \
  --custom-configuration '{
    "Image":"replace-with-brain-image-tag@sha256:digest",
    "ImageRegistryType":"personal",
    "Command":["node","/app/dist/brain/server.js"],
    "Env":[
      {"Name":"MYSQL_HOST","Value":"replace-me"},
      {"Name":"MYSQL_PORT","Value":"3306"},
      {"Name":"MYSQL_USER","Value":"replace-me"},
      {"Name":"MYSQL_PASSWORD","Value":"replace-me"},
      {"Name":"MYSQL_DATABASE","Value":"dsh-cookbook"},
      {"Name":"BRAIN_WORKSPACE_USER_ID","Value":"replace-me"},
      {"Name":"AGS_REGION","Value":"ap-shanghai"},
      {"Name":"HANDS_DEPLOYMENT_ID","Value":"dpl-replace-me"},
      {"Name":"TENCENTCLOUD_SECRET_ID","Value":"replace-me"},
      {"Name":"TENCENTCLOUD_SECRET_KEY","Value":"replace-me"},
      {"Name":"TOKENHUB_API_KEY","Value":"replace-me"}
    ],
    "Ports":[{"Name":"http","Port":8080,"Protocol":"TCP"}],
    "Resources":{"CPU":"2000m","Memory":"4Gi"},
    "Probe":{
      "HttpGet":{"Path":"/readyz","Port":8080,"Scheme":"HTTP"},
      "ReadyTimeoutMs":30000,
      "ProbeTimeoutMs":3000,
      "ProbePeriodMs":5000,
      "SuccessThreshold":1,
      "FailureThreshold":12
    }
  }' \
  --wait
```

AGS requires a Tool to be marked `persistent` before it can back a Deployment. That capability flag does not make Brain stateful: the Brain Tool has no storage mount, the Deployment uses `STOP`, and the process keeps all authoritative state in MySQL. The Brain process runs as the unprivileged `node` user.

Then create a non-affine, multi-replica Deployment:

```bash
export BRAIN_TOOL_ID='sdt-replace-me'
export BRAIN_DEPLOYMENT_NAME='dsh-brain-your-name'

agr deployment create \
  --region "$AGR_REGION" \
  --deployment-name "$BRAIN_DEPLOYMENT_NAME" \
  --tool-id "$BRAIN_TOOL_ID" \
  --scaling-configuration '{
    "MinInstanceCount":2,
    "MaxInstanceCount":4,
    "MaxInstanceRequestConcurrency":20
  }' \
  --lifecycle-configuration '{
    "IdleTimeoutSeconds":300,
    "IdleAction":"STOP"
  }'

export BRAIN_DEPLOYMENT_ID='dpl-replace-me'
```

Do not configure Brain session affinity. Any replica can accept any request because MySQL owns the session log, binding, migration journal, and turn lease.

## 5. Exercise the API

For local debugging, proxy the Brain Deployment:

```bash
agr deployment proxy "$BRAIN_DEPLOYMENT_ID" 18080:8080 --region "$AGR_REGION"
```

Create a session. `user` mode shares one Hands workspace across this cookbook user's sessions; `session` mode allocates one Hands workspace per DSH session.

```bash
curl --fail-with-body --silent --show-error \
  --request POST \
  --header 'content-type: application/json' \
  --data '{"workspaceMode":"user"}' \
  http://127.0.0.1:18080/v1/sessions
```

Copy the returned `sessionId`, then send a turn:

```bash
export DSH_SESSION_ID='replace-with-session-id'

curl --fail-with-body --silent --show-error \
  --request POST \
  --header 'content-type: application/json' \
  --data '{"message":"Create /workspace/hello.txt containing hello from Hands, then read it back."}' \
  "http://127.0.0.1:18080/v1/sessions/$DSH_SESSION_ID/turns"
```

The response contains the final DSH assistant content. It never contains the Hands affinity ID or a Deployment token.

If session creation returns `WORKSPACE_RECOVERY_REQUIRED`, no second workspace is allocated automatically. Use the returned session ID only after deciding that retry is safe:

```bash
curl --fail-with-body --silent --show-error \
  --request POST \
  "http://127.0.0.1:18080/v1/sessions/$DSH_SESSION_ID/recover"
```

## Failure semantics

| API result | Meaning | Operator/client action |
| --- | --- | --- |
| `409 SESSION_BUSY` | Another Brain owns an unexpired turn lease. | Do not retry in parallel; wait for that request or the lease expiry. |
| `409 WORKSPACE_RECOVERY_REQUIRED` | A previous workspace allocation is `PENDING` or `FAILED`. | Investigate, then invoke explicit recovery. |
| `503 WORKSPACE_RECOVERY_REQUIRED` | Allocation or atomic publication did not complete. | Treat the outcome as uncertain; invoke explicit recovery only after review. |
| `500 INTERNAL` | Brain did not complete the turn boundary. | The claim expires; the next DSH resume records the interrupted tail instead of replaying tool calls. |

An already-running Hands command cannot be undone when a lease expires. Fencing prevents the stale Brain from starting a later operation or committing a later DSH event.

## Cleanup

Delete Brain first so no new Hands sessions are created, then delete Hands:

```bash
agr deployment delete "$BRAIN_DEPLOYMENT_ID" --region "$AGR_REGION" --wait
agr tool delete "$BRAIN_TOOL_ID" --region "$AGR_REGION" --yes --wait
agr deployment delete "$HANDS_DEPLOYMENT_ID" --region "$AGR_REGION" --wait
agr tool delete "$HANDS_TOOL_ID" --region "$AGR_REGION" --yes --wait
```

Delete `dsh-cookbook` only when no other Brain Deployment uses it.

## Scope limits

This example does not provide public-user authentication, tenant isolation, a browser UI, cross-region disaster recovery, backup automation, or an SLO. It is a deployment cookbook for the Brain/Hands state boundary, not a general Agent platform.
