# Run Windows Agent Arena on AGS

This example runs the public [Windows Agent Arena](https://github.com/microsoft/WindowsAgentArena) project on AGS (Agent Sandbox) with a small overlay.

The overlay keeps the native WAA runner, tasks, Navi agent, and evaluator in place. It only adds the AGS sandbox launcher and replaces the WAA files that need to talk to a remote AGS Windows sandbox instead of a local Docker/QEMU VM.

Note that the WAA server running inside the AGS sandbox is built on top of **Tencent Cloud Windows Server 2025 (64-bit, English edition)**. All in-sandbox behavior (locale, default fonts, installed components, PowerShell / .NET versions, activation, etc.) matches that base image. Windows Server 2025 is a **server SKU**, so if your agent / task relies on features that are only available on Windows 10 / Windows 11 client SKUs (for example some UWP / Microsoft Store apps), those components may be absent or behave differently.

## What You Need

- `git`
- `uv`
- an AGS API key
- a WAA-compatible AGS sandbox template
- an OpenAI-compatible model endpoint

## Install

### 1. Enter this example

```bash
cd /path/to/ags-cookbook/examples/waa-ags
```

### 2. Clone WindowsAgentArena

```bash
git clone https://github.com/microsoft/WindowsAgentArena.git waa
```

### 3. Apply the overlay

```bash
cp -R overlay/WindowsAgentArena/. waa/
```

### 4. Add your environment variables

```bash
cp .env.example .env
```

At minimum, set:

```bash
E2B_API_KEY=your_api_key_here
E2B_DOMAIN=ap-guangzhou.tencentags.com
AGS_TEMPLATE=your_waa_tool_id
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_BASE_URL=https://api.openai.com/v1
```

Keep this `.env` file private.

### 5. Install dependencies

WAA currently requires Python 3.10.

```bash
make setup
```

This creates `waa/src/win-arena-container/client/.venv`, installs the overlaid `requirements.txt`, and installs Playwright Chromium.

## Run

```bash
make run
```

By default this runs `evaluation_examples_windows/test_small.json` with `gpt-4o`, `som_origin=a11y`, and `a11y_backend=uia`.

Use custom arguments when needed:

```bash
make run MODEL=gpt-4o TEST_META=evaluation_examples_windows/test_small.json MAX_STEPS=15
```

Or run WAA directly:

```bash
cd waa/src/win-arena-container/client
.venv/bin/python run_ags.py \
  --model gpt-4o \
  --test_all_meta_path evaluation_examples_windows/test_small.json \
  --som_origin a11y \
  --a11y_backend uia \
  --max_steps 15
```

## Overlay Files

New file added to WindowsAgentArena:

- `src/win-arena-container/client/run_ags.py`

Existing WindowsAgentArena files replaced by the overlay:

- `src/win-arena-container/client/desktop_env/envs/desktop_env.py`
- `src/win-arena-container/client/desktop_env/controllers/setup.py`
- `src/win-arena-container/client/requirements.txt`

## How It Works

`run_ags.py` will:

1. load `examples/waa-ags/.env`
2. create a Windows sandbox through the AGS/E2B-compatible SDK
3. proxy sandbox ports to localhost:
   - `5000`: WAA Windows-side server
   - `9222`: Chrome/Edge CDP
   - `8006`: noVNC
   - `8080`: VLC HTTP
4. set `WAA_AGS_REMOTE=1`
5. start native WAA with `run.py --emulator_ip 127.0.0.1 ...`
6. clean up local proxies and kill the AGS sandbox on exit

After startup, noVNC is available at:

```bash
http://127.0.0.1:8006
```

## Storage Notes

- The WAA sandbox **does not** support mounting Tencent Cloud storage services such as COS, CFS, or CBS. There is no mount point for these services inside the sandbox, so please do not rely on filesystem mounts to read/write them.
- If your agent / task really needs to access external storage (for example COS), the only option is to access it **over the network** from inside the sandbox (via the COS SDK / REST API / CLI tools).
- Choosing which COS endpoint to use from the sandbox:
  - **Same region**: when the sandbox and the COS bucket are in the same region, just use the COS **default endpoint** (like `<BucketName-APPID>.cos.<region>.myqcloud.com`). Requests are automatically routed over the Tencent Cloud internal network, so traffic is counted as internal traffic and there is no public egress traffic fee (request-count fees still apply).
  - **Cross region**: when the sandbox and the COS bucket are in different regions, you can still stay on the internal network by using the COS **internal global acceleration endpoint** (like `<BucketName-APPID>.cos-internal.accelerate.tencentcos.cn`). If you use the regular **global acceleration endpoint** (`<BucketName-APPID>.cos.accelerate.myqcloud.com`) or the default endpoint of a different region, the request will go over the public internet and incur public egress traffic fees.
- Therefore, in cross-region scenarios where cost or network path matters, prefer the **internal global acceleration endpoint**.
- For the full endpoint list, endpoint rules, and how to enable global acceleration, please refer to the official Tencent Cloud documentation: [COS Regions and Access Domains](https://cloud.tencent.com/document/product/436/6224).

## Notes

- This is not an official upstream WindowsAgentArena release.
- The overlay source is derived from WindowsAgentArena and remains under the MIT License.
- Upstream project: [microsoft/WindowsAgentArena](https://github.com/microsoft/WindowsAgentArena)
