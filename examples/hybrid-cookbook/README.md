# hybrid-cookbook

A minimal cookbook project:
- **Control plane**: latest `tencentcloud-sdk-go`
- **Data plane**: `ags-go-sdk`

## Project Structure
- `main.go` - single entrypoint
- `.env` - unified config
- `.env.example` - config template
- `Agents.md` - quick run notes

## Setup
1. Copy template:
   - `cp .env.example .env`
2. Fill credentials in `.env`.

## Run
```bash
go mod tidy
go run .
```

## Flow
1. Start sbx (control plane)
2. Connect and run code (data plane)
3. List sbx (control plane)
4. Stop sbx (defer cleanup)
