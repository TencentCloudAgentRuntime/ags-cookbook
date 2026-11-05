#!/usr/bin/env bash
set -euo pipefail

: "${KUBECONFIG:?KUBECONFIG 未设置}"
: "${NAMESPACE:=dsh-awv}"
kubectl --kubeconfig "$KUBECONFIG" -n "$NAMESPACE" get deployment dsh-harness >/dev/null
pvc_phase="$(kubectl --kubeconfig "$KUBECONFIG" -n "$NAMESPACE" get pvc pelican-workspace -o jsonpath='{.status.phase}')"
[[ "$pvc_phase" == "Pending" || "$pvc_phase" == "Bound" ]]
kubectl --kubeconfig "$KUBECONFIG" -n "$NAMESPACE" auth can-i create jobs --as="system:serviceaccount:$NAMESPACE:dsh-harness" | grep -q yes
cluster_admin="$(kubectl --kubeconfig "$KUBECONFIG" auth can-i create clusterroles --as="system:serviceaccount:$NAMESPACE:dsh-harness" 2>/dev/null || true)"
[[ "$cluster_admin" == "no" ]]
echo "verify PASS"
