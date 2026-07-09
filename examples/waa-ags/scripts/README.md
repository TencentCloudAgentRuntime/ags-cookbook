# WAA Tool management CLI

`waa_tool.py` is a small, dependency-free helper for managing **WAA Sandbox
Tools** (a.k.a. *templates*) in [Tencent Cloud AGS](https://cloud.tencent.com/document/product/1899)
directly via CloudAPI.

We ship it because the AGS console **does not yet have a UI for creating WAA
tools**. Until that page is online you need a `ToolId` (`sdt-xxxx`) for the
`AGS_TEMPLATE` field in [.env.example](../.env.example), and this script is the
fastest way to get one.

> 中文版见 [README_zh.md](./README_zh.md).

---

## What this script is — and isn't

It **is**:

- An out-of-band utility for the four operations the console can't do yet:
  `list` / `get` / `create` / `delete` of WAA tools.
- 100% self-contained: only the Python 3 standard library (no `e2b`, no
  `openssl`, no `jq`, no `pip install`).
- Safe to run anywhere: it never writes to `examples/waa-ags/.env` or any
  other config file.

It is **not**:

- Part of `make run`. You run it manually, once, when you need a tool.
- A way to manage **API keys** — those you still get from the AGS console.
- A way to manage **sandbox instances** — instances are created and torn
  down automatically by `make run` (via the e2b SDK).

---

## Prerequisites

- Python 3.8+ (already on macOS / most Linux distros).
- A Tencent Cloud account with AGS enabled in the region you target.
- A pair of `SecretId` / `SecretKey` for that account. Generate them at
  <https://console.cloud.tencent.com/cam/capi> if you don't have one.

That's it — no `pip install`, no virtualenv.

---

## Configuration

Credentials and region can be supplied in three ways. **Higher precedence
wins**:

1. Command-line flags: `--secret-id`, `--secret-key`, `--region`.
2. Environment variables:

   ```bash
   export TENCENTCLOUD_SECRET_ID=AKIDxxxxxxxxxxxxxxxx
   export TENCENTCLOUD_SECRET_KEY=xxxxxxxxxxxxxxxxxxxxxxxx
   export AGS_REGION=ap-guangzhou
   ```

3. A `.env` file. The script falls back to (in order):
   - `examples/waa-ags/scripts/.env`
   - `examples/waa-ags/.env`

   …**but only for keys not already provided** by (1) or (2). The script
   never writes to either file.

> **Region has no default.** You must specify it. The expected value is the
> AGS region code such as `ap-guangzhou`. The script aborts with a helpful
> error if it can't resolve a region.

---

## Commands

Run from the repo root or from `examples/waa-ags/`. All examples below use
`python3 scripts/waa_tool.py …`.

### `list` — list all WAA tools in the current account

```bash
python3 scripts/waa_tool.py list
```

Sample output (table to stdout, log to stderr):

```text
TOOL_ID         NAME                STATUS  TYPE  CREATE_TIME
sdt-6h8pj4cl    waa-20260620-101530 ACTIVE  waa   2026-06-20T10:15:31Z
sdt-abcd1234    dev-tool            ACTIVE  waa   2026-06-25T03:42:11Z
```

Add `--json` to get the raw API objects (handy for piping into `jq`):

```bash
python3 scripts/waa_tool.py list --json | jq '.[] | {ToolId, Status}'
```

### `get` — show details of one tool

```bash
python3 scripts/waa_tool.py get --tool-id sdt-6h8pj4cl
```

Prints the full `SandboxTool` object as pretty-printed JSON.

### `create` — create a new WAA tool and wait until it's ACTIVE

```bash
# Auto-generated name (waa-YYYYMMDD-HHMMSS):
python3 scripts/waa_tool.py create

# Custom name:
python3 scripts/waa_tool.py create --name my-waa-tool

# Private network mode + longer wait:
python3 scripts/waa_tool.py create \
  --name internal-waa \
  --network-mode PRIVATE \
  --wait-seconds 240
```

Behaviour:

- Calls `CreateSandboxTool` with `ToolType=waa` and the requested
  `NetworkConfiguration.NetworkMode`.
- Polls `DescribeSandboxToolList` every 2 seconds. Logs status transitions
  to **stderr**.
- On success, prints **only the `ToolId`** to **stdout** as the very last
  line — perfect for shell substitution:

  ```bash
  TOOL_ID=$(python3 scripts/waa_tool.py create --name my-waa-tool | tail -n1)
  echo "$TOOL_ID"   # sdt-xxxxxxxx
  ```

- If the tool transitions to `FAILED`, or doesn't reach `ACTIVE` within
  `--wait-seconds` (default 120), the script exits non-zero. The tool may
  still exist; re-check with `get`.

| Flag | Default | Notes |
|---|---|---|
| `--name` | `waa-YYYYMMDD-HHMMSS` | Free-form name, must be unique per account |
| `--network-mode` | `PUBLIC` | `PUBLIC` or `PRIVATE` |
| `--wait-seconds` | `120` | How long to wait for `ACTIVE` |

### `delete` — delete a WAA tool

```bash
python3 scripts/waa_tool.py delete --tool-id sdt-6h8pj4cl
```

This deletes the **template only**. Sandbox **instances** spawned from this
tool are not affected by this call; they are managed by the e2b SDK that
`make run` uses, and are torn down automatically when `make run` exits.

---

## Typical workflow: provision `AGS_TEMPLATE` for a fresh `examples/waa-ags/.env`

```bash
# 1. Provide credentials (one-shot; not persisted to .env by the script).
export TENCENTCLOUD_SECRET_ID=AKIDxxxxxxxxxxxxxxxx
export TENCENTCLOUD_SECRET_KEY=xxxxxxxxxxxxxxxxxxxxxxxx
export AGS_REGION=ap-guangzhou

cd examples/waa-ags

# 2. See if a usable tool already exists.
python3 scripts/waa_tool.py list

# 3. If not, create one and capture the ToolId.
TOOL_ID=$(python3 scripts/waa_tool.py create --name dev-waa | tail -n1)
echo "AGS_TEMPLATE=$TOOL_ID"

# 4. Put TOOL_ID into examples/waa-ags/.env as AGS_TEMPLATE,
#    then continue with `make run` as usual.
```

---

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | Generic failure (missing creds, AGS API error, FAILED status, timeout, etc.) |
| `130` | Interrupted with Ctrl-C |

All errors are written to **stderr** prefixed with `[error]`; informational
logs use `[info]` / `[warn]`. Capture stderr if you script around it:

```bash
python3 scripts/waa_tool.py create 2> create.log
```

---

## Troubleshooting

**`missing credentials/config: TENCENTCLOUD_SECRET_ID …`**
The script could not resolve a credential. Set the environment variable, or
pass `--secret-id` / `--secret-key`. Note that values in `.env` are only used
if they're not already set in the environment.

**`missing credentials/config: AGS_REGION …`**
You must specify a region — the script intentionally has no default to avoid
silently hitting the wrong one. Use `ap-guangzhou` (or whichever region your
AGS account is enabled in).

**`CreateSandboxTool failed: code=AuthFailure.SignatureFailure …`**
Check the system clock — TC3 signatures expire quickly. `date -u` should
match real UTC within a few minutes.

**`CreateSandboxTool failed: code=LimitExceeded.* …`**
Your account has hit a quota. List existing tools (`list`) and delete the
ones you no longer need. Quotas like `APIKeyQuota` are global per
sub-account across regions, so creating in another region won't help.

**`tool sdt-xxxx did not become ACTIVE within 120s`**
Re-run `get --tool-id sdt-xxxx` — the tool may still finish provisioning
later. Use `--wait-seconds 240` (or higher) on `create` if your account
typically takes longer.

---

## How it works (one paragraph)

The script signs each request with **TC3-HMAC-SHA256** (the signed canonical
request only includes `content-type` and `host`, matching the official SDKs)
and POSTs to `https://ags.tencentcloudapi.com/` with the standard
`X-TC-Action` / `X-TC-Region` / `X-TC-Version` headers. Three CloudAPI
actions are used: `CreateSandboxTool`, `DescribeSandboxToolList`, and
`DeleteSandboxTool`. No SDK, no extra dependencies. See
[`waa_tool.py`](./waa_tool.py) for the ~400-line implementation.
