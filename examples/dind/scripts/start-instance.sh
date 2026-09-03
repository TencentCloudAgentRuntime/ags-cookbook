#!/usr/bin/env bash
set -Eeuo pipefail

# shellcheck source=common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require_command "${AGR_BIN}"
tool_id="$(read_id AGS_TOOL_ID "${ROOT_DIR}/.tool-id")"

printf 'Creating Sandbox\n'
print_agr_command instance create \
  --tool-id "${tool_id}" \
  --timeout "${AGS_INSTANCE_TIMEOUT}" \
  -o json \
  --jq '.Data.InstanceId'
if ! instance_id="$(
  agr_cli instance create \
    --tool-id "${tool_id}" \
    --timeout "${AGS_INSTANCE_TIMEOUT}" \
    -o json \
    --jq '.Data.InstanceId'
)"; then
  printf '%s\n' "${instance_id}" >&2
  exit 1
fi
if [[ -z "${instance_id}" || "${instance_id}" == "null" ]]; then
  printf 'Instance creation did not return an Instance ID\n' >&2
  exit 1
fi
printf '%s\n' "${instance_id}" > "${ROOT_DIR}/.instance-id"
printf 'Instance ID: %s\n' "${instance_id}"

deadline=$((SECONDS + 360))
last_state=""
printf 'Waiting for the Sandbox to enter RUNNING state\n'
print_agr_command instance get "${instance_id}" -o json --jq '.Data.Status'
while :; do
  if ! instance_state="$(agr_cli instance get "${instance_id}" -o json --jq '.Data.Status' 2>/dev/null | tr -d '"[:space:]')"; then
    instance_state="temporarily-unavailable"
  fi
  if [[ "${instance_state}" != "${last_state}" ]]; then
    printf 'Instance status: %s\n' "${instance_state}"
    last_state="${instance_state}"
  fi
  case "${instance_state}" in
    RUNNING|running)
      break
      ;;
    FAILED|failed|STOPPED|stopped|STOP_FAILED|stop_failed)
      printf 'Instance entered terminal state: %s\n' "${instance_state}" >&2
      exit 1
      ;;
  esac
  (( SECONDS < deadline )) || {
    printf 'Instance did not become RUNNING within 360 seconds; last state: %s\n' "${instance_state}" >&2
    exit 1
  }
  sleep 3
done

readiness_command='test "$(id -u)" = 0 && test "${ENVD_DISTRIBUTION:-}" = 0.5.14-oci && test "$PWD" = /workspace && docker info >/dev/null 2>&1 && docker compose version >/dev/null 2>&1'
printf 'Waiting for envd and the inner Docker daemon\n'
print_agr_command instance exec "${instance_id}" \
  --user "${AGS_EXEC_USER}" -- sh -lc "${readiness_command}"
exec_deadline=$((SECONDS + 60))
until agr_cli instance exec "${instance_id}" --user "${AGS_EXEC_USER}" -- \
  sh -lc "${readiness_command}" >/dev/null 2>&1; do
  (( SECONDS < exec_deadline )) || {
    printf 'envd data plane did not become ready within 60 seconds\n' >&2
    exit 1
  }
  sleep 3
done

printf 'Running Sandbox diagnostics through envd\n'
print_agr_command instance exec "${instance_id}" \
  --user "${AGS_EXEC_USER}" --stream -- bash -lc '<diagnostic commands shown below>'
agr_cli instance exec "${instance_id}" \
  --user "${AGS_EXEC_USER}" \
  --stream \
  -- \
  bash -lc '
    set -e

    print_remote_command() {
      if [[ -z "${NO_COLOR:-}" ]]; then
        printf "\n\033[1;36m$ %s\033[0m\n" "$*"
      else
        printf "\n$ %s\n" "$*"
      fi
    }

    print_remote_command id
    id

    print_remote_command pwd
    pwd

    print_remote_command "envd -version"
    envd -version

    print_remote_command "docker version --format ..."
    docker version --format "Docker Engine client: {{.Client.Version}}\nDocker Engine server: {{.Server.Version}}"

    print_remote_command "docker compose version"
    docker compose version

    print_remote_command "docker info --format ..."
    docker info --format "Storage driver: {{.Driver}}\nDocker root dir: {{.DockerRootDir}}\nCgroup version: {{.CgroupVersion}}" 2>/dev/null

    print_remote_command "findmnt -T /mnt"
    findmnt -T /mnt -o SOURCE,FSTYPE,TARGET

    print_remote_command "findmnt -T /var/lib/docker"
    findmnt -T /var/lib/docker -o SOURCE,FSTYPE,TARGET

    print_remote_command "df -h /mnt /var/lib/docker /var/lib/containerd"
    df -h /mnt /var/lib/docker /var/lib/containerd
  '

printf 'DinD sandbox is ready. Saved to %s\n' "${ROOT_DIR}/.instance-id"
