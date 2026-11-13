#!/usr/bin/env bash
set -euo pipefail

case "${1:-}" in
  simple|revisions|connect|tool-market|scaling-session) scenario="$1" ;;
  -h|--help)
    echo 'Usage: bash scripts/preflight.sh <scenario>'
    echo 'Example: make preflight SCENARIO=simple'
    exit 0 ;;
  *) echo 'Choose simple, revisions, connect, tool-market or scaling-session.' >&2; exit 2 ;;
esac

for command in agr python3; do
  command -v "$command" >/dev/null || { echo "Required command is missing: $command" >&2; exit 1; }
done
for variable in AGR_REGION AGR_ROLE_ARN HARNESS_SUBNET_ID HARNESS_SECURITY_GROUP_ID TOKENHUB_API_KEY_ID HARNESS_NAME_SUFFIX; do
  value="${!variable:-}"
  if [[ -z "$value" || "$value" == *replace-me* || "$value" == your-name ]]; then
    echo "Set $variable in managed-harness-cookbook/.env first." >&2
    exit 1
  fi
done
[[ "$HARNESS_NAME_SUFFIX" =~ ^[a-z0-9][a-z0-9.-]*$ ]] || {
  echo 'HARNESS_NAME_SUFFIX must start with a lowercase letter or digit and use only lowercase letters, digits, hyphens or dots.' >&2; exit 1;
}

agr version -o json | python3 -c '
import json, sys
value = json.load(sys.stdin)
if value.get("Status") != "succeeded" or value.get("Data", {}).get("Channel") != "preview":
    sys.exit("Install the preview CLI described in README.md.")
'
agr harness --help >/dev/null
agr model-provider --help >/dev/null

if [[ "$scenario" == connect ]]; then
  agr schema harness.web -o json >/dev/null || {
    echo 'connect needs agr harness web; build the updated CLI PR described in README.md.' >&2; exit 1;
  }
  command -v curl >/dev/null || { echo 'Required command is missing for connect: curl' >&2; exit 1; }
  if ! command -v node >/dev/null || ! command -v npx >/dev/null ||
     ! node -e 'process.exit(process.versions.node.split(".").map(Number).slice(0,2).reduce((v,n)=>v*100+n,0)>=2213 ? 0 : 1)'; then
    echo 'Warning: the optional acpx example needs npx and Node.js 22.13 or newer. Install them before running that example.' >&2
  fi
fi

agr status -o text
agr doctor --region "$AGR_REGION" -o text
echo "Preflight passed: $scenario ($AGR_REGION)."
