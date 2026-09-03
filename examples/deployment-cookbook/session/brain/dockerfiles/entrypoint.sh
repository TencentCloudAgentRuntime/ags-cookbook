#!/bin/sh
set -eu

: "${AGR_REGION:?AGR_REGION is required}"
: "${AGR_DOMAIN:?AGR_DOMAIN is required}"

profile_modules="${DSH_HOME:-/root/.dsh}/profiles/web/node_modules/@tencentcloud"
mkdir -p "$profile_modules"
ln -sfn \
  /usr/local/lib/node_modules/@tencentcloud/ags-dsh-session-persistence \
  "$profile_modules/ags-dsh-session-persistence"

exec node --expose-internals \
  /usr/local/lib/node_modules/@deepseek-ai/dsh/lib/bin.js \
  web \
  --patch /opt/dsh/agent-runtime-session.cordis.yml \
  --host 0.0.0.0 \
  --port 3080 \
  --trusted-host "*.${AGR_REGION}.agents.${AGR_DOMAIN}" \
  --trusted-host "*.${AGR_REGION}.internal.${AGR_DOMAIN}" \
  --allow-remote-management \
  --no-open
