# Skill: COS-Mounted Sandbox

This example demonstrates **persistent storage across sandbox instances** by mounting a COS (Cloud Object Storage) bucket into the sandbox filesystem. Any file written under `mount_path` survives instance teardown and is visible to every subsequent instance that mounts the same bucket+path — the canonical way to share state between short-lived sandboxes.

The flow mirrors `e2e/storage/cos_mount/*`:

1. `CreateSandboxTool` with `StorageMounts=[{Name, StorageSource:{Cos:{BucketName, BucketPath}}, MountPath}]`
2. `StartSandboxInstance` referencing that Tool
3. Read / write files under `mount_path` — changes are synced to COS automatically
4. Stop / repeat — data persists

> **AKSK-only.** COS mount configuration is a control-plane-only feature.

## What this example demonstrates

- **`start_cos_sandbox(cos_bucket, cos_path, mount_path, role_arn, …)`** — create a tool with the mount, start one instance, return identifiers
- **`write_then_read_across_instances(cos_bucket, cos_path, mount_path, content)`** — full demonstration: start A, write, stop A, start B, read, stop B, verify `match == True`
- **`stop_cos_sandbox(instance_id, tool_id=None, delete_tool_after=False)`** — teardown

## Prerequisites

- Python 3.13 (managed by `uv`)
- `uv` installed
- Valid Tencent Cloud credentials
- A COS bucket you own, and a `RoleArn` that grants AGS permission to read/write under the bucket path

## Required environment variables

```bash
export TENCENTCLOUD_SECRET_ID="your_secret_id"
export TENCENTCLOUD_SECRET_KEY="your_secret_key"
export TENCENTCLOUD_REGION="ap-guangzhou"

export AGS_ROLE_ARN="qcs::cam::uin/<uin>:roleName/<role>"
export AGS_DEMO_COS_BUCKET="my-bucket-1300000000"
export AGS_DEMO_COS_PATH="skills-demo/"
export AGS_DEMO_COS_MOUNT="/mnt/cos"
```

## Install and run

```bash
make setup
make run
```

## Expected output

```
=== Skill Result: write_then_read_across_instances ===
{
  "tool_id":     "tool-xxxxxxxx",
  "written_in":  "sbi-AAAAAAAA",
  "read_from":   "sbi-BBBBBBBB",
  "expected":    "cross-instance @ 0a1b2c…",
  "retrieved":   "cross-instance @ 0a1b2c…",
  "match":       true,
  "round_trip_bytes": 32
}
```

`match == true` confirms the file written by instance A was durably persisted to COS and then correctly mounted into instance B. The demo deletes the tool afterwards; your own COS files stay in the bucket.

## Common failure modes

| Symptom | Likely cause |
|---|---|
| `KeyError: 'E2B_API_KEY'` | Not applicable — this skill is AKSK-only |
| Sandbox creation timeout | `E2B_DOMAIN` wrong (only affects other skills) |
| `TencentCloudSDKException` on credential check | Invalid or missing `TENCENTCLOUD_SECRET_ID` / `SECRET_KEY` |
| `InvalidParameter` on `CreateSandboxTool` | Missing `RoleArn`, or the bucket is in a region other than your AGS region |
| `retrieved != expected` | The COS mount sync lag exceeded the test; retry or add a `time.sleep` between write and the B instance start |
| `AccessDenied` inside the sandbox when writing | `RoleArn` lacks `cos:PutObject` on the bucket path |

## Skill interface

```python
start_cos_sandbox(
    cos_bucket: str, cos_path: str, mount_path: str,
    *, role_arn: str | None = None,
    tool_type: str = "code-interpreter",
    tool_name: str | None = None, timeout: str = "10m",
    read_only: bool = False,
) -> dict

write_then_read_across_instances(
    cos_bucket: str, cos_path: str, mount_path: str,
    content: str = "…",
    *, role_arn: str | None = None, timeout: str = "10m",
) -> dict

stop_cos_sandbox(instance_id: str, tool_id: str | None = None, delete_tool_after: bool = False) -> dict
```
