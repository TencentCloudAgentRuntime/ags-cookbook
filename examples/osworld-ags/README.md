# Run OSWorld on AGS

This example lets you run the public [OSWorld](https://github.com/xlang-ai/OSWorld) project on AGS (Agent Sandbox) using the overlay published in this cookbook.

It works by copying a small overlay into a local OSWorld checkout. The overlay adds the `ags` provider and replaces a few upstream files that must change for AGS to work reliably.

## What You Get

- `provider_name=ags` support in OSWorld
- local HTTP/WebSocket proxying for AGS sandbox access
- noVNC support for remote desktop viewing

## Before You Start

You need:

- `uv` (used to manage an isolated Python 3.10 environment)
- `git`
- an AGS API key
- an OSWorld-compatible AGS sandbox template
- an LLM API key for the model you plan to run

## Install

### 1. Enter this example directory

```bash
cd /path/to/ags-cookbook/examples/osworld-ags
```

### 2. Clone OSWorld into `./osworld`

```bash
git clone https://github.com/xlang-ai/OSWorld.git osworld
```

### 3. Apply the overlay

```bash
cp -R overlay/OSWorld/. osworld/
```

### 4. Add your environment variables

```bash
cp .env.example osworld/.env
```

At minimum, set:

```bash
E2B_API_KEY=your_api_key_here
E2B_DOMAIN=ap-singapore.tencentags.com
AGS_TEMPLATE=your_osworld_template_id
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_BASE_URL=https://api.openai.com/v1
```

### 5. Install dependencies in an isolated uv environment
Note: currently only supports Python 3.10
```bash
make setup
```

This creates `osworld/.venv` with `uv`, installs Python 3.10 if needed, and installs the overlaid `requirements.txt` into that virtual environment. The overlay adds the AGS dependencies to `requirements.txt`, including `e2b-code-interpreter` and `aiohttp`.

## Run

### Quick check

```bash
make run
```

If this succeeds, the AGS provider is installed correctly.

### Run multienv

```bash
cd osworld
uv run --python .venv/bin/python run_multienv.py --provider_name ags --model gpt-4o --num_envs 2
```

## What The Overlay Changes

New files added to OSWorld:

- `desktop_env/providers/ags/__init__.py`
- `desktop_env/providers/ags/config.py`
- `desktop_env/providers/ags/manager.py`
- `desktop_env/providers/ags/provider.py`

Existing OSWorld files replaced by the overlay:

- `desktop_env/desktop_env.py`
- `desktop_env/providers/__init__.py`
- `desktop_env/controllers/python.py`
- `run_multienv.py`
- `requirements.txt`

## View VNC

After startup, the AGS provider logs the local proxy ports it opened. Open the VNC proxy in your browser:

```bash
http://localhost:<vnc_port>/vnc.html
```

## Notes

- This is not an official upstream OSWorld release.
- The AGS provider is distributed here as a cookbook overlay.
- The overlaid source is derived from OSWorld and remains under Apache-2.0.
- Upstream project: [xlang-ai/OSWorld](https://github.com/xlang-ai/OSWorld)
