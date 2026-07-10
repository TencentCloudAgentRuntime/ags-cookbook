FROM nousresearch/hermes-agent:v2026.4.23

USER root

COPY --from=ccr.ccs.tencentyun.com/ags-image/envd:latest --chmod=755 /usr/bin/envd /usr/bin/envd

RUN cat > /entrypoint.sh <<'EOF'
#!/bin/bash
set -e

mkdir -p /logs

# 1. Start envd
/usr/bin/envd >/logs/envd.log 2>&1 &

# 2. Initialize Hermes
HERMES_HOME="${HERMES_HOME:-/opt/data}"
INSTALL_DIR="/opt/hermes"

source "${INSTALL_DIR}/.venv/bin/activate"

mkdir -p "$HERMES_HOME"/{cron,sessions,logs,hooks,memories,skills,skins,plans,workspace,home}

if [ ! -f "$HERMES_HOME/.env" ]; then
    cp "$INSTALL_DIR/.env.example" "$HERMES_HOME/.env"
fi

if [ ! -f "$HERMES_HOME/config.yaml" ]; then
    cp "$INSTALL_DIR/cli-config.yaml.example" "$HERMES_HOME/config.yaml"
fi

if [ ! -f "$HERMES_HOME/SOUL.md" ]; then
    cp "$INSTALL_DIR/docker/SOUL.md" "$HERMES_HOME/SOUL.md"
fi

if [ -d "$INSTALL_DIR/skills" ]; then
    python3 "$INSTALL_DIR/tools/skills_sync.py" >/logs/skills_sync.log 2>&1
fi

# 3. Start dashboard in background
hermes dashboard --host 0.0.0.0 --insecure --no-open >/logs/dashboard.log 2>&1 &

# 4. Start gateway as main process
exec hermes gateway run --accept-hooks >/logs/gateway.log 2>&1
EOF

RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
