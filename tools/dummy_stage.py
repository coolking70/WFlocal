#!/usr/bin/env python3
"""Give challenge quest 1 a mob room that leads into its boss room.

Why the zako placed by dummy_zone.py never appeared: a stage's rooms live in its
*terrain* file, one layer per wave, and enemies only spawn where that layer has
SPAWN objects.

    tutorial_5 terrain   layer '0'  BOUNDS y=366..686  SPAWN3 x6, GATE, TRANSIT
                         layer '1'  BOUNDS y=16..336   CUSTOM_POSITION p0..p3
    tutorial_5 zone      wave 0     objective ZakoKill(10), zako01..06
                         wave 1     objective BossClear,   boss1 maou_tutorial

    main_3_6_2_trial     layer '0'  BOUNDS y=134..454  CUSTOM_POSITION (kraken)
                         wave 0     objective BossClear,  boss1 kraken_single

One layer, no SPAWN objects, so the six mobs had nowhere to stand and the
console had nothing to complain about.

This builds the two-room shape the tutorial uses:

    layer '0'  <- tutorial_5's mob room, copied whole
    layer '1'  <- the shipped kraken room, renamed

The mob room is copied rather than synthesised because every object in it comes
from a room the game actually runs - bounds, walls, coffins, the gate and the
transit that carry the ball to the next room. A hand-built room would be a pile
of guesses about objects whose semantics are not established.

The copy is a new asset under battle/terrain/wfmod/, registered with
wfmod/runtime.js; the shipped terrain is not touched. field_data and zone are
master edits, each reversible with --revert.

    python3 tools/dummy_stage.py --build --zako enemy_eviltower_tutorial --count 6
    python3 tools/dummy_stage.py --revert
"""

import argparse
import copy
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import orderedmap  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TRIAL = ROOT / "WFTest" / "assets" / "trial" / "production"
PROD = ROOT / "WFTest" / "assets" / "production"
MASTER = TRIAL / "master" / "battle"
RUNTIME = ROOT / "WFTest" / "wfmod" / "runtime.js"
BASELINE = ROOT / "tools" / "baseline"

ZONE = MASTER / "zone.orderedmap"
FIELD_DATA = MASTER / "field_data.orderedmap"

# Which zone a quest runs is not guessable from the quest's position in the menu.
# Everything here is keyed off the zone name that ZoneMapTools is actually handed,
# which ?wfdev=trace reports:
#
#   quest 111/1/1  VS ガーディアンゴーレム  main_2_9_5        <- first in the list
#   quest 111/1/2  VS クラーケン           main_3_6_2_trial
#   quest 111/1/3  VS 妖狐                main_6_6_2
#
DEFAULT_ZONE = "main_2_9_5"
MOB_ROOM_TERRAIN = PROD / "battle/terrain/tutorial/tutorial_01_01_04.json"
FORK_RELATIVE = "battle/terrain/wfmod/wfmod_dummy_stage"

# The asset roots are disjoint per file: chapter_02 and chapter_06 terrains exist
# only under assets/production, chapter_03 only under assets/trial/production. The
# fork must land in the same root as the terrain it replaces, or the game silently
# loads the shipped one - no error, just the old content.
ROOTS = (PROD, TRIAL)


def terrain_of(zone_key):
    """(source terrain path, its root) from field_data, not from a guess."""
    entries = load_master(FIELD_DATA)
    entry = find(entries, zone_key)
    if entry is None:
        sys.exit(f"field_data has no {zone_key}; have: "
                 f"{', '.join(e['key'] for e in entries)}")
    relative = row_columns(entry)[1] + ".json"
    for root in ROOTS:
        if (root / relative).exists():
            return relative, root
    sys.exit(f"terrain {relative} for {zone_key} is in neither asset root")

# Object ids are unique within a terrain; the copied room keeps its own numbering
# from another file, so push it clear of anything in the host terrain.
ID_OFFSET = 100000


def backup(path):
    return BASELINE / (path.name + ".original")


def save_original(path):
    target = backup(path)
    if not target.exists():
        target.write_bytes(path.read_bytes())
        print(f"  saved {target.name}")


def restore(path):
    target = backup(path)
    if target.exists():
        path.write_bytes(target.read_bytes())
        target.unlink()
        print(f"  restored {path.name}")
        return True
    return False


def load_master(path):
    return orderedmap.decode(path.read_bytes())


def find(entries, key):
    for entry in entries:
        if entry["key"] == key:
            return entry
    return None


def row_columns(entry):
    return entry["value"].split("\n")[0].split(",")


def set_row(entry, cols):
    lines = entry["value"].split("\n")
    lines[0] = ",".join(cols)
    entry["value"] = "\n".join(lines)


def mob_room_layer(count):
    """tutorial_5's mob room, renumbered, trimmed to `count` spawn points."""
    source = json.loads(MOB_ROOM_TERRAIN.read_text(encoding="utf-8"))
    layer = None
    for candidate in source["layers"]:
        objects = candidate.get("objects")
        if objects and any(str(o.get("type", "")).startswith("SPAWN") for o in objects):
            layer = copy.deepcopy(candidate)
            break
    if layer is None:
        sys.exit(f"{MOB_ROOM_TERRAIN.name} has no layer with SPAWN objects")

    spawns = [o for o in layer["objects"] if str(o.get("type", "")).startswith("SPAWN")]
    if count > len(spawns):
        sys.exit(f"the tutorial mob room has {len(spawns)} spawn points, asked for {count}")
    keep = set(id(o) for o in spawns[:count])
    layer["objects"] = [o for o in layer["objects"]
                        if not str(o.get("type", "")).startswith("SPAWN") or id(o) in keep]
    for obj in layer["objects"]:
        if isinstance(obj.get("id"), int):
            obj["id"] += ID_OFFSET
    layer["name"] = "0"
    return layer, len(spawns)


def build(zone_key, zako, count):
    print("terrain")
    model, root = terrain_of(zone_key)
    source_terrain = root / model
    fork_file = root / (FORK_RELATIVE + ".json")
    print(f"  {zone_key} currently uses {model}")
    print(f"  asset root: {root.relative_to(ROOT)}")
    terrain = json.loads(source_terrain.read_text(encoding="utf-8"))
    if len(terrain["layers"]) != 1:
        sys.exit(f"expected 1 layer in {source_terrain.name}, found {len(terrain['layers'])}")
    boss_room = copy.deepcopy(terrain["layers"][0])
    boss_room["name"] = "1"
    room, available = mob_room_layer(count)
    terrain["layers"] = [room, boss_room]
    fork_file.parent.mkdir(parents=True, exist_ok=True)
    fork_file.write_text(json.dumps(terrain, ensure_ascii=False), encoding="utf-8")
    print(f"  layer '0' mob room from {MOB_ROOM_TERRAIN.name} "
          f"({count} of {available} spawn points)")
    print(f"  layer '1' boss room from {source_terrain.name}")
    print(f"  wrote {fork_file.relative_to(ROOT)}")

    print("field_data")
    save_original(FIELD_DATA)
    entries = load_master(FIELD_DATA)
    entry = find(entries, zone_key)
    if entry is None:
        sys.exit(f"field_data has no {zone_key}")
    cols = row_columns(entry)
    cols[1] = FORK_RELATIVE
    set_row(entry, cols)
    FIELD_DATA.write_bytes(orderedmap.encode(entries))
    print(f"  {zone_key} terrain -> {FORK_RELATIVE}")

    print("zone")
    save_original(ZONE)
    entries = load_master(ZONE)
    entry = find(entries, zone_key)
    if entry is None or entry["kind"] != "map":
        sys.exit(f"zone {zone_key} missing or not a nested table")
    waves = entry["entries"]
    boss_wave = copy.deepcopy(waves[0])
    boss_wave["key"] = "1"
    # The boss wave keeps the shipped row exactly, minus any zako left by an
    # earlier dummy_zone.py run - those belong to the mob wave now.
    cols = row_columns(boss_wave)
    for slot in range(10):
        cols[2 + slot * 2] = "(None)"
        cols[3 + slot * 2] = "(None)"
    cols[0], cols[1] = "1", ""
    set_row(boss_wave, cols)

    mob_wave = copy.deepcopy(boss_wave)
    mob_wave["key"] = "0"
    cols = row_columns(mob_wave)
    cols[0], cols[1] = "0", str(count)          # objective: ZakoKill(count)
    for slot in range(count):
        cols[2 + slot * 2] = zako
        cols[3 + slot * 2] = "(None)"
    for at in (22, 24, 26):                     # no boss in the mob room
        cols[at], cols[at + 1] = "(None)", "(None)"
    set_row(mob_wave, cols)

    entry["entries"] = [mob_wave, boss_wave]
    ZONE.write_bytes(orderedmap.encode(entries))
    print(f"  wave 0  ZakoKill({count})  {count} x {zako}")
    print("  wave 1  BossClear    (the shipped boss row)")

    register(FORK_RELATIVE + ".json", model)
    print("\nNow the quest is a mob room that leads into the kraken room, which is the "
          "shape the tutorial already uses.")


def register(path, model):
    text = RUNTIME.read_text(encoding="utf-8")
    marker = "\tvar ADDED_ASSETS = ["
    start = text.index(marker)
    end = text.index("\t];", start)
    if path in text[start:end]:
        print("runtime.js already registers the forked terrain")
        return
    entry = f'\n\t\t["{path}",\n\t\t\t"{model}"],'
    RUNTIME.write_text(text[:start + len(marker)] + entry + text[start + len(marker):end] +
                       text[end:], encoding="utf-8")
    print(f"runtime.js registers {path}")
    subprocess.run([sys.executable, str(ROOT / "tools" / "stamp_assets.py")], check=True)


def revert():
    for path in (ZONE, FIELD_DATA):
        if not restore(path):
            print(f"  {path.name} had no backup, left alone")
    text = RUNTIME.read_text(encoding="utf-8")
    import re
    pattern = re.compile(r'\n\t\t\["' + re.escape(FORK_RELATIVE) + r'\.json",\n\t\t\t"[^"]+"\],')
    if pattern.search(text):
        RUNTIME.write_text(pattern.sub("", text), encoding="utf-8")
        print("  removed the terrain from runtime.js ADDED_ASSETS")
        subprocess.run([sys.executable, str(ROOT / "tools" / "stamp_assets.py")], check=True)
    for root in ROOTS:
        fork = root / (FORK_RELATIVE + ".json")
        if fork.exists():
            fork.unlink()
            print(f"  removed {fork.relative_to(ROOT)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--zone", default=DEFAULT_ZONE,
                    help="zone key as reported by ?wfdev=trace on ZoneMapTools")
    ap.add_argument("--zako", default="enemy_eviltower_tutorial")
    ap.add_argument("--count", type=int, default=6)
    args = ap.parse_args()
    if args.revert:
        revert()
        return 0
    if not args.build:
        sys.exit("pass --build or --revert")
    build(args.zone, args.zako, args.count)
    return 0


if __name__ == "__main__":
    sys.exit(main())
