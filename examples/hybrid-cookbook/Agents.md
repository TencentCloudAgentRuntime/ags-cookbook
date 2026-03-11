# Agents

## Goal
Run a hybrid AGS cookbook with the simplest possible workflow.

## Quick Start
1. Open `./.env` and fill real credentials.
2. Run: `go mod tidy`
3. Run: `go run .`

## What This Cookbook Does
1. Create AGS sbx via new `tencentcloud-sdk-go` (control plane).
2. Connect sbx via `ags-go-sdk` (data plane).
3. Execute code in sbx.
4. Query sbx list in control plane.
5. Stop sbx in defer cleanup.

## Files
- `main.go`: single entry, minimal flow.
- `.env`: unified runtime config.
- `.env.example`: env template.
- `README.md`: user guide.
