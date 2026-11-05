#!/usr/bin/env bash
set -euo pipefail
: "${KUBECONFIG:?KUBECONFIG is required}"
: "${NAMESPACE:=dsh-awv}"
printf '%s\n' 'Open the token-bearing login URL from the Controller logs:'
kubectl --kubeconfig "$KUBECONFIG" -n "$NAMESPACE" logs deployment/dsh-harness --tail=50
printf '%s\n' 'Forwarding Harness to http://127.0.0.1:3080; Ctrl-C stops forwarding only.'
kubectl --kubeconfig "$KUBECONFIG" -n "$NAMESPACE" port-forward service/dsh-harness 3080:80
