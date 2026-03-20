# hybrid-cookbook

A minimal Go example for the AGS hybrid workflow: create a sandbox through the Tencent Cloud control plane, connect through the AGS data plane, run code, and clean up on exit.

## Prerequisites

- Go
- `TENCENTCLOUD_SECRET_ID`
- `TENCENTCLOUD_SECRET_KEY`
- Optional `TENCENTCLOUD_REGION` (defaults to `ap-guangzhou` in this example)
- An available AGS tool name if you override the default in `.env`

## Local commands

```bash
make setup
make run
```

## Expected result

A successful run should:

- start a sandbox instance
- connect and execute code through the data plane
- print sandbox information
- stop the sandbox during cleanup

## Common failure hints

- If the control plane rejects the request, verify `TENCENTCLOUD_SECRET_ID` / `TENCENTCLOUD_SECRET_KEY`
- If tool startup fails, check that the configured AGS tool exists in your account and region
