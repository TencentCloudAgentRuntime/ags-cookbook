# AgentCBS VolumeTemplate: start a sandbox with a persistent disk

This example starts a `custom` AGS sandbox with an **AgentCBS** block-storage
Volume mounted at `/workspace`. The data on that Volume is kept after the
sandbox is gone.

- **No image build**: the sandbox uses the public code interpreter image
  `ccr.ccs.tencentyun.com/ags-image/sandbox-code:latest`.
- **No manual Volume management**: the Tool references a **VolumeTemplate**.
  For each `reuse_key` passed at sandbox start, AGS creates a Volume the first
  time and mounts the same Volume on every later start.

```text
VolumeTemplate (AgentCbs, 10Gi, ReadWriteOnce, Retain)
        │  referenced by
SandboxTool (custom, sandbox-code image)
  StorageMounts: workspace → /workspace, ReuseKey=${metadata.reuse_key}
        │  Sandbox.create(metadata={"reuse_key": "session-s001", ...})
Derived Volume <template>-ws-session-s001   (created on first start, reused afterwards)
```

## Quick start

```bash
cp .env.example .env    # fill in the 4 required values, see below
make setup              # optional: install dependencies now (make run also does it)
make run                # run the demo
make cleanup            # deletes the Tool, the Volumes (and their data), and the template
```

`make run` does the following:

1. On the first run, it creates the VolumeTemplate and the SandboxTool and
   waits until both are `ACTIVE`. Their IDs are saved in `.state/` and reused
   by later runs.
2. It starts a sandbox with `reuse_key=session-s001`. AGS mounts that key's
   Volume at `/workspace`.
3. It writes a line to `/workspace/notes.txt` with `run_code`, prints the file,
   and kills the sandbox.

Run `make run` again and `notes.txt` has one more line, because the same Volume
is mounted again.

If you do not use `uv`, run the scripts with any Python 3.11+ environment:

```bash
pip install "e2b>=2.55.1" "e2b-code-interpreter>=2.11.5" "tencentcloud-sdk-python-common>=3.1.32"
python scripts/run.py
python scripts/cleanup.py
```

## Prerequisites

- [`uv`](https://docs.astral.sh/uv/) (or pip with Python 3.11+, see above).
- An AGS account in a region where AgentCBS is available. Verified in `ap-guangzhou`.
- The following values for `.env`:

| Variable | Where to get it |
|---|---|
| `TENCENTCLOUD_SECRET_ID` / `TENCENTCLOUD_SECRET_KEY` | [CAM API keys](https://console.cloud.tencent.com/cam/capi). The identity must be allowed to call these AGS APIs: `CreateVolumeTemplate`, `DescribeVolumeTemplateList`, `CreateSandboxTool`, `DescribeSandboxToolList`, and `DescribeVolumeList` for `make run`; `DeleteSandboxTool`, `DeleteVolume`, and `DeleteVolumeTemplate` for `make cleanup`. |
| `TENCENTCLOUD_REGION` | AGS region, default `ap-guangzhou`. |
| `E2B_API_KEY` | AGS API Key from the Agent Runtime console. It starts with `ark_` and is different from the SecretId/SecretKey. |
| `ROLE_ARN` | CAM role that AGS assumes to pull the image. Create it as described in steps 2 and 3 of [Create a custom sandbox](https://cloud.tencent.com/document/product/1814/129691): a role for the Agent Runtime service with CCR pull permission, plus `cam:PassRole` on that role for the caller. |

Optional values in `.env`:

| Variable | Default | Description |
|---|---|---|
| `E2B_DOMAIN` | `<TENCENTCLOUD_REGION>.tencentags.com` | E2B endpoint |
| `SESSION_ID` | `session-s001` | Reuse key. The same key mounts the same Volume. Lowercase letters, digits, `-`, `_`, at most 128 characters. |
| `VOLUME_CAPACITY` | `10Gi` | Disk size, used when the template is created |
| `SANDBOX_IMAGE_REF` | `ccr.ccs.tencentyun.com/ags-image/sandbox-code:latest` | Your own image built `FROM` the code interpreter image |
| `SANDBOX_IMAGE_REGISTRY_TYPE` | `personal` | `personal` (CCR) or `enterprise` (TCR) |

## Expected output

```text
Created VolumeTemplate agentcbs-ws-1028135535 (10Gi): volt-pjospoun
volume template status: ACTIVE
Created SandboxTool agentcbs-code-1028135536: sdt-m1lyuepb
tool status: CREATING
tool status: ACTIVE

== Start a sandbox with reuse_key=session-s001 ==
Sandbox started: ermyibaxia4ppyqt7ebotpf5uhzqms6qvyc42ed3 (14.0s)
Mount:
/dev/vda /workspace ext4 rw,relatime 0 0
/dev/vda        9.8G   24K  9.3G   1% /workspace
Volume: vol-01a18114-1d4f-8001-b361-e78a5ff909a6 (agentcbs-ws-1028135535-ws-session-s001, 10Gi, mounted_by=ermyibaxia4ppyqt7ebotpf5uhzqms6qvyc42ed3)
/workspace/notes.txt:
2026-10-28 05:55:56 written by ermyibaxia4ppyqt7ebotpf5uhzqms6qvyc42ed3
Sandbox killed: ermyibaxia4ppyqt7ebotpf5uhzqms6qvyc42ed3 (the Volume is retained)
AGENTCBS_VOLUME_OK
```

A start that mounts AgentCBS is always a cold start and does not use a
pre-created sandbox. With this 1.8 GB image it takes about 10–17 seconds.

## How it works

### 1. VolumeTemplate (`CreateVolumeTemplate`)

```json
{
  "VolumeTemplateName": "agentcbs-ws",
  "StorageType": "AgentCbs",
  "StorageSpec": {"AgentCbs": {"Capacity": "10Gi"}},
  "VolumeNamePattern": "ws-${reuse_key}",
  "AccessMode": "ReadWriteOnce",
  "ReclaimPolicy": "Retain"
}
```

AgentCBS templates support only `ReadWriteOnce` with `ReclaimPolicy=Retain`.
`VolumeNamePattern` must contain `${reuse_key}`. AGS adds the template name as a
prefix, so the derived Volume is named `<template>-ws-<reuse_key>`.

### 2. SandboxTool (`CreateSandboxTool`)

The image settings follow [Create a custom sandbox](https://cloud.tencent.com/document/product/1814/129691).
`StorageMounts` references the template:

```json
{
  "ToolName": "agentcbs-code",
  "ToolType": "custom",
  "NetworkConfiguration": {"NetworkMode": "PUBLIC"},
  "RoleArn": "qcs::cam::uin/<uin>:roleName/<role>",
  "CustomConfiguration": {
    "Image": "ccr.ccs.tencentyun.com/ags-image/sandbox-code:latest",
    "ImageRegistryType": "personal",
    "Command": ["/init"],
    "Args": ["sleep", "infinity"],
    "Ports": [
      {"Name": "run-code", "Port": 49999, "Protocol": "TCP"},
      {"Name": "envd", "Port": 49983, "Protocol": "TCP"}
    ],
    "Resources": {"CPU": "2", "Memory": "1Gi"},
    "Probe": {
      "HttpGet": {"Path": "/health", "Port": 49999, "Scheme": "HTTP"},
      "ReadyTimeoutMs": 30000, "ProbeTimeoutMs": 1000, "ProbePeriodMs": 1000,
      "SuccessThreshold": 1, "FailureThreshold": 30
    }
  },
  "StorageMounts": [{
    "Name": "workspace",
    "VolumeTemplate": {"VolumeTemplateName": "agentcbs-ws", "ReuseKey": "${metadata.reuse_key}"},
    "MountPath": "/workspace",
    "ReadOnly": false
  }]
}
```

- The API requires `Command` and `Probe.HttpGet.Scheme`.
- The probe checks `run-code` on port `49999`. If it checks `envd` on `49983`
  instead, the sandbox can be reported ready before the code interpreter is up,
  and the first `run_code()` fails.

### 3. Start the sandbox (E2B SDK)

```python
from e2b_code_interpreter import Sandbox

sandbox = Sandbox.create(
    template="<tool id or name>",
    metadata={
        "reuse_key": "session-s001",             # fills ${metadata.reuse_key}
        "x-ags-agent-cbs-system-disk": "true",   # required for AgentCBS, lowercase "true"
    },
)
sandbox.run_code("open('/workspace/notes.txt', 'a').write('hello\\n')")
sandbox.kill()   # the Volume is retained
```

The E2B SDK does not manage templates, Volumes, or Tools. `scripts/run.py`
creates them with Tencent Cloud API 3.0 through the `CommonClient` of
`tencentcloud-sdk-python-common`.

## Cleanup

```bash
make cleanup
```

This deletes the Tool, every Volume derived from the template, and the
template itself. **Deleting a Volume deletes its data.** `DeleteVolume` returns
as soon as the request is accepted, and the disk is released in the background.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `... is not set; fill it in .env` | Copy `.env.example` to `.env` and fill in the required values. |
| `Invalid API key format: expected "e2b_"...` | The installed `e2b` 2.25–2.45 rejects AGS keys (`ark_...`). Run `pip install -U "e2b>=2.55.1" "e2b-code-interpreter>=2.11.5"`. |
| `AuthFailure...` / `UnauthorizedOperation` | Check the SecretId/SecretKey and their AGS permissions. |
| `MissingParameter.RoleArn`, or the Tool fails to pull the image | Check `ROLE_ARN`, its CCR permission, and the caller's `cam:PassRole` on it, then run `make run` again. A Tool in `FAILED` status is replaced automatically; the template and Volumes are kept. |
| `ResourceInUse` on start | The Volume is `ReadWriteOnce`, and another running sandbox with the same `reuse_key` still holds it. Kill that sandbox, or use a different `SESSION_ID`. |
| `UnsupportedOperation.SandboxInstance: AgentCBS Volume requires metadata x-ags-agent-cbs-system-disk=true` | Add the metadata entry when you start the sandbox. |
| `FailedOperation.ImagePrepare` with a built-in template such as `code-interpreter-v1` | Built-in templates cannot mount AgentCBS. Use a `custom` Tool, as this example does. |
| `InvalidParameter: Storage.AgentCbs.Capacity must be a positive integer with the Gi suffix` | Use values such as `10Gi`. |

## AgentCBS limits

- Only `ReadWriteOnce`: a Volume can be mounted by one running sandbox at a time.
  Read-only mounts, `SubPath`, and mounting at `/` are not supported.
- A sandbox can mount at most one AgentCBS Volume. It can still mount COS or CFS alongside it.
- `StartSandboxInstance.StorageMounts` and E2B `x-storage` cannot reference a
  VolumeTemplate. Template mounts must be declared on the Tool.
- Sandboxes that mount AgentCBS support only `DISK` Pause/Resume.
- The Volume and the sandbox must be in the same region.

## Files

| File | Purpose |
|---|---|
| `scripts/run.py` | Creates or reuses the template and Tool, then starts the sandbox and uses the Volume |
| `scripts/cleanup.py` | Deletes everything that `run.py` created |
| `scripts/common.py` | Loads `.env`, provides the Tencent Cloud API client, and stores resource IDs in `.state/` |
| `.env.example` | Configuration template |
