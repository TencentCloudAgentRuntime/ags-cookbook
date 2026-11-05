#!/usr/bin/env bash
set -euo pipefail

: "${KUBECONFIG:?KUBECONFIG 未设置}"
: "${NAMESPACE:=dsh-awv}"
kubectl --kubeconfig "$KUBECONFIG" -n "$NAMESPACE" delete \
  deployment/pelican-site service/pelican-site --ignore-not-found=true --wait=true
helm uninstall dsh-awv --kubeconfig "$KUBECONFIG" -n "$NAMESPACE" --wait 2>/dev/null || true
kubectl --kubeconfig "$KUBECONFIG" -n "$NAMESPACE" delete job,configmap,lease,service,deployment -l app=dsh-awv --ignore-not-found=true
echo "PVC pelican-workspace 和凭证 Secret 已保留。确认不再需要后手工删除 namespace。"
