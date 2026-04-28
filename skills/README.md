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

## Skill index

### Code sandbox

| Skill | Auth | What it covers |
|---|---|---|
| [`skill-code-interpreter`](./skill-code-interpreter/) | APIKey / AKSK | Single-shot execution; multi-context isolation |
| [`skill-code-repl`](./skill-code-repl/) | APIKey / AKSK | Persistent Python REPL — variables survive across tool calls |
| [`skill-run-shell`](./skill-run-shell/) | APIKey / AKSK | Bash command execution; `{exit_code, stdout, stderr}` |
| [`skill-run-shell-stream`](./skill-run-shell-stream/) | APIKey / AKSK | Bash with **real-time** chunk streaming callbacks |
| [`skill-file-sandbox`](./skill-file-sandbox/) | APIKey / AKSK | File upload, in-sandbox transform, download |
| [`skill-file-ops-extended`](./skill-file-ops-extended/) | APIKey / AKSK | `exists` / `mkdir` / `remove` / `list` / `rename` / batch ops |
| [`skill-data-analysis`](./skill-data-analysis/) | APIKey / AKSK | CSV → pandas → matplotlib chart |
| [`skill-data-pipeline`](./skill-data-pipeline/) | APIKey / AKSK | Multi-context pipeline: isolated Python state, shared filesystem |

### Browser sandbox

| Skill | Auth | What it covers |
|---|---|---|
| [`skill-browser-action`](./skill-browser-action/) | APIKey / AKSK | Page navigation, element text extraction, full-page screenshot |
| [`skill-browser-interact`](./skill-browser-interact/) | APIKey / AKSK | Click, fill, evaluate JS, multi-tab, cookies, NoVNC URL |
| [`skill-browser-agent`](./skill-browser-agent/) | APIKey / AKSK | LLM-driven multi-step tool loop; runnable with a scripted echo LLM |

### AIO sandbox (uvicorn / multi-language)

| Skill | Auth | What it covers |
|---|---|---|
| [`skill-multi-lang-exec`](./skill-multi-lang-exec/) | APIKey / AKSK | `/execute` NDJSON endpoint: Python / JavaScript / Bash / R / Java |

### Control-plane only (AKSK)

| Skill | Auth | What it covers |
|---|---|---|
| [`skill-tencent-cloud-api`](./skill-tencent-cloud-api/) | AKSK | STS `GetCallerIdentity`; AGS image listing |
| [`skill-sandbox-lifecycle`](./skill-sandbox-lifecycle/) | AKSK | Pause / Resume (Full, Disk), DescribeInstanceList, AutoPause/Resume, stop |
| [`skill-custom-instance`](./skill-custom-instance/) | AKSK | Create tool with custom image / command / ports / probe; start / stop |
| [`skill-cos-sandbox`](./skill-cos-sandbox/) | AKSK | COS mount; cross-instance persistence proof |
| [`skill-noauth-sandbox`](./skill-noauth-sandbox/) | AKSK | `AuthMode=NONE` — data-plane access without `X-Access-Token` |

`skill-tencent-cloud-api` and every skill in the AKSK-only section never create a data-plane session; they raise `RuntimeError` if invoked without AKSK credentials.

## Quick start — APIKey mode

```bash
export E2B_API_KEY="your_ags_api_key"
export E2B_DOMAIN="ap-guangzhou.tencentags.com"

cd skills/skill-code-interpreter
make setup && make run
```

## Quick start — AKSK mode

```bash
export TENCENTCLOUD_SECRET_ID="your_secret_id"
export TENCENTCLOUD_SECRET_KEY="your_secret_key"
export TENCENTCLOUD_REGION="ap-guangzhou"

cd skills/skill-code-interpreter
make setup && make run
```

## Moved from the previous layout

Earlier revisions of this directory contained parallel `apikey/` and `aksk/` sub-trees with the same five skills duplicated. The current layout replaces that with a single flat set of `skill-*/` directories backed by an auto-detecting `ags_client.py`; existing references to `skills/apikey/<name>/` or `skills/aksk/<name>/` should be updated to `skills/<name>/`.

## Known limitations

- In APIKey mode, `BrowserSandboxSession` reads the sandbox access token from the e2b `Sandbox._envd_access_token` attribute. This mirrors the pattern previously used by `skills/apikey/skill-browser-action/main.py` and works with `e2b>=2.9.0`; if the upstream SDK renames the attribute, update `ags_client.py::BrowserSandboxSession._enter_apikey` accordingly.
- The `timeout` argument accepts a human-readable duration (`"10m"`) in AKSK mode and is converted to seconds (with a hard minimum of `300`) in APIKey mode. Values below the server minimum are silently clamped.
- When both AKSK and APIKey environment variables are set, AKSK wins; this is a deterministic precedence rule implemented in `ags_client.credential_mode()`.
- `skill-code-repl` uses a process-local dict as its REPL registry; multi-process Agent deployments need to wrap the functions with a shared registry (e.g. Redis) keyed on `repl_id`.
- `skill-custom-instance` / `skill-cos-sandbox` require an AGS `RoleArn` granting pull / bucket permissions; the demo `AGS_ROLE_ARN` value is a placeholder — replace with your real ARN.
- `skill-multi-lang-exec` and the AIO demo in `skill-noauth-sandbox` assume a tool image that ships `uvicorn` on port 49999 (i.e. the `aio-v1` family). Running them against `code-interpreter-v1` / `browser-v1` will return `404` on `/execute`.
- `skill-browser-agent` bundles a deterministic `make_echo_llm` helper so the demo runs without any external LLM credential; real-world use replaces it with your own `llm_fn`.
- No `uv.lock` is committed for the new P1~P3 skills — run `uv sync` in each skill directory on first use; the canonical 5 skills (`skill-code-interpreter`, `skill-file-sandbox`, `skill-browser-action`, `skill-tencent-cloud-api`, `skill-data-analysis`) inherit locks from their AKSK-mode ancestors.
