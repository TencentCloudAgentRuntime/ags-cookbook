# Example Validation Summary

This file summarizes the latest full example validation round performed from a real development environment.

## Status Matrix

| Example | Status | Notes |
|---|---|---|
| `browser-agent` | fixed-pass | Needed LLM timeout hardening, tool-result truncation, and `click_element` fix |
| `custom-image-go-sdk` | fixed-pass | Default `custom-dev` tool was unhealthy; fallback tool worked |
| `data-analysis` | fixed-pass | Default `tencentags.com` failed; explicit AGS region domain worked |
| `html-processing` | pass | Worked after explicit AGS region domain was provided |
| `hybrid-cookbook` | pass | Minimal Go control-plane + data-plane flow validated successfully |
| `mini-rl` | pass | Core code-interpreter flow healthy |
| `mobile-use` | fixed-pass | Core path worked; long-running phase needed env-configurable bypass |
| `osworld-ags` | fixed-pass | Documented `AGS_TEMPLATE=osworld` was stale; real available tool was different |
| `shop-assistant` | fixed-pass | `cookie.json` should not be a hard blocker; guest flow works |

## Repeated DX problems found across examples

1. Inconsistent default AGS domains
2. Hidden assumptions about pre-provisioned tools/templates
3. Weak repository-level onboarding
4. Long-running demos without CI/smoke-friendly controls
5. Credential env naming had drift and was normalized during repair
6. Insufficient runtime observability in multi-step demos

## Local evidence

Per-example detailed reports live in:

- `reports/example-runs/`
