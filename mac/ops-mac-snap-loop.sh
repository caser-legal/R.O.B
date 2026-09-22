#!/bin/bash
# Background loop: run ops-mac-snap.sh every 15s
DIR="$HOME/Library/Application Support/rob"
SCRIPT="$DIR/ops-mac-snap.sh"
LOG="$DIR/ops-mac-snap.log"
PIDFILE="$DIR/ops-mac-snap.pid"
echo $$ > "$PIDFILE"
# ignore HUP
trap '' HUP
while true; do
  /bin/bash "$SCRIPT" >>"$LOG" 2>&1 || true
  sleep 15
done
