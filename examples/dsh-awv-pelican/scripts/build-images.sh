#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
: "${OUTPUT_DIR:=$root/.local}"
: "${REGISTRY:?REGISTRY 未设置}"
: "${IMAGE_TAG:?IMAGE_TAG 未设置}"
mkdir -p "$OUTPUT_DIR"

controller="$REGISTRY/dsh-awv-controller:$IMAGE_TAG"
worker="$REGISTRY/dsh-awv-worker:$IMAGE_TAG"
docker build --platform linux/amd64 --target controller -f "$root/images/Dockerfile" -t "$controller" "$root"
docker build --platform linux/amd64 --target worker -f "$root/images/Dockerfile" -t "$worker" "$root"
docker push "$controller"
docker push "$worker"

controller_digest="$(docker inspect --format '{{index .RepoDigests 0}}' "$controller")"
worker_digest="$(docker inspect --format '{{index .RepoDigests 0}}' "$worker")"
printf 'CONTROLLER_IMAGE=%q\nWORKER_IMAGE=%q\n' "$controller_digest" "$worker_digest" > "$OUTPUT_DIR/images.env"
echo "controller=$controller_digest"
echo "worker=$worker_digest"
