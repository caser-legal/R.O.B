#!/bin/bash
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
while true; do
  python3 publish_status.py >>/tmp/ops-publish.log 2>&1
  sleep 10
done
