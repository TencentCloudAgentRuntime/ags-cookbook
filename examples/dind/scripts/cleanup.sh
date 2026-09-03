#!/usr/bin/env bash
set -Eeuo pipefail

# shellcheck source=common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require_command "${AGR_BIN}"

instance_id="${AGS_INSTANCE_ID:-}"
if [[ -z "${instance_id}" && -f "${ROOT_DIR}/.instance-id" ]]; then
  instance_id="$(tr -d '[:space:]' < "${ROOT_DIR}/.instance-id")"
fi
if [[ -n "${instance_id}" ]]; then
  print_agr_command instance delete "${instance_id}" --yes --ignore-not-found
  agr_cli instance delete "${instance_id}" --yes --ignore-not-found
  run_command rm -f "${ROOT_DIR}/.instance-id"
else
  printf 'No Sandbox ID found; skipping Sandbox deletion.\n'
fi

tool_id="${AGS_TOOL_ID:-}"
if [[ -z "${tool_id}" && -f "${ROOT_DIR}/.tool-id" ]]; then
  tool_id="$(tr -d '[:space:]' < "${ROOT_DIR}/.tool-id")"
fi
if [[ -n "${tool_id}" ]]; then
  print_agr_command tool delete "${tool_id}" --yes
  agr_cli tool delete "${tool_id}" --yes
  run_command rm -f "${ROOT_DIR}/.tool-id"
else
  printf 'No Tool ID found; skipping Tool deletion.\n'
fi
