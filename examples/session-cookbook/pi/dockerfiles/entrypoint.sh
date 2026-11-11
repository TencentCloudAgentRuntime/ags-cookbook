#!/bin/sh
set -eu

: "${AGR_REGION:?AGR_REGION is required}"
: "${PI_SESSION_ID:?PI_SESSION_ID is required}"

session_dir="${PI_SESSION_DIR:-/var/pi/sessions}"
export PI_SESSION_DIR="$session_dir"

# Writes models.json and restores the session from Agent Runtime Session.
node /opt/pi/extension/prepare.mjs

# --session-id opens the restored session file, or creates the session when the
# cloud has none. The prompt arrives later over stdin, as pi RPC commands.
exec pi --mode rpc \
  --offline \
  --session-dir "$session_dir" \
  --session-id "$PI_SESSION_ID" \
  --extension /opt/pi/extension/index.js \
  --provider custom \
  --model "$LLM_MODEL" \
  --no-skills --no-prompt-templates --no-themes --no-context-files
