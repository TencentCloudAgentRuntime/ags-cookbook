# AGR Custom Image Services

Use this for high-frequency service runtime tasks: custom images, long-running HTTP services, explicit ports, probes, resources, env vars, private registries, or per-instance overrides.

Prefer a full request JSON because probes, ports, resources, env, RoleArn, storage mounts, and log configuration are nested:

```bash
agr tool create --generate-skeleton > tool.json
agr tool create --request @tool.json -o json
```

### Minimal HTTP Service Tool

Create `custom-service-tool.json`:

```json
{
  "ToolName": "custom-svc-REPLACE",
  "ToolType": "custom",
  "Description": "Custom HTTP service runtime",
  "DefaultTimeout": "1h",
  "NetworkConfiguration": {
    "NetworkMode": "PUBLIC"
  },
  "CustomConfiguration": {
    "Image": "ccr.ccs.tencentyun.com/team/app:latest",
    "ImageRegistryType": "enterprise",
    "Command": ["/bin/sh"],
    "Args": ["-c", "python -m uvicorn app:app --host 0.0.0.0 --port 8080"],
    "Env": [
      {
        "Name": "APP_ENV",
        "Value": "prod"
      }
    ],
    "Ports": [
      {
        "Name": "http",
        "Port": 8080,
        "Protocol": "TCP"
      }
    ],
    "Probe": {
      "HttpGet": {
        "Path": "/health",
        "Port": 8080,
        "Scheme": "HTTP"
      },
      "ReadyTimeoutMs": 30000,
      "ProbePeriodMs": 5000,
      "ProbeTimeoutMs": 3000,
      "SuccessThreshold": 1,
      "FailureThreshold": 5
    },
    "Resources": {
      "CPU": "2",
      "Memory": "4Gi"
    }
  },
  "Tags": [
    {
      "Key": "kind",
      "Value": "custom-service"
    }
  ]
}
```

Create and verify:

```bash
tool_id=$(agr tool create \
  --request @custom-service-tool.json \
  -o json --jq '.Data.ToolId')

agr tool get "$tool_id" -o json

instance_id=$(agr instance create \
  --tool-id "$tool_id" \
  --timeout 30m \
  --auth-mode TOKEN \
  -o json --jq '.Data.InstanceId')

agr instance get "$instance_id" -o json
agr instance exec "$instance_id" -o json -- sh -lc "curl -fsS http://127.0.0.1:8080/health"
```

If the user wants to inspect the service from the local machine, run an interactive proxy only when requested:

```bash
agr instance proxy "$instance_id" 3000:8080 --address 127.0.0.1
```

### Private Registry Or Storage Access

Add `RoleArn` when the image registry or mounts require cloud access:

```json
{
  "RoleArn": "qcs::cam::uin/100000000:roleName/ags-runtime-role"
}
```

For COS/CFS/Image mounts, combine this custom Tool JSON with `StorageMounts`; see [mount-templates.md](mount-templates.md). Use mount paths that do not collide with the application path.

### Fork A Custom Tool With Overrides

Use this when the user has an existing custom Tool but wants a new image tag, new env vars, changed resources, or changed ports:

```bash
agr tool get "$source_tool_id" -o json
```

Create `custom-override.json` with only the custom fields to override:

```json
{
  "Image": "ccr.ccs.tencentyun.com/team/app:v2",
  "ImageRegistryType": "enterprise",
  "Env": [
    {
      "Name": "APP_ENV",
      "Value": "staging"
    }
  ],
  "Ports": [
    {
      "Name": "http",
      "Port": 8080,
      "Protocol": "TCP"
    }
  ],
  "Resources": {
    "CPU": "4",
    "Memory": "8Gi"
  }
}
```

Fork and verify:

```bash
new_tool_id=$(agr tool fork "$source_tool_id" \
  --tool-name "custom-fork-$(date +%s)-$$" \
  --custom-configuration @custom-override.json \
  -o json --jq '.Data.ToolId')

agr tool get "$new_tool_id" -o json
```

### Per-Instance Overrides

Use per-instance overrides for temporary env/image changes that should not become a new Tool:

```bash
instance_id=$(agr instance create \
  --tool-id "$tool_id" \
  --timeout 30m \
  --custom-configuration '{"Env":[{"Name":"RUN_ID","Value":"test-001"}]}' \
  -o json --jq '.Data.InstanceId')
```

### Custom Tool Checklist

- `ToolType: "custom"`
- `CustomConfiguration.Image`
- `CustomConfiguration.ImageRegistryType`
- `CustomConfiguration.Command` / `Args`
- `CustomConfiguration.Ports`
- `CustomConfiguration.Probe`
- `CustomConfiguration.Resources`
- `RoleArn` for private/personal/enterprise registries or storage mounts

Probe configuration is required for services that must become ready before use. `ReadyTimeoutMs` must be at most `30000`. Validate with `agr tool get <tool-id> -o json`, then start a test Instance, wait for `RUNNING`, and verify the service from inside the Instance before exposing a local proxy.
