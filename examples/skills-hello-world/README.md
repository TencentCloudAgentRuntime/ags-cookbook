# Skills Hello World

This example demonstrates the **minimum viable Skills integration** with AGS:

1. Validate Tencent Cloud credentials using `tencentcloud-sdk-python`
2. Execute code inside an AGS sandbox using `e2b-code-interpreter`
3. Return a structured result that an Agent can consume as a skill output

## What this example demonstrates

- How to structure an AGS Skills example (Python 3.13, `uv`, `pyproject.toml`)
- How to use `tencentcloud-sdk-python` alongside `e2b-code-interpreter` in the same project
- A callable `run_code` skill that an Agent can register as a tool

## Prerequisites

- Python 3.13 (managed by `uv`)
- `uv` installed
- An AGS API key (`E2B_API_KEY`)
- Tencent Cloud credentials (`TENCENTCLOUD_SECRET_ID`, `TENCENTCLOUD_SECRET_KEY`) — optional for the credential health-check

## Required environment variables

Copy `.env.example` to `.env` and fill in your values, then export them:

```bash
cp .env.example .env
# edit .env, then:
export E2B_API_KEY="your_ags_api_key"
export E2B_DOMAIN="ap-guangzhou.tencentags.com"

# Optional — only needed for the credential health-check skill
export TENCENTCLOUD_SECRET_ID="your_secret_id"
export TENCENTCLOUD_SECRET_KEY="your_secret_key"
export TENCENTCLOUD_REGION="ap-guangzhou"
```

## Install and run

```bash
make setup
make run
```

## Expected output

```
INFO Creating sandbox (domain=ap-guangzhou.tencentags.com)…
INFO Sandbox closed.

=== Skill Result ===
{
  "stdout": "372\n",
  "logs": {
    "stdout": ["372\n"],
    "stderr": []
  },
  "error": null
}
```

## Common failure modes

| Symptom | Likely cause |
|---|---|
| `KeyError: 'E2B_API_KEY'` | Environment variable not exported |
| Sandbox creation timeout | Wrong `E2B_DOMAIN` for your region |
| `TencentCloudSDKException` on credential check | Invalid or missing `TENCENTCLOUD_SECRET_ID` / `SECRET_KEY` |

## Skill interface contract

A Skill is a plain Python callable with a clear signature:

```python
def skill_name(arg1: type, ...) -> dict:
    ...
```

- Arguments come from the Agent's tool-call payload
- The return value must be JSON-serialisable so the Agent can parse it
- Secrets are always read from environment variables — never hard-coded
