#!/bin/bash
# Keep the ops board HTTP server and publish loop running.
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
mkdir -p data

ensure_http() {
  if ! curl -sf -o /dev/null --max-time 2 http://127.0.0.1:8765/; then
    if [ -f /tmp/ops-center-http.pid ]; then
      kill "$(cat /tmp/ops-center-http.pid)" 2>/dev/null || true
      rm -f /tmp/ops-center-http.pid
    fi
    nohup python3 -m http.server 8765 >/tmp/ops-center-http.log 2>&1 &
    echo $! > /tmp/ops-center-http.pid
    sleep 0.4
  fi
}

ensure_publish() {
  if ! pgrep -f "$ROOT/publish_loop.sh" >/dev/null 2>&1; then
    nohup bash "$ROOT/publish_loop.sh" >/tmp/ops-publish-loop.out 2>&1 &
    echo $! > /tmp/ops-publish-loop.pid
  fi
}

if [ "${1:-}" = "once" ]; then
  ensure_http
  ensure_publish
  python3 publish_status.py || true
  exit 0
fi

while true; do
  ensure_http
  ensure_publish
  sleep 20
done
