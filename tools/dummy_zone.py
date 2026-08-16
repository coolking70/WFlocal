#!/usr/bin/env python3
"""Put practice mobs into a battle zone, so hit-area geometry becomes observable.

Hit areas are never drawn - ActionHitArea builds a physics shape, not a display
object. The only visible consequence of a skill's range is which enemies take
damage, and a quest with a single boss cannot show it: every shape tested so far
contains that one boss, so every shape looks identical.

Several enemies spread across the field turn range into something you can see.

A zone row (ZoneValues) is:

    col 0,1   objective: '0' ZakoKill(n) | '1' BossClear | '2' Unspecified
    col 2..21 zako01..zako10, each a pair (id, interval)
    col 22..27 boss1..boss3, each a pair (level, id)

`interval` is the respawn spacing; '(None)' means the mob appears once.

    python3 tools/dummy_zone.py --zone main_3_6_2_trial --list
    python3 tools/dummy_zone.py --zone main_3_6_2_trial --fill enemy_eviltower_tutorial --count 6
    python3 tools/dummy_zone.py --zone main_3_6_2_trial --revert

The four *_tutorial zako are the only ones whose pixel art the demo ships; the
two in the non-bundled general_zako table point at character/evil_* files that
are not in the tree. Nothing here invents an enemy - it places shipped ones.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import orderedmap  # noqa: E402
from master_schema import read_rows  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MASTER = ROOT / "WFTest" / "assets" / "trial" / "production" / "master" / "battle"
ZONE = MASTER / "zone.orderedmap"
ZAKO = MASTER / "zako" / "general_zako_iosbundled.orderedmap"

ZAKO_SLOTS = 10
ZAKO_FIRST_COLUMN = 2
# The backup lives outside the served tree. Anything under WFTest/ is checked
# against the baseline manifest, and a stray copy of a master table there is
# indistinguishable from an accidental edit.
BACKUP = ROOT / "tools" / "baseline" / "zone.orderedmap.original"


def known_zako():
    return sorted({path.split("/")[0] for path, _ in read_rows(ZAKO)})


def zone_rows(entries, key):
    for entry in entries:
        if entry["key"] != key:
            continue
        if entry["kind"] != "map":
            sys.exit(f"zone {key} is not a nested table")
        return entry["entries"]
    return None


def columns(entry):
    return entry["value"].split("\n")[0].split(",")


def write_columns(entry, cols):
    lines = entry["value"].split("\n")
    lines[0] = ",".join(cols)
    entry["value"] = "\n".join(lines)


def describe(cols):
    zako = []
    for slot in range(ZAKO_SLOTS):
        at = ZAKO_FIRST_COLUMN + slot * 2
        if at < len(cols) and cols[at] != "(None)":
            zako.append(f"{cols[at]}(interval={cols[at + 1]})")
    boss = []
    for at in (22, 24, 26):
        if at + 1 < len(cols) and cols[at] != "(None)":
            boss.append(f"{cols[at + 1]}(level={cols[at]})")
    return zako, boss


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zone", required=True)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--fill", help="zako id to place in the empty slots")
    ap.add_argument("--count", type=int, default=6)
    ap.add_argument("--interval", default="(None)", help="respawn spacing, or (None) for once")
    ap.add_argument("--revert", action="store_true")
    args = ap.parse_args()

    if args.revert:
        if not BACKUP.exists():
            sys.exit("no backup to restore; this zone was never modified by this tool")
        ZONE.write_bytes(BACKUP.read_bytes())
        BACKUP.unlink()
        print(f"restored {ZONE.relative_to(ROOT)} and removed the backup")
        return 0

    entries = orderedmap.decode(ZONE.read_bytes())
    rows = zone_rows(entries, args.zone)
    if rows is None:
        sys.exit(f"zone {args.zone!r} not found in {ZONE.name}; "
                 f"have: {', '.join(e['key'] for e in entries)}")

    if args.list or not args.fill:
        print(f"zone {args.zone}  ({len(rows)} wave(s))")
        for wave in rows:
            zako, boss = describe(columns(wave))
            print(f"  wave {wave['key']}  zako={zako or '-'}  boss={boss or '-'}")
        print("\nzako ids the demo ships assets for:")
        for name in known_zako():
            print(f"  {name}")
        return 0

    if args.fill not in known_zako():
        sys.exit(f"{args.fill!r} is not in {ZAKO.name}; that means the demo ships no art "
                 f"for it and placing it would fail with ClientError 8100")
    if args.count > ZAKO_SLOTS:
        sys.exit(f"a zone has {ZAKO_SLOTS} zako slots, asked for {args.count}")

    # Keep one pristine copy, so --revert does not depend on remembering what was
    # there. The zone table is shipped data; every other edit in this project is
    # reversible and this one should be too.
    if not BACKUP.exists():
        BACKUP.write_bytes(ZONE.read_bytes())
        print(f"saved {BACKUP.name}")

    for wave in rows:
        cols = columns(wave)
        while len(cols) < 34:
            cols.append("")
        for slot in range(args.count):
            at = ZAKO_FIRST_COLUMN + slot * 2
            cols[at] = args.fill
            cols[at + 1] = args.interval
        write_columns(wave, cols)
        zako, boss = describe(cols)
        print(f"  wave {wave['key']}  zako={zako}  boss={boss or '-'}")

    ZONE.write_bytes(orderedmap.encode(entries))
    print(f"\nwrote {ZONE.relative_to(ROOT)}")
    print("The objective column is untouched, so the quest still ends the way it did.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
