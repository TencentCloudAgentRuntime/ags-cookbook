# AGR VPC Networking

Load this file when the user asks for private network access, VPC mode, subnet/security group configuration, private services, databases, Redis, private APIs, or a new Tool with different network access.

## Required Inputs

Ask for any missing required values before creating VPC resources:

- `SubnetIds`: one or more subnet IDs, for example `subnet-xxxx`.
- `SecurityGroupIds`: one or more security group IDs, for example `sg-xxxx`.
- Region: use `agr status -o json` to inspect the resolved region, or pass `--region`.
- Target private endpoint to verify, such as a private HTTP URL, database host/port, or Redis host/port.

VPC mode does not use public Internet routing by default. Security group and subnet routing rules must allow the intended outbound traffic from the sandbox.

## Create A VPC Code Tool

```bash
network_config='{
  "NetworkMode": "VPC",
  "VpcConfig": {
    "SubnetIds": ["subnet-xxxx"],
    "SecurityGroupIds": ["sg-xxxx"]
  }
}'

tool_id=$(agr tool create \
  --tool-name "vpc-code-$(date +%s)-$$" \
  --tool-type code-interpreter \
  --network-configuration "$network_config" \
  --default-timeout 1h \
  -o json --jq '.Data.ToolId')

agr tool get "$tool_id" -o json
```

## Create A VPC Custom Service Tool

Use a full request when combining VPC mode with a custom image, ports, probes, resources, RoleArn, or storage mounts.

```json
{
  "ToolName": "vpc-custom-svc-REPLACE",
  "ToolType": "custom",
  "Description": "Custom service with VPC network access",
  "DefaultTimeout": "1h",
  "NetworkConfiguration": {
    "NetworkMode": "VPC",
    "VpcConfig": {
      "SubnetIds": ["subnet-xxxx"],
      "SecurityGroupIds": ["sg-xxxx"]
    }
  },
  "CustomConfiguration": {
    "Image": "ccr.ccs.tencentyun.com/team/app:latest",
    "ImageRegistryType": "enterprise",
    "Command": ["/bin/sh"],
    "Args": ["-c", "python -m uvicorn app:app --host 0.0.0.0 --port 8080"],
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
  }
}
```

```bash
tool_id=$(agr tool create \
  --request @vpc-custom-tool.json \
  -o json --jq '.Data.ToolId')

agr tool get "$tool_id" -o json
```

For private registries or storage mounts, add `RoleArn`; see [custom-images.md](custom-images.md) for custom-image service details and [mount-templates.md](mount-templates.md) for mount JSON.
`ReadyTimeoutMs` must be at most `30000`.

## Fork Existing Tool Into VPC

Use this when the user wants the same Tool settings with VPC network access. VPC network configuration is creation-time only; do not try to update an existing Tool's network mode in place.

```bash
source_tool_id="sdt-xxxx"
agr tool get "$source_tool_id" -o json

new_tool_id=$(agr tool fork "$source_tool_id" \
  --tool-name "vpc-fork-$(date +%s)-$$" \
  --network-configuration '{
    "NetworkMode": "VPC",
    "VpcConfig": {
      "SubnetIds": ["subnet-xxxx"],
      "SecurityGroupIds": ["sg-xxxx"]
    }
  }' \
  -o json --jq '.Data.ToolId')

agr tool get "$new_tool_id" -o json
```

Do not mutate an existing Tool's network configuration. To move a workload between `SANDBOX`, `PUBLIC`, and `VPC`, create or fork a new Tool with the desired `NetworkConfiguration`.

## Validate Private Access

Create a short-lived Instance, wait for `RUNNING`, then verify the specific private target:

```bash
instance_id=$(agr instance create \
  --tool-id "$tool_id" \
  --timeout 30m \
  -o json --jq '.Data.InstanceId')

agr instance get "$instance_id" -o json

# Private HTTP service
agr instance exec "$instance_id" -o json -- sh -lc "curl -fsS http://10.0.0.10:8080/health"

# TCP port check
agr instance exec "$instance_id" -o json -- sh -lc "nc -vz 10.0.0.10 6379"

agr instance delete "$instance_id" --ignore-not-found -o json
```

If validation fails, check region, subnet route tables, security group egress/ingress, private DNS, and whether the target service allows traffic from the selected subnet/security group.
