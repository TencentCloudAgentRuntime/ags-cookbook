#!/bin/sh
set -eu

: "${AGR_REGION:?AGR_REGION is required}"

patch_file=/opt/dsh/agent-runtime-session.cordis.yml

# The sample model entries live in the same patch. Deployments that keep their own
# model configuration remove them, and then need no LLM_* variables.
if grep -q 'llm-pi-ai' "$patch_file"; then
  missing=
  for name in LLM_BASE_URL LLM_MODEL LLM_API_KEY; do
    eval "value=\${$name:-}"
    [ -n "$(printf '%s' "$value" | tr -d '[:space:]')" ] || missing="$missing $name"
  done
  if [ -n "$missing" ]; then
    echo "entrypoint: set${missing}; see .env.example. If this deployment keeps its own model configuration, remove the llm-pi-ai and agent-default-model entries from $patch_file instead." >&2
    exit 1
  fi
fi

profile_modules="${DSH_HOME:-/root/.dsh}/profiles/web/node_modules/@tencentcloud"
mkdir -p "$profile_modules"
ln -sfn \
  /usr/local/lib/node_modules/@tencentcloud/ags-dsh-session-persistence \
  "$profile_modules/ags-dsh-session-persistence"

# Official DSH binds one concrete address, never 0.0.0.0. Inside a container that is
# the container's own address, so a published port reaches it.
host="${DSH_HOST:-$(hostname -i | awk '{print $1}')}"

set -- --profile web \
  --patch "$patch_file" \
  --host "$host" \
  --port 3080 \
  --no-open
# The printed sign-in URL uses this root instead of the container address.
if [ -n "${DSH_PUBLIC_URL:-}" ]; then
  set -- "$@" --public-url "$DSH_PUBLIC_URL"
fi

exec dsh "$@"
