#!/usr/bin/env bash

set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$script_dir/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$script_dir/.env"
  set +a
fi

: "${TENCENTCLOUD_SECRET_ID:?TENCENTCLOUD_SECRET_ID is required}"
: "${TENCENTCLOUD_SECRET_KEY:?TENCENTCLOUD_SECRET_KEY is required}"
: "${ENVD_DEMO_IMAGE:?ENVD_DEMO_IMAGE is required}"
: "${ENVD_IMAGE_REGISTRY_TYPE:?ENVD_IMAGE_REGISTRY_TYPE is required}"
: "${AGS_ROLE_ARN:?AGS_ROLE_ARN is required}"

TENCENTCLOUD_REGION="${TENCENTCLOUD_REGION:-ap-guangzhou}"
AGS_EXEC_USER="${AGS_EXEC_USER:-root}"
ENVD_VERSION="${ENVD_VERSION:-0.5.14}"

case "$ENVD_VERSION" in
  0.5.14 | 0.5.14-modified | 0.2.11) ;;
  *)
    echo "ENVD_VERSION must be 0.5.14, 0.5.14-modified, or 0.2.11" >&2
    exit 1
    ;;
esac

case "$ENVD_IMAGE_REGISTRY_TYPE" in
  personal | enterprise) ;;
  *)
    echo "ENVD_IMAGE_REGISTRY_TYPE must be personal or enterprise" >&2
    exit 1
    ;;
esac

if [[ ! "$ENVD_DEMO_IMAGE" =~ ^[A-Za-z0-9._/:@-]+$ ]]; then
  echo "ENVD_DEMO_IMAGE contains unsupported characters" >&2
  exit 1
fi

for command_name in agr; do
  command -v "$command_name" >/dev/null 2>&1 || {
    echo "$command_name is required" >&2
    exit 1
  }
done

agr_args=(--region "$TENCENTCLOUD_REGION" -o json)
tool_suffix="$(date +%s)-$$"
tool_version="${ENVD_VERSION//./-}"
off_tool_id=""
on_tool_id=""
off_instance_id=""
on_instance_id=""

cleanup() {
  local exit_code=$?
  set +e
  if [[ -n "$off_instance_id" ]]; then
    agr instance delete "$off_instance_id" "${agr_args[@]}" --ignore-not-found >/dev/null
  fi
  if [[ -n "$on_instance_id" ]]; then
    agr instance delete "$on_instance_id" "${agr_args[@]}" --ignore-not-found >/dev/null
  fi
  if [[ -n "$off_tool_id" ]]; then
    agr tool delete "$off_tool_id" "${agr_args[@]}" >/dev/null
  fi
  if [[ -n "$on_tool_id" ]]; then
    agr tool delete "$on_tool_id" "${agr_args[@]}" >/dev/null
  fi
  exit "$exit_code"
}
trap cleanup EXIT

wait_for_instance() {
  local instance_id="$1"
  local instance_status=""

  for _ in {1..90}; do
    instance_status="$(
      agr instance get "$instance_id" \
        "${agr_args[@]}" \
        --jq '.Data.Status'
    )"

    case "$instance_status" in
      RUNNING)
        return 0
        ;;
      FAILED | STARTING_FAILED | STOPPING_FAILED)
        echo "Instance $instance_id entered terminal status $instance_status" >&2
        return 1
        ;;
    esac

    sleep 2
  done

  echo "Instance $instance_id did not become RUNNING within 180 seconds" >&2
  return 1
}

echo "Pre-caching $ENVD_DEMO_IMAGE"
image_digest="$(
  agr pre-cache-image-task create \
    --image "$ENVD_DEMO_IMAGE" \
    --image-registry-type "$ENVD_IMAGE_REGISTRY_TYPE" \
    "${agr_args[@]}" \
    --jq '.Data.ImageDigest'
)"

pre_cache_ready=false
for _ in {1..60}; do
  pre_cache_status="$(
    agr pre-cache-image-task get "$image_digest" \
      --image "$ENVD_DEMO_IMAGE" \
      --image-registry-type "$ENVD_IMAGE_REGISTRY_TYPE" \
      "${agr_args[@]}" \
      --jq '.Data.Status'
  )"
  case "$pre_cache_status" in
    Success)
      echo "Image pre-cache completed"
      pre_cache_ready=true
      break
      ;;
    Failed)
      echo "Image pre-cache failed" >&2
      exit 1
      ;;
  esac
  sleep 2
done

if [[ "$pre_cache_ready" != true ]]; then
  echo "Image pre-cache did not complete within 120 seconds" >&2
  exit 1
fi

if [[ "${1:-}" == "--pre-cache-only" ]]; then
  trap - EXIT
  exit 0
fi

common_custom_config="$(
  printf '{"Image":"%s","ImageRegistryType":"%s","Command":["/usr/bin/envd"],"Env":[{"Name":"EXEC_ENABLE_ALL_ENV","Value":"0"},{"Name":"ENVD_RUNTIME_OFF","Value":"from-runtime-config"}],"Ports":[{"Name":"envd","Port":49983,"Protocol":"TCP"}],"Probe":{"HttpGet":{"Path":"/health","Port":49983,"Scheme":"HTTP"},"ReadyTimeoutMs":30000,"ProbePeriodMs":1000,"ProbeTimeoutMs":1000,"SuccessThreshold":1,"FailureThreshold":20},"Resources":{"CPU":"1","Memory":"1Gi"}}' \
    "$ENVD_DEMO_IMAGE" "$ENVD_IMAGE_REGISTRY_TYPE"
)"

enabled_custom_config="$(
  printf '{"Image":"%s","ImageRegistryType":"%s","Command":["/usr/bin/envd"],"Env":[{"Name":"ENVD_RUNTIME_ONLY","Value":"from-runtime-config"}],"Ports":[{"Name":"envd","Port":49983,"Protocol":"TCP"}],"Probe":{"HttpGet":{"Path":"/health","Port":49983,"Scheme":"HTTP"},"ReadyTimeoutMs":30000,"ProbePeriodMs":1000,"ProbeTimeoutMs":1000,"SuccessThreshold":1,"FailureThreshold":20},"Resources":{"CPU":"1","Memory":"1Gi"}}' \
    "$ENVD_DEMO_IMAGE" "$ENVD_IMAGE_REGISTRY_TYPE"
)"

echo "Creating temporary AGS tools"
off_tool_id="$(
  agr tool create \
    --tool-name "envd-$tool_version-env-off-$tool_suffix" \
    --tool-type custom \
    --description "Temporary envd $ENVD_VERSION inheritance validation: disabled" \
    --default-timeout 30m \
    --network-configuration '{"NetworkMode":"SANDBOX"}' \
    --role-arn "$AGS_ROLE_ARN" \
    --custom-configuration "$common_custom_config" \
    "${agr_args[@]}" \
    --jq '.Data.ToolId'
)"

on_tool_id="$(
  agr tool create \
    --tool-name "envd-$tool_version-env-on-$tool_suffix" \
    --tool-type custom \
    --description "Temporary envd $ENVD_VERSION inheritance validation: enabled" \
    --default-timeout 30m \
    --network-configuration '{"NetworkMode":"SANDBOX"}' \
    --role-arn "$AGS_ROLE_ARN" \
    --custom-configuration "$enabled_custom_config" \
    "${agr_args[@]}" \
    --jq '.Data.ToolId'
)"

echo "Creating temporary AGS sandboxes"
off_instance_id="$(
  agr instance create \
    --tool-id "$off_tool_id" \
    --timeout 20m \
    "${agr_args[@]}" \
    --jq '.Data.InstanceId'
)"

on_instance_id="$(
  agr instance create \
    --tool-id "$on_tool_id" \
    --timeout 20m \
    "${agr_args[@]}" \
    --jq '.Data.InstanceId'
)"

echo "Waiting for temporary AGS sandboxes"
wait_for_instance "$off_instance_id"
wait_for_instance "$on_instance_id"

echo "Validating inheritance behavior with EXEC_ENABLE_ALL_ENV=0"
agr instance exec "$off_instance_id" \
  --user "$AGS_EXEC_USER" \
  --env ENVD_EXPECTED_SOURCE="$ENVD_VERSION" \
  "${agr_args[@]}" \
  -- /bin/sh -c \
  'actual_version="$(/usr/bin/envd -version)"
   expected_version="${ENVD_EXPECTED_SOURCE%%-*}"
   test "$actual_version" = "$expected_version" || {
     printf "FAIL: envd version is %s, expected %s\n" "$actual_version" "$expected_version" >&2
     exit 1
   }
   if test "$ENVD_EXPECTED_SOURCE" = "$expected_version-modified"; then
     test "${ENVD_IMAGE_ONLY-}" = from-oci-image || {
       printf "FAIL: modified envd did not inherit image env\n" >&2
       exit 1
     }
     test "${ENVD_RUNTIME_OFF-}" = from-runtime-config || {
       printf "FAIL: modified envd did not inherit runtime env\n" >&2
       exit 1
     }
     printf "PASS: envd %s inherits image and runtime env independently of the opt-in switch\n" "$actual_version"
   else
     test "${ENVD_IMAGE_ONLY+x}" != x || {
       printf "FAIL: image env is present when inheritance is disabled\n" >&2
       exit 1
     }
     test "${ENVD_RUNTIME_OFF+x}" != x || {
       printf "FAIL: runtime env is present when inheritance is disabled\n" >&2
       exit 1
     }
     printf "PASS: envd %s does not inherit image or runtime env when disabled\n" "$actual_version"
   fi'

echo "Validating EXEC_ENABLE_ALL_ENV=1"
agr instance exec "$on_instance_id" \
  --user "$AGS_EXEC_USER" \
  --env ENVD_EXPECTED_SOURCE="$ENVD_VERSION" \
  "${agr_args[@]}" \
  -- /bin/sh -c \
  'actual_version="$(/usr/bin/envd -version)"
   expected_version="${ENVD_EXPECTED_SOURCE%%-*}"
   test "$actual_version" = "$expected_version" || {
     printf "FAIL: envd version is %s, expected %s\n" "$actual_version" "$expected_version" >&2
     exit 1
   }
   pid1_exe="$(readlink /proc/1/exe)"
   test "$pid1_exe" = /usr/bin/envd || {
     printf "FAIL: PID 1 executable is %s, expected /usr/bin/envd\n" "$pid1_exe" >&2
     exit 1
   }
   test "${ENVD_SOURCE_VERSION-}" = "$ENVD_EXPECTED_SOURCE" || {
     printf "FAIL: image source marker is %s, expected %s\n" "${ENVD_SOURCE_VERSION-}" "$ENVD_EXPECTED_SOURCE" >&2
     exit 1
   }
   test "${ENVD_IMAGE_ONLY-}" = from-oci-image || {
     printf "FAIL: OCI image environment was not inherited\n" >&2
     exit 1
   }
   test "${ENVD_RUNTIME_ONLY-}" = from-runtime-config || {
     printf "FAIL: AGS runtime environment is unavailable\n" >&2
     exit 1
   }
   test "${EXEC_ENABLE_ALL_ENV-}" = 1 || {
     printf "FAIL: EXEC_ENABLE_ALL_ENV is unavailable\n" >&2
     exit 1
   }
   printf "PASS: envd %s PID 1, image env, and runtime env verified\n" "$actual_version"'

echo "Validating per-request override precedence"
agr instance exec "$on_instance_id" \
  --user "$AGS_EXEC_USER" \
  --env ENVD_OVERRIDE_ORDER=from-request \
  "${agr_args[@]}" \
  -- /bin/sh -c \
  'test "${ENVD_OVERRIDE_ORDER-}" = from-request || {
     printf "FAIL: command-specific environment did not override the inherited value\n" >&2
     exit 1
   }
   printf "PASS: command-specific env overrides inherited image env\n"'

echo "All envd inheritance checks passed"
