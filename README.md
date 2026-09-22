# Rob Ops Board

A local glance board for cameras and a Mac network snapshot. You point it at your own devices. This repository has no camera names, floor plan, LAN addresses, or tokens from a particular home.

## What it does

- `mac/ops-mac-snap.sh` writes a JSON snapshot: link rates, ARP hosts on a prefix you set, and online/offline for cameras you list.
- `ops-center/publish_status.py` merges that snapshot with an optional camera-status JSON file and writes `ops-center/status.json`.
- `ops-center/index.html` renders `status.json`. A small Python HTTP server serves the folder on port 8765.

Events append to `ops-center/data/events.jsonl`. The board shows a recent window. Those data files are gitignored.

## Run your own board

Requirements: macOS for the snapshot script (`ipconfig`, `arp`, optional Swift/CoreWLAN), and Python 3 for the board. You can still serve the page on another system if you produce `data/mac-snap.json` yourself.

1. Clone the repo.
2. Install the Mac snapshot agent:

```sh
bash mac/install-mac.sh
```

3. Edit the camera list it copied to `~/Library/Application Support/rob/cameras.json`. Start from `mac/cameras.example.json`. Use your own camera display names, MACs, and addresses. `192.0.2.11` in the example is a documentation address, not a device.
4. Export LAN settings before you expect real results. Defaults stay on the documentation network `192.0.2.0/24` so a fresh clone does not scan a private subnet:

```sh
export ROB_IFACE=en0
export ROB_GATEWAY=192.0.2.1
export ROB_LAN_PREFIX=192.0.2.
export ROB_CAMERAS="$HOME/Library/Application Support/rob/cameras.json"
# optional comma-separated addresses to treat as known
export ROB_KNOWN_IPS=
```

The LaunchAgent starts the loop only. It does not embed a home network. Put those variables in the agent environment if you want them on every run.

5. Optional camera feed. If you already produce a JSON file with a `cameras` array (`name`, `online`, `recording`, `mac`, `last_activity`), point at it:

```sh
export RING_STATUS_JSON=/path/to/camera_status.json
```

Optional local files under `ops-center/data/` (gitignored once you create them):

- `camera-names.json` maps feed names to board labels
- `camera-order.json` is an array of board labels

6. Start the board:

```sh
bash scripts/run-board.sh
```

Open `http://127.0.0.1:8765/`. Copy `ops-center/status.example.json` to `ops-center/status.json` if you only want to preview the page before the publisher runs.

The snapshot does not read Wi-Fi passwords. It records the network as `connected` or `unknown`, not the network name.

## License

MIT. See LICENSE.
