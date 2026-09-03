#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -f "${ROOT_DIR}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT_DIR}/.env"
  set +a
fi

AGR_BIN="${AGR_BIN:-agr}"
AGS_REGION="${AGS_REGION:-ap-hongkong}"
AGS_EXEC_USER="${AGS_EXEC_USER:-root}"
AGS_INSTANCE_TIMEOUT="${AGS_INSTANCE_TIMEOUT:-90m}"

AGR_GLOBAL_ARGS=(--region "${AGS_REGION}" --non-interactive)
if [[ -n "${AGR_CONFIG:-}" ]]; then
  AGR_GLOBAL_ARGS+=(--config "${AGR_CONFIG}")
fi
if [[ -n "${AGS_CLOUD_ENDPOINT:-}" ]]; then
  AGR_GLOBAL_ARGS+=(--cloud-endpoint "${AGS_CLOUD_ENDPOINT}")
fi
if [[ -n "${AGS_DATA_DOMAIN:-}" ]]; then
  AGR_GLOBAL_ARGS+=(--domain "${AGS_DATA_DOMAIN}")
fi
if [[ -n "${TENCENTCLOUD_SECRET_ID:-}" && -n "${TENCENTCLOUD_SECRET_KEY:-}" ]]; then
  AGR_GLOBAL_ARGS+=(
    --secret-id "${TENCENTCLOUD_SECRET_ID}"
    --secret-key "${TENCENTCLOUD_SECRET_KEY}"
  )
fi
if [[ -n "${TENCENTCLOUD_TOKEN:-}" ]]; then
  AGR_GLOBAL_ARGS+=(--token "${TENCENTCLOUD_TOKEN}")
fi

agr_cli() {
  "${AGR_BIN}" "${AGR_GLOBAL_ARGS[@]}" "$@"
}

print_command() {
  local argument
  if [[ -z "${NO_COLOR:-}" ]]; then
    printf '\033[1;36m' >&2
  fi
  printf '$' >&2
  for argument in "$@"; do
    if [[ "${argument}" == *$'\n'* ]]; then
      argument='<multiline argument>'
    elif (( ${#argument} > 180 )); then
      argument="${argument:0:160}..."
    fi
    printf ' %q' "${argument}" >&2
  done
  if [[ -z "${NO_COLOR:-}" ]]; then
    printf '\033[0m' >&2
  fi
  printf '\n' >&2
}

print_command_line() {
  if [[ -z "${NO_COLOR:-}" ]]; then
    printf '\033[1;36m' >&2
  fi
  printf '%s' "$1" >&2
  if [[ -z "${NO_COLOR:-}" ]]; then
    printf '\033[0m' >&2
  fi
  printf '\n' >&2
}

# Print the useful, non-secret portion of an agr invocation. Authentication is
# supplied by agr_cli from .env, but credentials must never be copied to logs.
print_agr_command() {
  print_command "${AGR_BIN}" --region "${AGS_REGION}" --non-interactive "$@"
}

run_command() {
  print_command "$@"
  "$@"
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    printf 'required command is missing: %s\n' "$1" >&2
    exit 1
  }
}

require_agr_storage_support() {
  local version
  local major
  local minor
  local patch
  version="$("${AGR_BIN}" version | awk 'NR == 1 {print $3}')"
  if [[ "${version}" =~ ^v([0-9]+)\.([0-9]+)\.([0-9]+) ]]; then
    major="${BASH_REMATCH[1]}"
    minor="${BASH_REMATCH[2]}"
    patch="${BASH_REMATCH[3]}"
    if (( major == 0 && (minor < 6 || (minor == 6 && patch < 6)) )); then
      printf 'agr >= v0.6.6 is required; found %s\n' "${version}" >&2
      exit 1
    fi
  fi
}

read_id() {
  local environment_name="$1"
  local state_file="$2"
  local value="${!environment_name:-}"
  if [[ -z "${value}" && -f "${state_file}" ]]; then
    value="$(tr -d '[:space:]' < "${state_file}")"
  fi
  [[ -n "${value}" ]] || {
    printf '%s is unset and %s does not exist\n' "${environment_name}" "${state_file}" >&2
    exit 1
  }
  printf '%s' "${value}"
}
