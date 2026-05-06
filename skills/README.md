# AGS Skills

This directory contains **Skills** — standalone, runnable examples that expose AGS capabilities as plain Python callables an Agent can register as tools.

Each skill follows the conventions defined in [`../SKILLS_STANDARD.md`](../SKILLS_STANDARD.md).

## Authentication — one module, two modes

All skills share a single helper module: [`ags_client.py`](./ags_client.py). It inspects environment variables at runtime and picks one of two modes:

| Mode | Trigger | Sandbox lifecycle |
|---|---|---|
| **APIKey** | `E2B_API_KEY` + `E2B_DOMAIN` set | Sandbox created directly via `e2b-code-interpreter`, killed via `Sandbox.kill()` on exit |
| **AKSK** | `TENCENTCLOUD_SECRET_ID` + `TENCENTCLOUD_SECRET_KEY` set (precedence) | Sandbox lifecycle managed through the Tencent Cloud AGS control plane (`StartSandboxInstance` → `AcquireSandboxInstanceToken` → `StopSandboxInstance`) |

Skill code stays identical across modes — it only imports `SandboxSession` or `BrowserSandboxSession` from `ags_client` and uses them as context managers. When both variable sets are present, AKSK wins. See [`.env.example`](./.env.example) for a template.

The canonical `ags_client.py` lives at the root of this directory; an identical copy is placed inside each skill so that `uv` projects remain self-contained.

## Directory layout

```
skills/
├── basic/                          # 基础沙箱操作（代码执行、文件、数据、凭证）
│   ├── skill-code-interpreter/
│   ├── skill-code-repl/
│   ├── skill-credential-check/
│   ├── skill-data-analysis/
│   ├── skill-data-pipeline/
│   ├── skill-file-roundtrip/
│   └── skill-filesystem-crud/
├── code/                           # Shell / 命令执行
│   ├── skill-run-shell/
│   └── skill-run-shell-stream/
├── browser/                        # 浏览器沙箱
│   ├── skill-browser-navigate/
│   ├── skill-browser-control/
│   └── skill-browser-agent/
├── aio/                            # AIO 沙箱（多语言执行）
│   └── skill-aio-polyglot/
├── storage/                        # 存储挂载
│   └── skill-cos-mount/
├── custom/                         # 自定义镜像
│   └── skill-custom-image/
├── network/                        # 网络 / 认证模式
│   └── skill-public-dataplane/
├── ags_client.py
├── .env.example
└── README.md
```

## Skill index

### `basic/` — 基础沙箱操作

| Skill | Auth | What it covers |
|---|---|---|
| [`skill-code-interpreter`](./basic/skill-code-interpreter/) | APIKey / AKSK | One-shot Python execution in a fresh sandbox; multi-context isolation demo |
| [`skill-code-repl`](./basic/skill-code-repl/) | APIKey / AKSK | Persistent Python session — variables survive across sequential tool calls |
| [`skill-file-roundtrip`](./basic/skill-file-roundtrip/) | APIKey / AKSK | Upload a file → transform it with code inside the sandbox → download the result |
| [`skill-filesystem-crud`](./basic/skill-filesystem-crud/) | APIKey / AKSK | Atomic filesystem primitives: exists / mkdir / remove / list / rename / batch |
| [`skill-data-analysis`](./basic/skill-data-analysis/) | APIKey / AKSK | Upload CSV → pandas aggregation → matplotlib chart → download PNG |
| [`skill-data-pipeline`](./basic/skill-data-pipeline/) | APIKey / AKSK | Multi-stage pipeline: isolated Python contexts sharing a common filesystem |
| [`skill-credential-check`](./basic/skill-credential-check/) | AKSK | Verify AKSK credentials (STS GetCallerIdentity) and list available sandbox images |

### `code/` — Shell 命令执行

| Skill | Auth | What it covers |
|---|---|---|
| [`skill-run-shell`](./code/skill-run-shell/) | APIKey / AKSK | Execute bash commands; structured `{exit_code, stdout, stderr}` return |
| [`skill-run-shell-stream`](./code/skill-run-shell-stream/) | APIKey / AKSK | Bash execution with real-time per-chunk streaming via callbacks |

### `browser/` — 浏览器沙箱

| Skill | Auth | What it covers |
|---|---|---|
| [`skill-browser-navigate`](./browser/skill-browser-navigate/) | APIKey / AKSK | Read-only browser ops: open URL, extract element text, take screenshot |
| [`skill-browser-control`](./browser/skill-browser-control/) | APIKey / AKSK | Drive a page: click, fill inputs, evaluate JS, manage tabs, inject cookies, get NoVNC URL |
| [`skill-browser-agent`](./browser/skill-browser-agent/) | APIKey / AKSK | LLM-in-the-loop multi-step browser automation with observe→decide→act cycle |

### `aio/` — AIO 沙箱（多语言执行）

| Skill | Auth | What it covers |
|---|---|---|
| [`skill-aio-polyglot`](./aio/skill-aio-polyglot/) | APIKey / AKSK | AIO sandbox `/execute` endpoint: run Python, JavaScript, Bash, R, or Java via NDJSON |

### `storage/` — 存储挂载

| Skill | Auth | What it covers |
|---|---|---|
| [`skill-cos-mount`](./storage/skill-cos-mount/) | AKSK | Mount a COS bucket into the sandbox; prove cross-instance file persistence |

### `custom/` — 自定义镜像

| Skill | Auth | What it covers |
|---|---|---|
| [`skill-custom-image`](./custom/skill-custom-image/) | AKSK | Run your own container image with custom entrypoint, ports, and readiness probe |

### `network/` — 网络与认证模式

| Skill | Auth | What it covers |
|---|---|---|
| [`skill-public-dataplane`](./network/skill-public-dataplane/) | AKSK | Start a sandbox with `AuthMode=NONE` — data-plane access without `X-Access-Token` |

## Quick start — APIKey mode

```bash
export E2B_API_KEY="your_ags_api_key"
export E2B_DOMAIN="ap-guangzhou.tencentags.com"

cd skills/basic/skill-code-interpreter
make setup && make run
```

## Quick start — AKSK mode

```bash
export TENCENTCLOUD_SECRET_ID="your_secret_id"
export TENCENTCLOUD_SECRET_KEY="your_secret_key"
export TENCENTCLOUD_REGION="ap-guangzhou"

cd skills/basic/skill-code-interpreter
make setup && make run
```

## Known limitations

- In APIKey mode, `BrowserSandboxSession` reads the sandbox access token from the e2b `Sandbox._envd_access_token` attribute. Works with `e2b>=2.9.0`; if the upstream SDK renames the attribute, update `ags_client.py::BrowserSandboxSession._enter_apikey` accordingly.
- The `timeout` argument accepts a human-readable duration (`"10m"`) in AKSK mode and is converted to seconds (with a hard minimum of `300`) in APIKey mode. Values below the server minimum are silently clamped.
- When both AKSK and APIKey environment variables are set, AKSK wins; this is a deterministic precedence rule implemented in `ags_client.credential_mode()`.
- `skill-code-repl` uses a process-local dict as its REPL registry; multi-process Agent deployments need to wrap the functions with a shared registry (e.g. Redis) keyed on `repl_id`.
- `skill-custom-image` requires `AGS_ROLE_ARN` with image-pull permissions; demo exits early without it.
- `skill-cos-mount` requires an AGS `RoleArn` granting pull / bucket permissions and a `AGS_DEMO_COS_BUCKET` env var; the demo values are placeholders — replace with your real ARN and bucket.
- `skill-aio-polyglot` requires an AIO sandbox tool; in AKSK mode the demo auto-creates a temporary `aio` tool and deletes it on exit. Set `AGS_AIO_TOOL_NAME` to reuse an existing tool.
- `skill-browser-agent` bundles a deterministic `make_echo_llm` helper so the demo runs without any external LLM credential; real-world use replaces it with your own `llm_fn`.
