# Example Run Report: osworld-ags

- Status: fixed-pass
- Started: 2026-03-21T03:12:00+08:00
- Directory: `examples/osworld-ags`

## Commands Planned

```bash
git clone https://github.com/xlang-ai/OSWorld.git osworld
cp -R overlay/OSWorld/. osworld/
uv python install 3.10
uv venv --python 3.10 .venv
uv pip install -r requirements.txt
python quickstart.py --provider_name ags
```

## Findings

- Repository prep and dependency installation completed successfully, though the dependency set is extremely heavy.
- First quickstart attempt failed with:
  - `Sandbox tool osworld not found`
- This proved the repository/documented default `AGS_TEMPLATE=osworld` is stale or environment-specific.
- I queried the real AGS tool list for the current account and found an available OSWorld tool:
  - `goops-gogogo` (type `osworld`)
- After updating `.env` to `AGS_TEMPLATE=goops-gogogo`, quickstart succeeded.
- Successful run verified:
  - AGS sandbox creation
  - local proxy creation for server/VNC/VLC/CDP
  - OSWorld environment startup
  - action execution
  - environment cleanup

## Fixes Attempted

- Installed Python 3.10 via `uv`, as required by the example.
- Queried AGS control-plane tool list to find a real available OSWorld template.
- Retried with:

```bash
AGS_TEMPLATE=goops-gogogo
python quickstart.py --provider_name ags
```

## Final Outcome

- Exit status: 0
- Result: fixed-pass

## Logs

- First failed attempt: reports/example-runs/osworld-ags.log
- Successful retry: reports/example-runs/osworld-ags.retry.log
