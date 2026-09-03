#!/usr/bin/env bash
set -Eeuo pipefail

# shellcheck source=common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require_command "${AGR_BIN}"

instance_id="$(read_id AGS_INSTANCE_ID "${ROOT_DIR}/.instance-id")"
run_suffix="$(date +%Y%m%d%H%M%S)-$$"
remote_script="/workspace/run-harbor-oracle-${run_suffix}.sh"
remote_script_uploaded=0

# 本地脚本只负责通过 envd 上传和启动 runner；Harbor、TB3 和构建产物均留在 Sandbox 内。
cleanup_remote() {
  if (( remote_script_uploaded )); then
    printf 'Removing the temporary Sandbox script\n'
    print_agr_command instance exec "${instance_id}" --user root -- \
      rm -f "${remote_script}"
    agr_cli instance exec "${instance_id}" --user root -- \
      rm -f "${remote_script}" >/dev/null 2>&1 || true
  fi
}
trap cleanup_remote EXIT

printf 'Uploading the Harbor Oracle runner\n'
print_agr_command instance file upload \
  "${instance_id}" \
  "${ROOT_DIR}/scripts/run-harbor-oracle-in-sandbox.sh" \
  "${remote_script}" \
  --user root
agr_cli instance file upload \
  "${instance_id}" \
  "${ROOT_DIR}/scripts/run-harbor-oracle-in-sandbox.sh" \
  "${remote_script}" \
  --user root
remote_script_uploaded=1

printf 'Running the Terminal-Bench task with Harbor Oracle in the Sandbox\n'
print_agr_command instance exec "${instance_id}" \
  --user root --stream -- bash "${remote_script}"
agr_cli instance exec "${instance_id}" \
  --user root \
  --stream \
  -- \
  bash "${remote_script}"
