#!/bin/bash
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
DIR="$HOME/Library/Application Support/rob"
LA="$HOME/Library/LaunchAgents"
mkdir -p "$DIR" "$LA"
cp -f "$SRC/ops-mac-snap.sh" "$DIR/"
if [ ! -f "$DIR/cameras.json" ]; then
  cp -f "$SRC/cameras.example.json" "$DIR/cameras.json"
fi
cp -f "$SRC/ops-mac-snap-loop.sh" "$DIR/"
chmod +x "$DIR/ops-mac-snap.sh" "$DIR/ops-mac-snap-loop.sh"
PLIST="$LA/com.rob.ops-mac-snap.plist"
sed "s|REPLACE_ME/ops-mac-snap-loop.sh|$DIR/ops-mac-snap-loop.sh|" "$SRC/com.rob.ops-mac-snap.plist" > "$PLIST"
UID_N="$(id -u)"
launchctl bootout "gui/$UID_N/com.rob.ops-mac-snap" 2>/dev/null || true
launchctl bootstrap "gui/$UID_N" "$PLIST"
echo "Installed com.rob.ops-mac-snap → $DIR/ops-mac-snap.json"
