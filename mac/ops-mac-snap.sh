#!/bin/bash
# Lightweight Mac ops snapshot for Rob ops board. No WiFi passwords. No GUI focus.
exec /usr/bin/python3 - "$@" << 'PY'
#!/usr/bin/env python3
"""ops-mac-snap: wifi/link/arp/ring status JSON for Rob ops board."""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

DIR = Path.home() / "Library/Application Support/rob"
OUT = DIR / "ops-mac-snap.json"
STATE = DIR / "ops-mac-snap.state"
TMP = DIR / "ops-mac-snap.json.tmp"
IFACE = os.environ.get("ROB_IFACE", "en0")
GATEWAY_IP = os.environ.get("ROB_GATEWAY", "192.0.2.1")
LAN_PREFIX = os.environ.get("ROB_LAN_PREFIX", "192.0.2.")

def load_rings():
    """Cameras come from cameras.json next to this script, not from the repo."""
    path = Path(os.environ["ROB_CAMERAS"]) if os.environ.get("ROB_CAMERAS") else (DIR / "cameras.json")
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text())
    except Exception:
        return []
    rings = []
    for row in data if isinstance(data, list) else []:
        name = str(row.get("name") or "").strip()
        mac = normalize_mac(str(row.get("mac") or ""))
        ip = str(row.get("ip") or "").strip()
        if name and mac and ip:
            rings.append({"name": name, "mac": mac, "ip": ip})
    return rings


def run(cmd, timeout=8):
    try:
        return subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL, timeout=timeout)
    except Exception:
        return ""


def normalize_mac(raw: str) -> str:
    if not raw:
        return ""
    parts = re.split(r"[:\-]", raw.strip())
    out = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        try:
            out.append(f"{int(p, 16):02X}")
        except ValueError:
            return ""
    return ":".join(out) if len(out) == 6 else ""


def iface_ip() -> str:
    return run(["ipconfig", "getifaddr", IFACE], timeout=3).strip()


def iface_mac() -> str:
    out = run(["ifconfig", IFACE], timeout=3)
    m = re.search(r"\bether\s+([0-9a-fA-F:]+)", out)
    return normalize_mac(m.group(1)) if m else ""


def wifi_info():
    """ssid_hint connected|unknown. Does not record the network name."""
    ssid_hint = "unknown"
    tx_rate = None
    # CoreWLAN via swift — no GUI focus; SSID often privacy-redacted
    cw = run(
        [
            "swift",
            "-e",
            'import CoreWLAN; let i=CWWiFiClient.shared().interface(); '
            'print("SSID="+String(i?.ssid() ?? "")); '
            'print("RATE="+String(i?.transmitRate() ?? -1))',
        ],
        timeout=12,
    )
    ssid_raw = ""
    rate_raw = ""
    for ln in cw.splitlines():
        ln = ln.strip()
        if ln.startswith("SSID="):
            ssid_raw = ln[5:]
        elif ln.startswith("RATE="):
            rate_raw = ln[5:]
    if ssid_raw and ssid_raw.lower() != "nil":
        ssid_hint = "connected"
    try:
        r = float(rate_raw)
        if r >= 0:
            tx_rate = int(r) if r == int(r) else r
    except (TypeError, ValueError):
        pass
    ip = iface_ip()
    return ssid_hint, tx_rate


def link_bytes():
    out = run(["netstat", "-I", IFACE, "-b"], timeout=3)
    # Header + first data row (Link)
    for ln in out.splitlines()[1:]:
        parts = ln.split()
        if len(parts) >= 10 and parts[0] == IFACE:
            try:
                return int(parts[6]), int(parts[9])  # Ibytes, Obytes
            except ValueError:
                continue
    return 0, 0


def compute_mbps(now, rx, tx):
    rx_mbps = 0.0
    tx_mbps = 0.0
    if STATE.exists():
        try:
            prev_ts, prev_rx, prev_tx = STATE.read_text().strip().split()
            prev_ts, prev_rx, prev_tx = int(prev_ts), int(prev_rx), int(prev_tx)
            dt = now - prev_ts
            if 0 < dt < 600:
                rx_mbps = round((rx - prev_rx) * 8 / dt / 1e6, 3)
                tx_mbps = round((tx - prev_tx) * 8 / dt / 1e6, 3)
                if rx_mbps < 0:
                    rx_mbps = 0.0
                if tx_mbps < 0:
                    tx_mbps = 0.0
        except Exception:
            pass
    STATE.write_text(f"{now} {rx} {tx}\n")
    return rx_mbps, tx_mbps


def parse_arp():
    """Return dict ip -> {mac, online} for ROB_LAN_PREFIX entries."""
    out = run(["arp", "-an"], timeout=5)
    table = {}
    for ln in out.splitlines():
        m = re.search(r"\((\d+\.\d+\.\d+\.\d+)\)\s+at\s+(\S+)", ln)
        if not m:
            continue
        ip, mac_raw = m.group(1), m.group(2)
        if not ip.startswith(LAN_PREFIX):
            continue
        if "incomplete" in ln or mac_raw == "(incomplete)":
            table[ip] = {"mac": "", "online": False}
            continue
        mac = normalize_mac(mac_raw)
        if mac:
            table[ip] = {"mac": mac, "online": True}
    return table


def ping_ok(ip: str) -> bool:
    try:
        r = subprocess.run(
            ["ping", "-c", "1", "-t", "1", ip],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3,
        )
        return r.returncode == 0
    except Exception:
        return False


def main():
    DIR.mkdir(parents=True, exist_ok=True)
    now = int(time.time())

    ssid_hint, tx_rate = wifi_info()
    rx_bytes, tx_bytes = link_bytes()
    rx_mbps, tx_mbps = compute_mbps(now, rx_bytes, tx_bytes)

    rings = load_rings()
    # Ping configured cameras in parallel first to populate ARP
    with ThreadPoolExecutor(max_workers=max(1, len(rings) or 1)) as ex:
        ping_results = {ip: fut.result() for ip, fut in {
            r["ip"]: ex.submit(ping_ok, r["ip"]) for r in rings
        }.items()}

    arp = parse_arp()

    hosts = []
    for ip in sorted(arp.keys(), key=lambda x: list(map(int, x.split(".")))):
        ent = arp[ip]
        if ent["mac"]:
            hosts.append({"ip": ip, "mac": ent["mac"], "online": True})

    rings_out = []
    for r in rings:
        ip, mac = r["ip"], r["mac"]
        online = bool(ping_results.get(ip))
        if not online:
            ent = arp.get(ip)
            if ent and ent.get("online") and ent.get("mac"):
                online = True
        rings_out.append({"name": r["name"], "mac": mac, "ip": ip, "online": online})

    self_ip = iface_ip()
    self_mac = iface_mac()
    known_ips = {GATEWAY_IP, self_ip} | {r["ip"] for r in rings}
    known_macs = {r["mac"] for r in rings}
    if self_mac:
        known_macs.add(self_mac)
    # gateway mac if present
    gw = arp.get(GATEWAY_IP)
    if gw and gw.get("mac"):
        known_macs.add(gw["mac"])

    unknowns = []
    for h in hosts:
        if h["ip"] in known_ips:
            continue
        if h["mac"] in known_macs:
            continue
        unknowns.append(h)

    doc = {
        "ts": now,
        "wifi": {"device": IFACE, "ssid_hint": ssid_hint, "tx_rate": tx_rate},
        "link": {
            "rx_bytes": rx_bytes,
            "tx_bytes": tx_bytes,
            "rx_mbps": rx_mbps,
            "tx_mbps": tx_mbps,
        },
        "hosts": hosts,
        "rings": rings_out,
        "unknowns": unknowns,
    }
    TMP.write_text(json.dumps(doc, indent=2) + "\n")
    os.replace(TMP, OUT)


if __name__ == "__main__":
    main()
PY
