# Autonomous Decision Log

This log records material decisions made during autonomous execution so the reasoning is preserved even if conversational context is lost.

## 2026-03-21

### Decision: align Tencent Cloud credential names to `TENCENTCLOUD_*` only
- Reason: user explicitly required alignment with Tencent Cloud / AGS SDK expectations and rejected compatibility aliases.
- Alternatives considered: keep backward-compatible `TENCENT_*` fallback.
- Outcome: code and docs now use `TENCENTCLOUD_SECRET_ID`, `TENCENTCLOUD_SECRET_KEY`, and repo-local `TENCENTCLOUD_REGION` only.

### Decision: do not switch Go examples to `AGS_REGION` yet
- Reason: `ags-go-sdk` examples show `AGS_REGION`, but the user explicitly deferred this change.
- Alternatives considered: update Go examples immediately to follow `ags-go-sdk` style.
- Outcome: region naming difference is acknowledged but intentionally left unchanged.

### Decision: treat root README as user-facing, not maintainer-facing
- Reason: user clarified that DX in this repository primarily targets AGS users and example readers.
- Alternatives considered: place maintainer principles in README.
- Outcome: maintenance-oriented principles were kept in draft/supporting docs instead of expanding user-facing README with internal process rules.

### Decision: local-first execution before hosted CI
- Reason: user required local `make` execution to become the primary contract before heavier GitHub-hosted validation.
- Alternatives considered: prioritize GitHub E2E workflows.
- Outcome: repository work focused first on `make`-based local setup/run/check entrypoints. Any CI added later mirrors those local commands.

### Decision: move `osworld-ags` to uv-managed isolated installs without changing its region example
- Reason: user wanted to avoid accidental pollution of the local machine, but also noted that the Singapore domain may be intentionally chosen for network conditions.
- Alternatives considered: keep `pip install -r requirements.txt`; switch doc examples to Guangzhou.
- Outcome: `osworld-ags` now uses `uv` to create `osworld/.venv` and install dependencies there, while documentation keeps `ap-singapore.tencentags.com` as the example domain.

### Decision: preserve real validation evidence in local reports
- Reason: user explicitly required per-example records to avoid losing context and to ensure fixes are grounded in real execution.
- Alternatives considered: summarize validation only in chat.
- Outcome: `reports/example-runs/` remains the evidence source for actual example execution outcomes.
