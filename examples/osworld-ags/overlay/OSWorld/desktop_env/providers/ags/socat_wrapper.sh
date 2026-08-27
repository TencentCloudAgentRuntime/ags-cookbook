#!/bin/bash

REAL=/usr/bin/socat.real
PROXY_PATH=${OSWORLD_CDP_PROXY_PATH:-/tmp/cdp_proxy.py}
PROXY_LOG=${OSWORLD_CDP_PROXY_LOG:-/tmp/cdp_proxy.log}
PROXY_PIDFILE=${OSWORLD_CDP_PROXY_PIDFILE:-/tmp/cdp_proxy.pid}
PROXY_PORT=${OSWORLD_CDP_PROXY_PORT:-9222}

proxy_ready() {
  python3 -S -c 'import socket, sys
s = socket.socket()
s.settimeout(0.5)
result = s.connect_ex(("127.0.0.1", int(sys.argv[1])))
s.close()
raise SystemExit(result)' "$PROXY_PORT"
}

proxy_process_matches() {
  python3 -S -c 'from pathlib import Path
import sys
cmdline = Path(f"/proc/{sys.argv[1]}/cmdline").read_bytes()
raise SystemExit(0 if sys.argv[2].encode() in cmdline else 1)' "$1" "$PROXY_PATH" 2>/dev/null
}

for arg in "$@"; do
  case "$arg" in
    tcp-listen:9222*)
      if [ -r "$PROXY_PIDFILE" ]; then
        read -r existing_pid <"$PROXY_PIDFILE" || existing_pid=
        if [ -n "$existing_pid" ] \
          && kill -0 "$existing_pid" 2>/dev/null \
          && proxy_process_matches "$existing_pid" \
          && proxy_ready; then
          exit 0
        fi
        if ! rm -f "$PROXY_PIDFILE"; then
          echo "Failed to remove stale CDP proxy pidfile: $PROXY_PIDFILE" >&2
          exit 1
        fi
      fi
      if proxy_ready; then
        echo "Port $PROXY_PORT is already in use by an unmanaged process" >&2
        exit 1
      fi

      nohup python3 -S "$PROXY_PATH" </dev/null >"$PROXY_LOG" 2>&1 &
      proxy_pid=$!
      if ! printf '%s\n' "$proxy_pid" >"$PROXY_PIDFILE"; then
        echo "Failed to write CDP proxy pidfile: $PROXY_PIDFILE" >&2
        kill "$proxy_pid" 2>/dev/null || true
        wait "$proxy_pid" 2>/dev/null || true
        exit 1
      fi
      for ((i = 0; i < 50; i++)); do
        if kill -0 "$proxy_pid" 2>/dev/null \
          && proxy_process_matches "$proxy_pid" \
          && proxy_ready; then
          exit 0
        fi
        sleep 0.2
      done
      echo "CDP proxy failed to listen on port $PROXY_PORT; see $PROXY_LOG" >&2
      kill "$proxy_pid" 2>/dev/null || true
      wait "$proxy_pid" 2>/dev/null || true
      if ! rm -f "$PROXY_PIDFILE"; then
        echo "Failed to remove CDP proxy pidfile: $PROXY_PIDFILE" >&2
      fi
      exit 1
      ;;
  esac
done

exec "$REAL" "$@"
