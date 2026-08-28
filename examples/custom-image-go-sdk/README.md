# custom-image-go-sdk-cookbook

A minimal Go demo that shows how to start an AGS instance with custom runtime configuration and then connect through the data plane.

## Prerequisites

- Go
- `TENCENTCLOUD_SECRET_ID`
- `TENCENTCLOUD_SECRET_KEY`
- Optional `TENCENTCLOUD_REGION` (defaults to `ap-guangzhou`)
- `AGS_TOOL_NAME` for an available custom or fallback tool in your AGS account

## Local commands

```bash
make setup
make run
```

## Important environment variables

- `TENCENTCLOUD_SECRET_ID` / `TENCENTCLOUD_SECRET_KEY`
- `TENCENTCLOUD_REGION`
- `AGS_TOOL_NAME`
- `AGS_RUNTIME_IMAGE` and related `AGS_CUSTOM_*` variables when overriding the default runtime image / command / probe settings

## Expected result

A successful run should:

- call the AGS control plane to start a sandbox instance
- optionally apply custom image/runtime configuration
- connect through the AGS Go SDK data plane
- execute remote code
- stop the instance during cleanup

## Common failure hints

- If the configured custom tool is unhealthy, retry with a known-good AGS tool and verify the custom image settings separately
- If the control plane rejects credentials, re-check `TENCENTCLOUD_SECRET_ID` / `TENCENTCLOUD_SECRET_KEY`
