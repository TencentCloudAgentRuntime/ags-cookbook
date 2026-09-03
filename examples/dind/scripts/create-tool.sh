#!/usr/bin/env bash
set -Eeuo pipefail

# shellcheck source=common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require_command "${AGR_BIN}"
require_agr_storage_support

tool_name_prefix="${AGS_TOOL_NAME:-ags-dind-v1-0-0}"
tool_name="${tool_name_prefix}-$(date +%Y%m%d%H%M%S)-$$"
config_file="${ROOT_DIR}/tool-custom-configuration.hk.json"

printf 'Creating Tool %s in %s\n' "${tool_name}" "${AGS_REGION}"
print_agr_command tool create \
  --tool-name "${tool_name}" \
  --tool-type custom \
  --description "Self-starting Docker-in-Docker sandbox with envd" \
  --default-timeout 2h \
  --network-configuration '{"NetworkMode":"PUBLIC"}' \
  --custom-configuration "@${config_file}" \
  --wait \
  -o json \
  --jq '.Data.ToolId'
if ! tool_id="$(
  agr_cli tool create \
    --tool-name "${tool_name}" \
    --tool-type custom \
    --description "Self-starting Docker-in-Docker sandbox with envd" \
    --default-timeout 2h \
    --network-configuration '{"NetworkMode":"PUBLIC"}' \
    --custom-configuration "@${config_file}" \
    --wait \
    -o json \
    --jq '.Data.ToolId'
)"; then
  printf '%s\n' "${tool_id}" >&2
  exit 1
fi

printf '%s\n' "${tool_id}" > "${ROOT_DIR}/.tool-id"
printf 'Tool ID: %s\n' "${tool_id}"
printf 'Saved to %s\n' "${ROOT_DIR}/.tool-id"
