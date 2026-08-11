#!/usr/bin/env bash
# End-to-end check of the OCI User / Workdir defaults on AGS.
#
# Prepares a temporary Tool with the envd Image Volume mounted into a business
# fixture, starts an Instance, runs the assertions through the E2B Python SDK, then
# deletes everything it created. `agr` is used only for the control plane; every
# behavioral assertion lives in validate_user_workdir.py.
#
# Credentials are read from the environment (or .env) and never printed.
#
# Required:
#   TENCENTCLOUD_SECRET_ID / TENCENTCLOUD_SECRET_KEY  control plane
#   AGS_API_KEY / E2B_DOMAIN                          data plane
#   ENVD_VOLUME_IMAGE                                 envd Image Volume reference
#   ENVD_VOLUME_IMAGE_DIGEST                          expected manifest digest
#   FIXTURE_A_IMAGE                                   business fixture A
#   FIXTURE_B_IMAGE                                   numeric-UID business fixture B
#   AGS_ROLE_ARN                                      CAM role that can read the registry
#
# Optional:
#   TENCENTCLOUD_REGION        default ap-guangzhou
#   ENVD_VOLUME_MOUNT_PATH     default /opt/envd
#   AGS_INSTANCE_TIMEOUT       default 20m (the spec caps this at 30m)
#   ENVD_IMAGE_REGISTRY_TYPE   default personal
#   AGS_ENVD_VERSION_METADATA  default 0.4.0
set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${script_dir}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${script_dir}/.env"
  set +a
fi

: "${TENCENTCLOUD_SECRET_ID:?TENCENTCLOUD_SECRET_ID is required}"
: "${TENCENTCLOUD_SECRET_KEY:?TENCENTCLOUD_SECRET_KEY is required}"
: "${AGS_API_KEY:=${E2B_API_KEY:-}}"
: "${AGS_API_KEY:?AGS_API_KEY is required}"
: "${E2B_DOMAIN:?E2B_DOMAIN is required}"
: "${ENVD_VOLUME_IMAGE:?ENVD_VOLUME_IMAGE is required}"
: "${ENVD_VOLUME_IMAGE_DIGEST:?ENVD_VOLUME_IMAGE_DIGEST is required}"
: "${FIXTURE_A_IMAGE:?FIXTURE_A_IMAGE is required}"
: "${FIXTURE_B_IMAGE:?FIXTURE_B_IMAGE is required}"
: "${AGS_ROLE_ARN:?AGS_ROLE_ARN is required}"
: "${ENVD_EXPECTED_COMMIT:?ENVD_EXPECTED_COMMIT is required}"

REGION="${TENCENTCLOUD_REGION:-ap-guangzhou}"
MOUNT_PATH="${ENVD_VOLUME_MOUNT_PATH:-/opt/envd}"
INSTANCE_TIMEOUT="${AGS_INSTANCE_TIMEOUT:-20m}"
REGISTRY_TYPE="${ENVD_IMAGE_REGISTRY_TYPE:-personal}"
ENVD_VERSION_METADATA="${AGS_ENVD_VERSION_METADATA:-0.4.0}"

# AGS issues ark_ keys. Its E2B-compatible data plane accepts the same secret
# with an e2b_ prefix. SDK 2.35 still rejects AGS's non-hex suffix locally, so
# use its supported validation opt-out; the backend continues to authenticate
# the normalized key. The envd version gate is never patched.
case "${AGS_API_KEY}" in
  ark_*) export E2B_API_KEY="e2b_${AGS_API_KEY#ark_}" ;;
  e2b_*) export E2B_API_KEY="${AGS_API_KEY}" ;;
  *) echo "AGS_API_KEY must start with ark_ (or already be normalized to e2b_)" >&2; exit 1 ;;
esac
export E2B_VALIDATE_API_KEY=false

# `latest` cannot be pinned to a digest, so the delivery would not be identifiable.
# A reference with no tag at all also resolves to `latest`, and tags are matched
# case-insensitively here because `:LATEST` is just as unpinnable.
envd_volume_tag="${ENVD_VOLUME_IMAGE##*/}"      # strip registry/namespace
case "${envd_volume_tag}" in
  *:*) envd_volume_tag="${envd_volume_tag##*:}" ;;
  *)   envd_volume_tag="latest" ;;              # no tag means latest
esac

if [[ "${envd_volume_tag,,}" == "latest" ]]; then
  echo "ENVD_VOLUME_IMAGE resolves to the 'latest' tag; use a unique immutable tag" >&2
  echo "  the artifact is identified by its manifest digest, which a mutable tag cannot pin" >&2
  exit 1
fi

# The delivery spec caps temporary test instances at 30 minutes. Enforce it rather
# than only documenting it, so a stray .env cannot leave a long-lived sandbox behind.
case "${INSTANCE_TIMEOUT}" in
  *m) timeout_minutes="${INSTANCE_TIMEOUT%m}" ;;
  *h) timeout_minutes=$(( ${INSTANCE_TIMEOUT%h} * 60 )) ;;
  *s) timeout_minutes=$(( ${INSTANCE_TIMEOUT%s} / 60 )) ;;
  *)  echo "AGS_INSTANCE_TIMEOUT must end in s, m, or h (got ${INSTANCE_TIMEOUT})" >&2; exit 1 ;;
esac

if ! [[ "${timeout_minutes}" =~ ^[0-9]+$ ]] || (( timeout_minutes > 30 )) || (( timeout_minutes < 1 )); then
  echo "AGS_INSTANCE_TIMEOUT must be between 1m and 30m (got ${INSTANCE_TIMEOUT})" >&2
  exit 1
fi

command -v agr >/dev/null 2>&1 || { echo "agr is required" >&2; exit 1; }
command -v uv >/dev/null 2>&1 || { echo "uv is required" >&2; exit 1; }

agr_args=(--region "${REGION}" -o json)

# One prefix per run, so cleanup and the leftover check can be scoped exactly.
run_prefix="envd-userworkdir-$(date +%s)-$$"
expected_tool_names=("${run_prefix}-a" "${run_prefix}-b")
created_tools=()
created_instances=()
cleanup_failed=0

cleanup() {
  local exit_code=$?
  set +e

  echo
  echo "== cleaning up ${run_prefix}"

  for instance in "${created_instances[@]:-}"; do
    [[ -n "${instance}" ]] || continue
    printf '   instance %s: ' "${instance:0:12}..."
    if ! agr instance delete "${instance}" "${agr_args[@]}" --ignore-not-found \
      --jq '.Status' 2>/dev/null; then
      echo "delete failed"
      cleanup_failed=1
    fi
  done

  for tool in "${created_tools[@]:-}"; do
    [[ -n "${tool}" ]] || continue
    printf '   tool %s: ' "${tool}"
    if ! agr tool delete "${tool}" "${agr_args[@]}" --jq '.Status' 2>/dev/null; then
      echo "delete failed"
      cleanup_failed=1
    fi
  done

  # Prove the cleanup rather than assume it.
  #
  # Query each exact expected name server-side. An unfiltered first page can miss
  # a leftover in an account with more than 100 Tools, especially if create
  # succeeded remotely but local response parsing failed before its id was saved.
  echo "   leftover check for prefix ${run_prefix}:"

  local expected_name listing
  for expected_name in "${expected_tool_names[@]}"; do
    if ! listing="$(agr tool list --limit 100 \
      --filters "[{\"Name\":\"ToolName\",\"Values\":[\"${expected_name}\"]}]" \
      "${agr_args[@]}" 2>&1)"; then
      echo "     FAIL: could not query Tool ${expected_name}" >&2
      cleanup_failed=1
      continue
    fi

    if ! printf '%s' "${listing}" | EXPECTED_TOOL_NAME="${expected_name}" python3 -c "
import json, sys
import os

payload = json.load(sys.stdin)
if payload.get('Status') != 'succeeded':
    print('     FAIL: tool list failed:', str(payload.get('Failure'))[:160])
    raise SystemExit(1)

items = (payload.get('Data') or {}).get('Items')
if items is None:
    print('     FAIL: unexpected response shape; keys:',
          list((payload.get('Data') or {}).keys()))
    raise SystemExit(1)

expected = os.environ['EXPECTED_TOOL_NAME']
leftover = [t for t in items if t.get('ToolName') == expected]
print(f'     {expected}: {len(leftover)} matching tools')
for tool in leftover:
    print('       LEFTOVER:', tool.get('ToolName'), tool.get('ToolId'))
raise SystemExit(1 if leftover else 0)
"; then
      cleanup_failed=1
    fi
  done

  # Instances are checked too: deleting a Tool does not imply its Instances are
  # gone. An unfiltered `agr instance list` is useless for this: it returns only
  # the first page (20) of every instance in the account, so a leftover from this
  # run would almost certainly not appear. The query is therefore scoped to the
  # Tool ids this run created, which is exactly the set that could leak.
  for tool in "${created_tools[@]:-}"; do
    [[ -n "${tool}" ]] || continue

    local instance_listing
    if ! instance_listing="$(agr instance list --tool-id "${tool}" "${agr_args[@]}" 2>&1)"; then
      echo "     FAIL: could not list instances for ${tool}; verify manually with:" >&2
      echo "       agr instance list --tool-id ${tool} --region ${REGION} -o json" >&2
      cleanup_failed=1
      continue
    fi

    if ! printf '%s' "${instance_listing}" | TOOL_ID="${tool}" python3 -c "
import json, os, sys

payload = json.load(sys.stdin)
tool_id = os.environ['TOOL_ID']

if payload.get('Status') != 'succeeded':
    print(f'     FAIL: instance list for {tool_id} failed:',
          str(payload.get('Failure'))[:160])
    raise SystemExit(1)

data = payload.get('Data') or {}
items = data.get('Items')
if items is None:
    print('     FAIL: unexpected response shape; keys:', list(data.keys()))
    raise SystemExit(1)

terminal = {'STOPPED', 'DELETED', 'TERMINATED'}
live = [i for i in items if i.get('Status') not in terminal]
print(f'     {tool_id}: {len(live)} non-terminal of {len(items)} instances')
for inst in live:
    print('       LIVE:', str(inst.get('InstanceId'))[:14] + '...', inst.get('Status'))
raise SystemExit(1 if live else 0)
"; then
      cleanup_failed=1
    fi
  done

  trap - EXIT
  if (( exit_code != 0 || cleanup_failed != 0 )); then
    exit 1
  fi

  exit 0
}
trap cleanup EXIT

pre_cache() {
  local image="$1"
  local expected_digest="${2:-}"
  echo "== pre-caching ${image}"

  local digest
  digest="$(
    agr pre-cache-image-task create \
      --image "${image}" \
      --image-registry-type "${REGISTRY_TYPE}" \
      "${agr_args[@]}" \
      --jq '.Data.ImageDigest'
  )"

  local status
  for _ in $(seq 1 60); do
    status="$(
      agr pre-cache-image-task get "${digest}" \
        --image "${image}" \
        --image-registry-type "${REGISTRY_TYPE}" \
        "${agr_args[@]}" \
        --jq '.Data.Status'
    )"
    case "${status}" in
      Success)
        echo "   ready, digest ${digest}"
        if [[ -n "${expected_digest}" && "${digest}" != "${expected_digest}" ]]; then
          echo "   pre-cache digest mismatch: expected ${expected_digest}" >&2
          return 1
        fi
        return 0
        ;;
      Failed)  echo "   pre-cache failed for ${image}" >&2; return 1 ;;
    esac
    sleep 5
  done

  echo "   pre-cache did not finish within 300s (last status: ${status})" >&2
  return 1
}

wait_for_tool() {
  local tool_id="$1" status
  for _ in $(seq 1 60); do
    status="$(agr tool get "${tool_id}" "${agr_args[@]}" --jq '.Data.Status')"
    case "${status}" in
      ACTIVE) return 0 ;;
      CREATE_FAILED | FAILED) echo "tool ${tool_id} is ${status}" >&2; return 1 ;;
    esac
    sleep 5
  done
  echo "tool ${tool_id} did not become ACTIVE (last status: ${status})" >&2
  return 1
}

wait_for_instance() {
  local instance_id="$1" status
  for _ in $(seq 1 60); do
    status="$(agr instance get "${instance_id}" "${agr_args[@]}" --jq '.Data.Status')"
    case "${status}" in
      RUNNING) return 0 ;;
      FAILED | STARTING_FAILED | STOP_FAILED | STOPPING_FAILED)
        echo "instance ${instance_id} is ${status}" >&2; return 1 ;;
    esac
    sleep 5
  done
  echo "instance ${instance_id} did not become RUNNING (last status: ${status})" >&2
  return 1
}

run_fixture() {
  local key="$1" image="$2"

  echo
  echo "======== fixture ${key}: ${image}"
  pre_cache "${image}"

  local storage_mounts custom_configuration
  storage_mounts="$(
    python3 -c "
import json, sys
print(json.dumps([{
    'Name': 'envd',
    'MountPath': sys.argv[1],
    'ReadOnly': True,
    'StorageSource': {'Image': {'Reference': sys.argv[2], 'ImageRegistryType': sys.argv[3]}},
}]))
" "${MOUNT_PATH}" "${ENVD_VOLUME_IMAGE}" "${REGISTRY_TYPE}"
  )"

  # The Command points at the mounted envd, so the business image supplies the OCI
  # User and Workdir while the volume supplies only the binary.
  custom_configuration="$(
    python3 -c "
import json, sys
mount, image, registry = sys.argv[1], sys.argv[2], sys.argv[3]
print(json.dumps({
    'Image': image,
    'ImageRegistryType': registry,
    'Command': [mount + '/usr/bin/envd'],
    'Ports': [{'Name': 'envd', 'Port': 49983, 'Protocol': 'TCP'}],
    'Probe': {
        'HttpGet': {'Path': '/health', 'Port': 49983, 'Scheme': 'HTTP'},
        # The control plane caps ReadyTimeoutMs at 30000.
        'ReadyTimeoutMs': 30000,
        'ProbePeriodMs': 1000,
        'ProbeTimeoutMs': 1000,
        'SuccessThreshold': 1,
        'FailureThreshold': 25,
    },
    'Resources': {'CPU': '1', 'Memory': '1Gi'},
}))
" "${MOUNT_PATH}" "${image}" "${REGISTRY_TYPE}"
  )"

  local tool_id
  tool_id="$(
    agr tool create \
      --tool-name "${run_prefix}-${key}" \
      --tool-type custom \
      --description "Temporary envd OCI User/Workdir validation (fixture ${key})" \
      --default-timeout "${INSTANCE_TIMEOUT}" \
      --network-configuration '{"NetworkMode":"SANDBOX"}' \
      --role-arn "${AGS_ROLE_ARN}" \
      --custom-configuration "${custom_configuration}" \
      --storage-mounts "${storage_mounts}" \
      "${agr_args[@]}" \
      --jq '.Data.ToolId'
  )"
  created_tools+=("${tool_id}")
  echo "   tool ${tool_id}"
  wait_for_tool "${tool_id}"

  local instance_id
  # The Cloud API field is Name/Value. agr's --metadata convenience flag
  # intentionally accepts Key/Value and maps it to that request shape.
  instance_id="$(
    agr instance create \
      --tool-id "${tool_id}" \
      --timeout "${INSTANCE_TIMEOUT}" \
      --metadata "[{\"Key\":\"x-envd-version\",\"Value\":\"${ENVD_VERSION_METADATA}\"}]" \
      "${agr_args[@]}" \
      --jq '.Data.InstanceId'
  )"
  created_instances+=("${instance_id}")
  echo "   instance ${instance_id:0:12}..."
  wait_for_instance "${instance_id}"

  (
    cd "${script_dir}"
    AGS_SANDBOX_ID="${instance_id}" uv run --frozen python validate_user_workdir.py "${key}"
  )
}

pre_cache "${ENVD_VOLUME_IMAGE}" "${ENVD_VOLUME_IMAGE_DIGEST}"
run_fixture a "${FIXTURE_A_IMAGE}"
run_fixture b "${FIXTURE_B_IMAGE}"

echo
echo "== all requested fixtures passed"
