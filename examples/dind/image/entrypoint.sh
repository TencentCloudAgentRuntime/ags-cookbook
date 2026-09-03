#!/usr/bin/env bash
set -Eeuo pipefail

log() {
  printf '[ags-dind] %s\n' "$*"
}

fatal() {
  log "ERROR: $*"
  exit 1
}

is_mountpoint() {
  mountpoint -q "$1"
}

bind_to_data_disk() {
  local source="$1"
  local target="$2"

  mkdir -p "${source}" "${target}"
  # docker:dind declares /var/lib/docker as a VOLUME. The outer runtime can
  # therefore mount an anonymous volume there before this script starts.
  if [[ "$(stat -Lc '%d:%i' "${source}")" != "$(stat -Lc '%d:%i' "${target}")" ]]; then
    mount --bind "${source}" "${target}"
  fi
}

prepare_devices_cgroup() {
  if [[ -f /sys/fs/cgroup/cgroup.controllers ]]; then
    log "cgroup v2 detected"
    return
  fi

  mkdir -p /sys/fs/cgroup/devices
  if ! is_mountpoint /sys/fs/cgroup/devices; then
    log "mounting the cgroup v1 devices controller"
    mount -t cgroup -o devices cgroup /sys/fs/cgroup/devices
  fi
}

prepare_external_storage() {
  local mount_point="${DIND_MOUNT_POINT}"
  local block_device="${DIND_BLOCK_DEVICE}"
  local state_dir="${DIND_STATE_DIR}"

  mkdir -p "${mount_point}"
  if is_mountpoint "${mount_point}"; then
    log "using storage already mounted at ${mount_point}"
  elif [[ -b "${block_device}" ]]; then
    log "mounting ${block_device} at ${mount_point}"
    mount "${block_device}" "${mount_point}"
  elif [[ "${DIND_REQUIRE_EXTERNAL_STORAGE}" == "1" ]]; then
    fatal "${mount_point} is not mounted and ${block_device} is unavailable"
  else
    log "WARNING: using the outer container filesystem"
    state_dir="/var/lib/ags-dind"
  fi

  # Keep inner writable layers off the outer container's overlay filesystem.
  bind_to_data_disk "${state_dir}/containerd" /var/lib/containerd
  bind_to_data_disk "${state_dir}/docker" /var/lib/docker

  log "Docker and containerd state are backed by ${state_dir}"
}

wait_for_docker() {
  local deadline=$((SECONDS + DIND_READY_TIMEOUT_SECONDS))
  until docker info >/dev/null 2>&1; do
    if ! kill -0 "${dockerd_pid}" 2>/dev/null; then
      wait "${dockerd_pid}" || true
      fatal "dockerd exited before becoming ready"
    fi
    if (( SECONDS >= deadline )); then
      fatal "dockerd was not ready within ${DIND_READY_TIMEOUT_SECONDS}s"
    fi
    sleep 1
  done
}

wait_for_envd() {
  local deadline=$((SECONDS + DIND_READY_TIMEOUT_SECONDS))
  until wget -q -O /dev/null "http://127.0.0.1:${ENVD_PORT}/health"; do
    if ! kill -0 "${envd_pid}" 2>/dev/null; then
      wait "${envd_pid}" || true
      fatal "envd exited before becoming ready"
    fi
    if (( SECONDS >= deadline )); then
      fatal "envd was not ready within ${DIND_READY_TIMEOUT_SECONDS}s"
    fi
    sleep 1
  done
}

shutdown_children() {
  local pid
  for pid in "${envd_pid:-}" "${dockerd_pid:-}"; do
    if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
      kill -TERM "${pid}" 2>/dev/null || true
    fi
  done

  local deadline=$((SECONDS + 20))
  while (( SECONDS < deadline )); do
    if ! kill -0 "${envd_pid:-0}" 2>/dev/null \
      && ! kill -0 "${dockerd_pid:-0}" 2>/dev/null; then
      break
    fi
    sleep 1
  done

  for pid in "${envd_pid:-}" "${dockerd_pid:-}"; do
    if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
      kill -KILL "${pid}" 2>/dev/null || true
    fi
    if [[ -n "${pid}" ]]; then
      wait "${pid}" 2>/dev/null || true
    fi
  done
}

on_signal() {
  log "received termination signal"
  shutdown_children
  exit 0
}

if [[ "$(id -u)" != "0" ]]; then
  fatal "the AGS DinD image must run as root"
fi

trap on_signal INT TERM HUP

prepare_devices_cgroup
prepare_external_storage
rm -f /var/run/docker.sock

log "starting dockerd"
/usr/local/bin/dockerd-entrypoint.sh \
  dockerd \
  --host="${DOCKER_HOST}" \
  --data-root=/var/lib/docker \
  "$@" &
dockerd_pid=$!

wait_for_docker
log "dockerd is ready: driver=$(docker info --format '{{.Driver}}')"

log "starting envd on port ${ENVD_PORT}"
/usr/bin/envd -port "${ENVD_PORT}" &
envd_pid=$!
wait_for_envd
log "envd is ready"

set +e
wait -n "${dockerd_pid}" "${envd_pid}"
exit_status=$?
set -e

log "a managed process exited with status ${exit_status}"
shutdown_children
exit "${exit_status}"
