#!/usr/bin/env bash
set -euo pipefail

: "${KUBECONFIG:?KUBECONFIG 未设置}"
: "${STORAGE_CLASS:=awv-btrfs}"
for command in kubectl helm node curl jq; do
  command -v "$command" >/dev/null || { echo "缺少命令：$command" >&2; exit 1; }
done
kubectl --kubeconfig "$KUBECONFIG" cluster-info >/dev/null
kubectl --kubeconfig "$KUBECONFIG" get storageclass "$STORAGE_CLASS" >/dev/null
ready_nodes="$(kubectl --kubeconfig "$KUBECONFIG" get nodes --no-headers | awk '$2 ~ /^Ready/ {count++} END {print count+0}')"
test "$ready_nodes" -ge 1 || { echo "没有 Ready 节点" >&2; exit 1; }
test -n "${OPENAI_API_KEY:-}" || { echo "OPENAI_API_KEY 未设置" >&2; exit 1; }
echo "preflight PASS: storageClass=$STORAGE_CLASS readyNodes=$ready_nodes"
