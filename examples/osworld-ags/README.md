# Run OSWorld on AGS

This example lets you run the public [OSWorld](https://github.com/xlang-ai/OSWorld) project on AGS (Agent Sandbox) using the overlay published in this cookbook.

It works by copying a small overlay into a local OSWorld checkout. The overlay adds the `ags` provider and replaces a few upstream files that must change for AGS to work reliably.

## What You Get

- `provider_name=ags` support in OSWorld
- local HTTP/WebSocket proxying for AGS sandbox access
- noVNC support for remote desktop viewing

## Before You Start

You need:

- `uv` (used to manage an isolated Python 3.12.12 environment)
- `git`
- an AGS API key
- an OSWorld-compatible AGS sandbox template with `/bin/bash`, `/usr/bin/socat`,
  `python3`, and `sudo`
- an LLM API key for the model you plan to run

## Install

### 1. Enter this example directory

```bash
cd /path/to/ags-cookbook/examples/osworld-ags
```

### 2. Clone OSWorld into `./osworld`

```bash
make clone
```

This checks out OSWorld commit
[`84aee655c2afb6b77ecf39884432615ba345c031`](https://github.com/xlang-ai/OSWorld/commit/84aee655c2afb6b77ecf39884432615ba345c031).
It also initializes the upstream `agp_client` submodule used by OSWorld's locked
project environment.
`make setup` verifies the checkout before installing dependencies.

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
AGS_SUDO_PASSWORD=password
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_BASE_URL=https://api.openai.com/v1
```

`AGS_SUDO_PASSWORD` must match the sudo password of the sandbox user. The
standard OSWorld image uses `password`.

### 5. Install dependencies in an isolated uv environment

```bash
make setup
```

This creates `osworld/.venv` with `uv`, installs Python 3.12.12 if needed, and
installs OSWorld from the upstream `uv.lock` plus the AGS-only dependencies in
`requirements-ags.lock`.

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

For setup-only batch validation without calling an LLM API, set
`OSWORLD_MOCK_LLM_DONE=1`. The mock agent returns `DONE` immediately after each
task setup finishes.

## What The Overlay Changes

New files added to OSWorld:

- `desktop_env/providers/ags/__init__.py`
- `desktop_env/providers/ags/config.py`
- `desktop_env/providers/ags/cdp_proxy.py`
- `desktop_env/providers/ags/manager.py`
- `desktop_env/providers/ags/provider.py`
- `desktop_env/providers/ags/sandbox_setup.py`
- `desktop_env/providers/ags/socat_wrapper.sh`
- `requirements-ags.lock`
- `run_multienv.py`

Existing OSWorld files replaced by the overlay:

- `desktop_env/desktop_env.py`
- `desktop_env/providers/__init__.py`

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
