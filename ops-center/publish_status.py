#!/usr/bin/env python3
"""Merge Ring + Mac snaps into ops-center status.json.

Events are APPENDED forever to data/events.jsonl — NEVER delete, truncate, or rotate.
Red/warn also append to data/alerts.jsonl forever.
Board "What changed" only *displays* the last 24h; storage has no cutoff.
"""
from __future__ import annotations
import json, time, os
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parent
RING = Path(os.environ.get("RING_STATUS_JSON", str(ROOT / "data" / "ring_camera_status.json")))
MAC = ROOT / 'data' / 'mac-snap.json'
HIST = ROOT / 'data' / 'history.jsonl'
EVENTS = ROOT / 'data' / 'events.jsonl'
ALERTS = ROOT / 'data' / 'alerts.jsonl'
ALERTS_JSON = ROOT / 'alerts.json'  # board history UI
OUT = ROOT / 'status.json'
PREV = ROOT / 'data' / 'prev_status.json'

def load_name_map():
    path = ROOT / "data" / "camera-names.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text())
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}

def load_order():
    path = ROOT / "data" / "camera-order.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text())
    except Exception:
        return []
    return [str(x) for x in data] if isinstance(data, list) else []

# Events older than this fall off the board (still kept in the file)
BOARD_WINDOW_H = 24
BOARD_MAX_LINES = 16

def load(p: Path):
    try:
        return json.loads(p.read_text())
    except Exception:
        return None

def ago(iso):
    if not iso:
        return None
    try:
        t = datetime.fromisoformat(iso.replace('Z','+00:00'))
        sec = int((datetime.now(timezone.utc) - t).total_seconds())
        if sec < 60: return f'{sec}s ago'
        if sec < 3600: return f'{sec//60}m ago'
        return f'{sec//3600}h ago'
    except Exception:
        return None

def pt_stamp(ts=None):
    # store UTC iso; display PT on board
    if ts is None:
        ts = time.time()
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    # America/Los_Angeles via fixed offset is wrong for DST; use zone if available
    try:
        from zoneinfo import ZoneInfo
        local = dt.astimezone(ZoneInfo('America/Los_Angeles'))
    except Exception:
        local = dt.astimezone(timezone(timedelta(hours=-7)))
    return local.strftime('%m-%d %H:%M')

def append_events(new_events):
    """Append ALL events forever. Red/warn also go to alerts.jsonl (permanent alert history)."""
    if not new_events:
        return
    EVENTS.parent.mkdir(parents=True, exist_ok=True)
    with EVENTS.open('a') as f:
        for e in new_events:
            if 'id' not in e:
                e['id'] = f"{int(e.get('ts', time.time()))}-{e.get('kind','x')}-{abs(hash(e.get('text','')))%10**8}"
            f.write(json.dumps(e) + '\n')
    alerts = [e for e in new_events if e.get('level') in ('bad', 'warn')]
    if alerts:
        with ALERTS.open('a') as f:
            for e in alerts:
                f.write(json.dumps(e) + '\n')

def rebuild_alerts_json(limit=2000):
    """Newest-first alerts.json for history UI. File on disk is never pruned."""
    rows = []
    seen = set()
    src = ALERTS if ALERTS.exists() else EVENTS
    if src.exists():
        for line in src.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except Exception:
                continue
            if e.get('level') not in ('bad', 'warn'):
                continue
            key = e.get('id') or f"{e.get('ts')}|{e.get('kind')}|{e.get('text')}"
            if key in seen:
                continue
            seen.add(key)
            rows.append(e)
    rows.sort(key=lambda e: float(e.get('ts') or 0), reverse=True)
    # display cap only — underlying jsonl is never trimmed
    shown = rows[:limit]
    out = {
        'updated': time.time(),
        'count': len(rows),
        'shown': len(shown),
        'retention': 'forever',
        'alerts': [
            {
                'id': e.get('id') or str(e.get('ts')),
                'ts': e.get('ts'),
                'when': pt_stamp(e.get('ts')),
                'level': e.get('level'),
                'kind': e.get('kind'),
                'text': e.get('text'),
            }
            for e in shown
        ],
    }
    tmp = ALERTS_JSON.with_suffix('.tmp')
    tmp.write_text(json.dumps(out, indent=2))
    tmp.replace(ALERTS_JSON)

def read_recent_events():
    if not EVENTS.exists():
        return []
    cutoff = time.time() - BOARD_WINDOW_H * 3600
    rows = []
    try:
        for line in EVENTS.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except Exception:
                continue
            if float(e.get('ts') or 0) >= cutoff:
                rows.append(e)
    except Exception:
        return []
    # newest last in file → reverse for display (newest first)
    rows.sort(key=lambda e: float(e.get('ts') or 0), reverse=True)
    return rows[:BOARD_MAX_LINES]


def cam_brief(name, r):
    note = (r.get('note') or '').strip()
    if r.get('recording'):
        extra = f'recording · {r["last_seen"]}' if r.get('last_seen') else 'recording'
        return (f'{note} · {extra}' if note else extra)[:48]
    if r.get('online') is True:
        return (note or 'online')[:48]
    if r.get('online') is False:
        return (note or 'offline')[:48]
    return (note or 'waiting')[:48]

def main():
    ring = load(RING) or {}
    mac = load(MAC) or {}
    prev = load(PREV) or {}

    by_full = {}
    for c in ring.get('cameras') or []:
        full = load_name_map().get(c.get('name'), c.get('name'))
        online = c.get('online')
        if online is True:
            state_online = True
        elif online is False:
            state_online = False
        else:
            state_online = None
        by_full[full] = {
            'name': full,
            'mac': (c.get('mac') or '').upper(),
            'online': state_online,
            'recording': bool(c.get('recording')),
            'last_seen': ago(c.get('last_activity')),
            'note': c.get('note') or '',
            'ip': None,
        }

    mac_rings = { (r.get('mac') or '').upper(): r for r in (mac.get('rings') or []) }
    for full, r in by_full.items():
        m = mac_rings.get(r['mac'])
        if m:
            r['ip'] = m.get('ip')
            if r['online'] is None and m.get('online') is not None:
                r['online'] = bool(m.get('online'))
            # LAN truth: if Mac sees device online, trust that over stale null
            if m.get('online') is True and r['online'] is not True:
                # don't override explicit Ring offline for daytime street unless Mac says up
                if r['online'] is None:
                    r['online'] = True
                    if not r['note']:
                        r['note'] = 'seen on LAN'

    # Also ensure configured camera entries from mac-only if Ring feed missing them
    for mr in (mac.get('rings') or []):
        name = mr.get('name')
        if name and name not in by_full:
            by_full[name] = {
                'name': name,
                'mac': (mr.get('mac') or '').upper(),
                'online': bool(mr.get('online')) if mr.get('online') is not None else None,
                'recording': False,
                'last_seen': None,
                'note': 'LAN probe',
                'ip': mr.get('ip'),
            }

    rings = []
    order = load_order() or list(by_full.keys())
    for name in order:
        r = by_full.get(name) or {'name': name, 'online': None, 'note': 'waiting for feed'}
        r['brief'] = cam_brief(name, r)
        rings.append(r)
    for name, r in by_full.items():
        if name not in order:
            r['brief'] = cam_brief(name, r)
            rings.append(r)

    link = mac.get('link') or {}
    rx = float(link.get('rx_mbps') or 0)
    tx = float(link.get('tx_mbps') or 0)
    wifi = mac.get('wifi') or {'ssid_hint': 'unknown'}

    unknowns_raw = mac.get('unknowns') or []
    known_ips = {ip.strip() for ip in os.environ.get("ROB_KNOWN_IPS", "").split(",") if ip.strip()}
    unknowns = []
    for u in unknowns_raw:
        if isinstance(u, dict) and (u.get('ip') or '') in known_ips:
            continue
        unknowns.append(u)
    flood = rx > 200 or tx > 80
    keeper_on = bool((ring.get('keeper') or {}).get('orchestrator_running'))
    threats = [
        {'label': 'Unknown LAN devices', 'state': 'bad' if unknowns else 'ok',
         'detail': f'{len(unknowns)} new device(s)' if unknowns else 'no unknown devices in the snap'},
        {'label': 'Traffic flood', 'state': 'bad' if flood else 'ok',
         'detail': f'{rx:.0f} down / {tx:.0f} up Mbps' if flood else 'under the flood thresholds'},
        {'label': 'Cameras', 'state': 'ok' if keeper_on else 'warn',
         'detail': 'recorder flag set' if keeper_on else 'no recorder flag in the feed'},
    ]

    defenses = [
        {'label': 'Mac snap', 'state': 'ok' if mac.get('ts') else 'warn',
         'detail': 'snapshot present' if mac.get('ts') else 'waiting for a Mac snapshot'},
        {'label': 'Camera feed', 'state': 'ok' if ring else 'warn',
         'detail': 'feed present' if ring else 'set RING_STATUS_JSON'},
    ]

    # --- durable event detection (diff vs prev) ---
    new_events = []
    now = time.time()
    prev_rings = {r['name']: r for r in (prev.get('rings') or [])}
    for r in rings:
        p = prev_rings.get(r['name']) or {}
        if p.get('online') is True and r.get('online') is False:
            new_events.append({
                'ts': now, 'level': 'bad', 'kind': 'cam_offline',
                'text': f"{r['name']} went OFFLINE",
            })
        if p.get('online') is False and r.get('online') is True:
            new_events.append({
                'ts': now, 'level': 'ok', 'kind': 'cam_online',
                'text': f"{r['name']} back ONLINE",
            })
        if r.get('recording') and not p.get('recording') and p:
            new_events.append({
                'ts': now, 'level': 'ok', 'kind': 'rec_start',
                'text': f"{r['name']} recording started",
            })
        if (not r.get('recording')) and p.get('recording'):
            new_events.append({
                'ts': now, 'level': 'warn', 'kind': 'rec_stop',
                'text': f"{r['name']} recording STOPPED",
            })

    prev_unknowns = set(json.dumps(u, sort_keys=True) if isinstance(u, dict) else str(u)
                        for u in (prev.get('_unknowns_raw') or []))
    cur_unknowns = [json.dumps(u, sort_keys=True) if isinstance(u, dict) else str(u) for u in unknowns]
    for u in cur_unknowns:
        if u not in prev_unknowns:
            new_events.append({
                'ts': now, 'level': 'bad', 'kind': 'unknown_device',
                'text': f"Unknown device on LAN: {u}",
            })

    prev_flood = bool((prev.get('_flags') or {}).get('flood'))
    if flood and not prev_flood:
        new_events.append({
            'ts': now, 'level': 'bad', 'kind': 'flood',
            'text': f"Traffic spike {rx:.0f}↓ / {tx:.0f}↑ Mbps",
        })
    if (not flood) and prev_flood:
        new_events.append({
            'ts': now, 'level': 'ok', 'kind': 'flood_clear',
            'text': 'Traffic spike cleared',
        })

    prev_threats = {t['label']: t.get('state') for t in (prev.get('threats') or [])}
    for t in threats:
        ps = prev_threats.get(t['label'])
        if ps == 'ok' and t['state'] in ('warn', 'bad'):
            new_events.append({
                'ts': now, 'level': t['state'], 'kind': 'threat',
                'text': f"{t['label']}: {t['detail']}",
            })
        if ps in ('warn', 'bad') and t['state'] == 'ok':
            new_events.append({
                'ts': now, 'level': 'ok', 'kind': 'threat_clear',
                'text': f"{t['label']} clear again",
            })

    append_events(new_events)

    recent = read_recent_events()
    if recent:
        changes = [f"{pt_stamp(e['ts'])}  {e.get('text','')}" for e in recent]
        # Sticky only for unresolved issues: skip bad events already cleared later
        last_bad = None
        cleared_kinds = set()
        for e in recent:  # newest first
            kind = e.get('kind') or ''
            level = e.get('level')
            if level == 'ok' and kind.endswith('_clear'):
                cleared_kinds.add(kind[:-6])  # threat_clear -> threat; flood_clear -> flood
                continue
            if level == 'ok' and kind in ('cam_online',):
                # cam_online clears matching cam_offline if same camera text stem
                continue
            if level in ('bad', 'warn'):
                base = kind[:-8] if kind.endswith('_offline') else kind
                # unknown_device / threat cleared by threat_clear; flood by flood_clear
                if kind in ('unknown_device', 'threat') and 'threat' in cleared_kinds:
                    continue
                if kind == 'flood' and 'flood' in cleared_kinds:
                    continue
                if kind == 'cam_offline':
                    # cleared if a newer cam_online exists for same name
                    name = (e.get('text') or '').replace(' went OFFLINE', '')
                    if any(x.get('kind')=='cam_online' and name in (x.get('text') or '') for x in recent if float(x.get('ts') or 0) >= float(e.get('ts') or 0)):
                        continue
                last_bad = e
                break
        # Also: if live unknowns empty, never sticky an unknown_device
        if last_bad and last_bad.get('kind') == 'unknown_device' and not unknowns:
            last_bad = None
        sticky = {
            'active': bool(last_bad),
            'level': (last_bad or {}).get('level') or 'ok',
            'text': (last_bad or {}).get('text') or '',
            'when': pt_stamp(last_bad['ts']) if last_bad else None,
        }
    else:
        changes = ['Quiet — no alerts in the last 24h.']
        sticky = {'active': False, 'level': 'ok', 'text': '', 'when': None}

    status = {
        'link': {'rx_mbps': rx, 'tx_mbps': tx},
        'wifi': wifi,
        'rings': rings,
        'defenses': defenses,
        'threats': threats,
        'changes': changes,
        'sticky_alert': sticky,
        'keeper': ring.get('keeper') or {},
        '_sweep': time.strftime('%Y-%m-%d %H:%M PT'),
        '_ring_updated': ring.get('updated_at'),
        '_mac_ts': mac.get('ts'),
        '_unknowns_raw': unknowns,
        '_flags': {'flood': flood},
        '_events_appended': len(new_events),
        'alert_count': sum(1 for _ in (ALERTS.read_text().splitlines() if ALERTS.exists() else []) if _.strip()),
    }
    ROOT.joinpath('data').mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix('.tmp')
    tmp.write_text(json.dumps(status, indent=2))
    tmp.replace(OUT)
    PREV.write_text(json.dumps(status, indent=2))
    with HIST.open('a') as f:
        f.write(json.dumps({'ts': now, 'rx': rx, 'tx': tx, 'rings': {r['name']: r.get('online') for r in rings}}) + '\n')
    rebuild_alerts_json()
    print('published', OUT, 'new_events', len(new_events), 'board_events', len(recent))

if __name__ == '__main__':
    main()
