#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
: "${OUTPUT_DIR:=$root/.local}"
: "${KUBECONFIG:?KUBECONFIG 未设置}"
: "${NAMESPACE:=dsh-awv}"
: "${MODEL_SECRET:=dsh-model}"
: "${STORAGE_CLASS:=awv-btrfs}"
: "${OPENAI_API_KEY:?OPENAI_API_KEY 未设置}"
source "$OUTPUT_DIR/images.env"

kubectl --kubeconfig "$KUBECONFIG" create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl --kubeconfig "$KUBECONFIG" apply -f -
model_secret_args=(--from-literal=OPENAI_API_KEY="$OPENAI_API_KEY")
if [[ -n "${OPENAI_BASE_URL:-}" ]]; then
  model_secret_args+=(--from-literal=OPENAI_BASE_URL="$OPENAI_BASE_URL")
fi
if [[ -n "${OPENAI_API_TYPE:-}" ]]; then
  model_secret_args+=(--from-literal=OPENAI_API_TYPE="$OPENAI_API_TYPE")
fi
if [[ -n "${DSH_MODEL:-}" ]]; then
  model_secret_args+=(--from-literal=DSH_MODEL="$DSH_MODEL")
fi
if [[ -n "${DSH_CODE_MODEL:-}" ]]; then
  model_secret_args+=(--from-literal=DSH_CODE_MODEL="$DSH_CODE_MODEL")
fi
if [[ -n "${DSH_REVIEW_MODEL:-}" ]]; then
  model_secret_args+=(--from-literal=DSH_REVIEW_MODEL="$DSH_REVIEW_MODEL")
fi
kubectl --kubeconfig "$KUBECONFIG" -n "$NAMESPACE" create secret generic "$MODEL_SECRET" \
  "${model_secret_args[@]}" --dry-run=client -o yaml \
  | kubectl --kubeconfig "$KUBECONFIG" apply -f -

pull_args=()
if [[ -n "${IMAGE_PULL_SECRET:-}" ]]; then
  : "${DOCKER_CONFIG_FILE:?配置 IMAGE_PULL_SECRET 时必须设置 DOCKER_CONFIG_FILE}"
  kubectl --kubeconfig "$KUBECONFIG" -n "$NAMESPACE" create secret generic "$IMAGE_PULL_SECRET" \
    --type=kubernetes.io/dockerconfigjson --from-file=.dockerconfigjson="$DOCKER_CONFIG_FILE" \
    --dry-run=client -o yaml | kubectl --kubeconfig "$KUBECONFIG" apply -f -
  pull_args=(
    --set "imagePullSecrets[0].name=$IMAGE_PULL_SECRET"
    --set-string "imagePullSecret=$IMAGE_PULL_SECRET"
  )
fi

helm upgrade --install dsh-awv "$root/deploy/helm/dsh-awv" \
  --kubeconfig "$KUBECONFIG" --namespace "$NAMESPACE" \
  --set-string "controller.image=$CONTROLLER_IMAGE" \
  --set-string "worker.image=$WORKER_IMAGE" \
  --set-string "workspace.storageClassName=$STORAGE_CLASS" \
  --set-string "modelSecret=$MODEL_SECRET" \
  --set-string "nodes.controller=${CONTROLLER_NODE:-}" \
  --set-string "nodes.code=${CODE_NODE:-}" \
  --set-string "nodes.review=${REVIEW_NODE:-}" \
  --set-string "nodes.site=${SITE_NODE:-}" \
  "${pull_args[@]}"

kubectl --kubeconfig "$KUBECONFIG" -n "$NAMESPACE" rollout status deployment/dsh-harness --timeout=5m
