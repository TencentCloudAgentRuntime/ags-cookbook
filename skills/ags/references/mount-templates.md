# AGS Storage Mount Templates

Use these with `agr tool create --storage-mounts @file.json` or `agr tool create --request @tool.json`. Validate the installed CLI with:

```bash
agr tool create --help
agr instance create --help
agr schema -o json
```

## COS Mount

`RoleArn` is required for COS access. Bucket names usually include the APPID suffix.

```json
[
  {
    "Name": "cos-assets",
    "StorageSource": {
      "Cos": {
        "BucketName": "team-shared-1250000000",
        "BucketPath": "/datasets"
      }
    },
    "MountPath": "/mnt/assets",
    "ReadOnly": false
  }
]
```

```bash
agr tool create \
  --tool-name "cos-tool-$(date +%s)-$$" \
  --tool-type code-interpreter \
  --network-configuration '{"NetworkMode":"PUBLIC"}' \
  --role-arn "qcs::cam::uin/100000000:roleName/ags-cos-role" \
  --storage-mounts @cos-mount.json \
  -o json
```

## CFS And Image Mounts

Use `--request` when several nested fields are required.

```json
{
  "ToolName": "analysis-runtime",
  "ToolType": "custom",
  "NetworkConfiguration": {
    "NetworkMode": "PUBLIC"
  },
  "RoleArn": "qcs::cam::uin/100000000:roleName/ags-storage-role",
  "StorageMounts": [
    {
      "Name": "cfs-workspace",
      "StorageSource": {
        "Cfs": {
          "FileSystemId": "cfs-12345678",
          "Path": "/team/project-a"
        }
      },
      "MountPath": "/workspace/project-a",
      "ReadOnly": false
    },
    {
      "Name": "image-seed",
      "StorageSource": {
        "Image": {
          "Reference": "ccr.ccs.tencentyun.com/team/bootstrap:v1",
          "ImageRegistryType": "CCR",
          "SubPath": "/seed"
        }
      },
      "MountPath": "/opt/seed",
      "ReadOnly": true
    }
  ]
}
```

```bash
agr tool create --request @tool-storage.json --non-interactive -o json
```

## Fork Existing Tool And Add CFS

Use this when the user wants a new Tool based on an existing Tool, such as
"fork `sdt-1234567` and mount CFS `cfs-1234567`".

First inspect the source Tool. Reuse its `RoleArn` if present; otherwise ask the user for the CAM role ARN that can access the CFS filesystem. Current `agr tool update` does not expose a direct `--storage-mounts` flag, so create a new fork instead of mutating the source Tool in place.

```bash
source_tool_id="sdt-1234567"
agr tool get "$source_tool_id" -o json
```

Create a CFS mount file. Choose a mount name and path that do not conflict with existing mounts on the source Tool.

```json
[
  {
    "Name": "cfs-workspace",
    "StorageSource": {
      "Cfs": {
        "FileSystemId": "cfs-1234567",
        "Path": "/"
      }
    },
    "MountPath": "/workspace/cfs",
    "ReadOnly": false
  }
]
```

Fork the Tool with the new mount. Include `--role-arn` if the source Tool does not already have an appropriate role or if the mount requires a different role.

```bash
new_tool_id=$(agr tool fork "$source_tool_id" \
  --tool-name "fork-cfs-$(date +%s)-$$" \
  --storage-mounts @cfs-mount.json \
  -o json --jq '.Data.ToolId')

agr tool get "$new_tool_id" -o json
```

If a role must be supplied or overridden:

```bash
new_tool_id=$(agr tool fork "$source_tool_id" \
  --tool-name "fork-cfs-$(date +%s)-$$" \
  --role-arn "qcs::cam::uin/100000000:roleName/ags-cfs-role" \
  --storage-mounts @cfs-mount.json \
  -o json --jq '.Data.ToolId')
```

Validate by starting a short-lived Instance and checking the mount path:

```bash
instance_id=$(agr instance create \
  --tool-id "$new_tool_id" \
  --timeout 30m \
  -o json --jq '.Data.InstanceId')

agr instance get "$instance_id" -o json
agr instance exec "$instance_id" -o json -- ls -la /workspace/cfs
agr instance delete "$instance_id" --ignore-not-found -o json
```

## Instance MountOptions

`MountOptions` can only reference names already defined in Tool `StorageMounts`.

```json
[
  {
    "Name": "cos-assets",
    "MountPath": "/workspace/input",
    "SubPath": "run-001",
    "ReadOnly": true
  },
  {
    "Name": "cos-assets",
    "MountPath": "/workspace/output",
    "SubPath": "run-002",
    "ReadOnly": false
  }
]
```

```bash
agr instance create \
  --tool-id "$tool_id" \
  --mount-options @mount-options.json \
  --timeout 30m \
  -o json
```

## Path Rules

- `MountPath` must be absolute, cannot be `/`, cannot contain `.` or `..`, and cannot duplicate another resolved mount path.
- `SubPath` must be relative, cannot start with `/`, and cannot contain `.` or `..`.
- `mobile` and `android-world` mount under `/data/local/tmp/mnt`.
- `osworld` mounts under `/tmp/mnt`.
- For other Tool types, avoid system paths such as `/bin`, `/etc`, `/tmp`, `/usr`, `/var`; use subdirectories under `/workspace`, `/mnt`, `/home`, or `/data`.
