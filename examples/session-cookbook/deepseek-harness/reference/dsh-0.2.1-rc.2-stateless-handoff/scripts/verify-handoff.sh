#!/bin/sh
# Check stateless handoff against two running replicas: A -> B -> A on one Session.
#
#   scripts/verify-handoff.sh <url-of-A-with-token> <url-of-B-with-token> [session-id]
#
# Each URL is the "dsh web: http://HOST:PORT/?token=..." line a replica prints at
# startup, with the host and port you actually published, for example
# http://127.0.0.1:18091/?token=abc. The Session must already exist (create one in
# the web UI, or use the id printed by a previous run), and both replicas must use
# the same SESSION_SPACE_ID / SESSION_USER_ID.
#
# Needs: curl, python3. The model must be configured; each turn makes one model call.
set -eu

A_URL=${1:?usage: $0 <A url with token> <B url with token> <session-id>}
B_URL=${2:?usage: $0 <A url with token> <B url with token> <session-id>}
SESSION_ID=${3:?usage: $0 <A url with token> <B url with token> <session-id>}

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

login() { # url cookie-file
  base=${1%%\?*}; base=${base%/}
  token=${1#*token=}
  code=$(curl -s -o /dev/null -w '%{http_code}' -c "$2" "$base/?token=$token")
  [ "$code" = 303 ] || { echo "login to $base failed (HTTP $code); is the token current?" >&2; exit 1; }
  echo "$base"
}

prompt() { # base cookie-file text
  rpc=$(python3 -c 'import uuid;print(uuid.uuid4())')
  body=$(python3 - "$rpc" "$SESSION_ID" "$3" <<'PY'
import json, sys
rpc, session, text = sys.argv[1:4]
print(json.dumps({"type": "client-request", "rpcId": rpc, "method": "session/prompt",
  "payload": {"args": {"request": {"requestId": "req-" + rpc, "sessionId": session, "mode": "queue",
    "content": [{"type": "text", "text": text}]}}}}))
PY
)
  curl --fail-with-body -sS -m 180 -b "$2" -H 'content-type: application/json' -X POST "$1/api/session/prompt" -d "$body" > "$work/response.json"
  python3 - "$work/response.json" <<'PYCODE'
import json, sys
with open(sys.argv[1]) as f:
    envelope = json.load(f)
result = envelope.get("result", {})
if not result.get("ok") or not result.get("value", {}).get("accepted"):
    raise SystemExit("prompt was not accepted: " + json.dumps(envelope))
print(json.dumps(envelope))
PYCODE
}

A=$(login "$A_URL" "$work/a.txt")
B=$(login "$B_URL" "$work/b.txt")

echo "1) A takes the first turn";  prompt "$A" "$work/a.txt" "Remember the marker ALPHA-42. Reply only ACK."
echo "   wait for the turn to finish (the answer shows in the web UI), then press Enter"; read -r _
echo "2) B takes the next turn";   prompt "$B" "$work/b.txt" "Reply only with the complete earlier marker that begins with ALPHA-."
echo "   wait for the turn to finish, then press Enter"; read -r _
echo "3) A takes it back";         prompt "$A" "$work/a.txt" "Reply only with the complete earlier marker that begins with ALPHA-."
echo
echo "Expected: all three requests return {\"ok\":true,\"value\":{\"accepted\":true}}."
echo "Then check the replies in the web UI (ACK, ALPHA-42, ALPHA-42) and A's container log:"
echo "  [dsh-stateless-handoff] handoff rebuild started   {\"reason\":\"preflight-stale\"}"
echo "  [dsh-stateless-handoff] handoff rebuild finished  {\"reason\":\"preflight-stale\"}"
