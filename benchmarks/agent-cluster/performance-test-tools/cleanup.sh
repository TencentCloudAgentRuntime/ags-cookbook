#!/usr/bin/env bash
set -Eeuo pipefail

system_namespace=cube-cri-load-system
run_id=""

while (($#)); do
  case "$1" in
    --run-id) run_id="$2"; shift 2 ;;
    -h|--help) echo "Usage: $0 --run-id ID"; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

[[ -n "$run_id" ]] || { echo "--run-id is required" >&2; exit 2; }
[[ -n "${KUBECONFIG:-}" && -r "$KUBECONFIG" ]] || { echo "KUBECONFIG must be explicitly set to a readable file" >&2; exit 2; }
[[ "$run_id" =~ ^[a-z0-9]([a-z0-9-]{0,30}[a-z0-9])?$ ]] || {
  echo "Invalid run ID: $run_id" >&2
  exit 2
}

namespaces=()
while IFS= read -r namespace; do
  [[ -n "$namespace" ]] && namespaces+=("$namespace")
done < <(
  kubectl get namespaces -l "cube-cri-load-owned=true,load-test-run=$run_id" -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}'
)

for namespace in "${namespaces[@]}"; do
  [[ "$namespace" =~ ^cube-cri-load-${run_id}-[0-9]+$ ]] || {
    echo "Cleanup refused for an unexpected Namespace name: $namespace" >&2
    exit 1
  }
done

for namespace in "${namespaces[@]}"; do
  [[ -n "$namespace" ]] || continue
  kubectl delete pods --all -n "$namespace" --wait=false >/dev/null
done

deadline=$((SECONDS + 600))
while ((SECONDS < deadline)); do
  residual_count="$(kubectl get pods -A -l "load-test-batch=$run_id" -o json | jq '.items | length')"
  [[ "$residual_count" -eq 0 ]] && break
  sleep 2
done
[[ "$residual_count" -eq 0 ]] || { echo "Target Pods did not reach zero within 600 seconds: $residual_count" >&2; exit 1; }

# Large Pod batches can generate thousands of duplicate Events. Delete both
# Event collections first to avoid namespace controller request timeouts.
event_delete_pids=()
for namespace in "${namespaces[@]}"; do
  [[ -n "$namespace" ]] || continue
  kubectl delete events --all -n "$namespace" --wait=false --request-timeout=300s >/dev/null &
  event_delete_pids+=("$!")
  kubectl delete events.events.k8s.io --all -n "$namespace" --wait=false --request-timeout=300s >/dev/null &
  event_delete_pids+=("$!")
done
for pid in "${event_delete_pids[@]}"; do
  wait "$pid"
done

for namespace in "${namespaces[@]}"; do
  [[ -n "$namespace" ]] || continue
  kubectl delete namespace "$namespace" --wait=false >/dev/null
done

kubectl delete pod -n "$system_namespace" "cube-cri-load-generator-$run_id" --ignore-not-found --wait=false >/dev/null
kubectl delete configmap -n "$system_namespace" "cube-cri-load-$run_id" --ignore-not-found >/dev/null

deadline=$((SECONDS + 300))
while ((SECONDS < deadline)); do
  namespace_count="$(kubectl get namespaces -l "cube-cri-load-owned=true,load-test-run=$run_id" -o json | jq '.items | length')"
  generator_count="$(kubectl get pods -n "$system_namespace" -l "load-test-run=$run_id" -o json | jq '.items | length')"
  [[ "$namespace_count" -eq 0 && "$generator_count" -eq 0 ]] && break
  sleep 2
done
[[ "$namespace_count" -eq 0 ]] || { echo "Target Namespaces did not reach zero within 300 seconds: $namespace_count" >&2; exit 1; }
[[ "$generator_count" -eq 0 ]] || { echo "Generator Pods did not reach zero within 300 seconds: $generator_count" >&2; exit 1; }

residual="$(kubectl get pods -A -l "load-test-batch=$run_id" -o name)"
[[ -z "$residual" ]] || { printf 'Residual Pods:\n%s\n' "$residual" >&2; exit 1; }
printf 'cleanup_run=%s namespaces=%s residual_pods=0\n' "$run_id" "${#namespaces[@]}"
