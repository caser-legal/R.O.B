#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/ops-center"
chmod +x ensure_ops_center.sh publish_loop.sh publish_status.py 2>/dev/null || true
bash ensure_ops_center.sh once
echo "Board: http://127.0.0.1:8765/"
echo "Watchdog: bash ensure_ops_center.sh"
