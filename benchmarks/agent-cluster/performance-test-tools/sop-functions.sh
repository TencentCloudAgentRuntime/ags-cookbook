#!/usr/bin/env bash

# Shared functions for the Cube CRI performance test SOP. Source this file; do not execute it directly.

export RESULT_ROOT="${RESULT_ROOT:-$PWD/_output/customer-cube-cri-performance}"
export GENERATOR_IMAGE="${GENERATOR_IMAGE:-ccr.ccs.tencentyun.com/journeyyou/cube-cri-load-generator@sha256:af8df75c2abd835b00755072df1c43e95244d4435abeeeaeff2cc41ec1416fad}"
export SNAPSHOTTER_PROFILE="${SNAPSHOTTER_PROFILE:-overlayfs}"

require_sop_variables() {
  local name
  for name in "$@"; do
    if [[ -z "$(printenv "$name")" ]]; then
      echo "Required variable is not set: $name" >&2
      return 1
    fi
  done
}

run_case() {
  require_sop_variables KUBECONFIG TARGET_NODE GENERATOR_NODE GENERATOR_IMAGE \
    SNAPSHOTTER_PROFILE LOAD_IMAGE SCALE_LOAD_DIR RESULT_ROOT || return 1
  local run_id="$1"
  local count="$2"
  local qps="$3"
  local workers="$4"
  local stable_seconds="$5"
  local image_state="$6"
  shift 6
  local workload_profile=simple
  local slo_args=()

  while (($#)); do
    case "$1" in
      --workload-profile)
        if (($# < 2)) || [[ -z "$2" || "$2" == --* ]]; then
          echo "Missing value for $1" >&2
          return 2
        fi
        workload_profile="$2"
        shift 2
        ;;
      *) echo "Unknown test argument: $1" >&2; return 2 ;;
    esac
  done
  case "$workload_profile" in
    simple|production) ;;
    *) echo 'workload-profile must be production or simple' >&2; return 2 ;;
  esac

  if [[ -n "${READY_P99_SLO_MS:-}" ]]; then
    slo_args=(--ready-p99-slo-ms "$READY_P99_SLO_MS")
  fi

  if kubectl get namespace "cube-cri-load-$run_id-0" >/dev/null 2>&1 \
    || [[ "$(kubectl get pods -A -l "load-test-batch=$run_id" -o json | jq '.items | length')" != 0 ]]; then
    echo "Run ID already exists; refusing to reuse it: $run_id" >&2
    return 1
  fi

  "$SCALE_LOAD_DIR/run.sh" \
    --stage S0 \
    --generator-node "$GENERATOR_NODE" \
    --target-node "$TARGET_NODE" \
    --workload-profile "$workload_profile" \
    --snapshotter-profile "$SNAPSHOTTER_PROFILE" \
    --load-image "$LOAD_IMAGE" \
    --image-state "$image_state" \
    --count "$count" \
    --namespaces 1 \
    --qps "$qps" \
    --workers "$workers" \
    --timeout 300 \
    --stable-seconds "$stable_seconds" \
    --generator-image "$GENERATOR_IMAGE" \
    --generator-image-pull-policy IfNotPresent \
    --output "$RESULT_ROOT/$run_id" \
    --run-id "$run_id" \
    "${slo_args[@]}"
}

show_result() {
  require_sop_variables RESULT_ROOT || return 1
  local summary="$RESULT_ROOT/$1/batch-summary.json"
  if [[ ! -f "$summary" ]]; then
    echo "Result file not found: $summary" >&2
    return 1
  fi
  if ! (cd "$(dirname "$summary")" && sha256sum -c artifacts.sha256 >/dev/null); then
    echo "Result integrity check failed: $(dirname "$summary")" >&2
    return 1
  fi
  jq '{
    runId, accepted, success, count, created, scheduled,
    containersStarted, ready, restartCount, readyLost, imageIdentityMismatches,
    configured: {qps: .createQPS, workers, stableSeconds},
    actualRequestWriteQPS: .batch.actualRequestWriteQPS,
    batchMs: {
      submit: .batch.submitMs,
      allScheduled: .batch.allScheduledMs,
      allContainersStarted: .batch.allContainersStartedMs,
      allReady: .batch.allReadyMs
    },
    latencyMs: {
      createToScheduled: .metrics.create_start_to_scheduled_observed_ms,
      scheduledToReady: .metrics.scheduled_to_ready_observed_ms,
      containersStartedToReady: .metrics.containers_started_to_ready_observed_ms,
      createToReady: .metrics.create_start_to_ready_observed_ms
    },
    slo,
    warnings: .workloadWarnings, errors
  }' "$summary"
}

cleanup_case() {
  require_sop_variables KUBECONFIG SCALE_LOAD_DIR || return 1
  local run_id="$1"
  local expected="namespace/cube-cri-load-$run_id-0"
  local selected
  selected="$(kubectl get namespaces \
    -l "cube-cri-load-owned=true,load-test-run=$run_id" -o name)"
  if [[ -n "$selected" && "$selected" != "$expected" ]]; then
    echo "Cleanup refused: expected $expected, found ${selected:-<none>}" >&2
    return 1
  fi
  "$SCALE_LOAD_DIR/cleanup.sh" --run-id "$run_id"
}

cleanup_test() {
  cleanup_case "$1"
}

assert_managed_resource() {
  local kind="$1"
  local name="$2"
  if kubectl get "$kind" "$name" >/dev/null 2>&1; then
    [[ "$(kubectl get "$kind" "$name" -o json | jq -r \
      '.metadata.labels["app.kubernetes.io/managed-by"] // ""')" \
      == cube-cri-performance-test ]] || {
      echo "Shared resource is not managed by this tool; refusing to delete: $kind/$name" >&2
      return 1
    }
  fi
}

cleanup_shared_test_resources() {
  require_sop_variables KUBECONFIG GENERATOR_NODE || return 1
  local active_load_pods
  local active_generators=0
  local node_state
  local node_marked
  local node_owner

  active_load_pods="$(kubectl get pods -A -l load-test-batch -o json | jq '.items | length')"
  if kubectl get namespace cube-cri-load-system >/dev/null 2>&1; then
    active_generators="$(kubectl get pods -n cube-cri-load-system \
      -l app=cube-cri-load-generator -o json | jq '.items | length')"
  fi
  if ((active_load_pods != 0 || active_generators != 0)); then
    echo 'Test Pods still exist; refusing to delete shared resources.' >&2
    return 1
  fi

  assert_managed_resource namespace cube-cri-load-system || return 1
  assert_managed_resource clusterrole cube-cri-load-generator || return 1
  assert_managed_resource runtimeclass cube-load || return 1

  node_state="$(kubectl get node "$GENERATOR_NODE" -o json)"
  node_marked="$(jq -r '
    ((.metadata.labels["cube-cri-load-generator"] // "") != "")
    or ([.spec.taints[]? | select(.key == "cube-cri-load-generator")] | length > 0)
  ' <<<"$node_state")"
  node_owner="$(jq -r \
    '.metadata.labels["cube-cri-load-generator-owner"] // ""' \
    <<<"$node_state")"
  if [[ "$node_marked" == true && "$node_owner" != cube-cri-performance-test ]]; then
    echo 'Generator node markers are not managed by this tool; refusing to remove them.' >&2
    return 1
  fi

  kubectl delete namespace cube-cri-load-system --ignore-not-found
  kubectl delete clusterrole cube-cri-load-generator --ignore-not-found
  kubectl delete runtimeclass cube-load --ignore-not-found
  if [[ "$node_marked" == true ]]; then
    kubectl label node "$GENERATOR_NODE" \
      cube-cri-load-generator- cube-cri-load-generator-owner-
    kubectl taint node "$GENERATOR_NODE" cube-cri-load-generator-
  fi
  echo 'Shared test resources cleaned up.'
}

run_warmup_test() {
  export WARMUP_RUN_ID="warmup-$(date +%m%d%H%M%S%N)"
  if ! READY_P99_SLO_MS=0 run_case "$WARMUP_RUN_ID" 1 1 1 10 uncontrolled "$@"; then
    echo "Warm-up failed; artifacts were preserved at: $RESULT_ROOT/$WARMUP_RUN_ID" >&2
    return 1
  fi
  if ! show_result "$WARMUP_RUN_ID" >/dev/null; then
    echo 'Warm-up results were not saved completely; artifacts were preserved.' >&2
    return 1
  fi
  cleanup_case "$WARMUP_RUN_ID" || return 1
  echo 'Warm-up succeeded.'
}

run_serial_test() {
  local test_pods="${TEST_PODS:-16}"
  if (($#)) && [[ "$1" != --* ]]; then
    test_pods="${1:-$test_pods}"
    shift
  fi
  [[ "$test_pods" =~ ^[1-9][0-9]*$ ]] || {
    echo "Serial Pod count must be a positive integer: $test_pods" >&2
    return 2
  }
  export SERIAL_RUN_ID="serial-$(date +%m%d%H%M%S)"
  if ! run_case "$SERIAL_RUN_ID" "$test_pods" 1 1 10 pre-pulled "$@"; then
    echo "Serial test failed; artifacts were preserved at: $RESULT_ROOT/$SERIAL_RUN_ID" >&2
    return 1
  fi
  if ! show_result "$SERIAL_RUN_ID"; then
    echo 'Results were not saved completely; artifacts were preserved.' >&2
    return 1
  fi
  cleanup_case "$SERIAL_RUN_ID"
}

run_parallel_test() {
  local test_pods="${TEST_PODS:-16}"
  if (($#)) && [[ "$1" != --* ]]; then
    test_pods="${1:-$test_pods}"
    shift
  fi
  [[ "$test_pods" =~ ^[1-9][0-9]*$ ]] || {
    echo "Parallel Pod count must be a positive integer: $test_pods" >&2
    return 2
  }
  export PARALLEL_RUN_ID="parallel-$(date +%m%d%H%M%S)"
  if ! run_case \
    "$PARALLEL_RUN_ID" \
    "$test_pods" \
    "$test_pods" \
    "$test_pods" \
    10 \
    pre-pulled \
    "$@"; then
    echo "Parallel test failed; artifacts were preserved at: $RESULT_ROOT/$PARALLEL_RUN_ID" >&2
    return 1
  fi
  if ! show_result "$PARALLEL_RUN_ID"; then
    echo 'Results were not saved completely; artifacts were preserved.' >&2
    return 1
  fi
  cleanup_case "$PARALLEL_RUN_ID"
}
