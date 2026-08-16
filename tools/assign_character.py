#!/usr/bin/env python3
"""Grant a character to a player and put it in a party slot.

Two master tables carry the player side of a character, and both nest under the
player id:

    player/player_character   <player>/<character_id> -> character_level
    player/player_party       <player>/<party>        -> main1..3, unison1..3

Challenge quests pick their party by quest number (quest 1 uses party 1), so
putting a character in party 1 slot main1 makes it the leader of the first
challenge quest.

    python3 tools/assign_character.py --player 4 --party 1 --slot main1 \
        --character 129001 --level 20
    python3 tools/assign_character.py --player 4 --party 1 --slot main1 --restore

`--restore` puts back whatever the slot held before, recorded alongside the
change, and revokes the granted character.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import orderedmap  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MASTER = ROOT / "WFTest" / "assets" / "trial" / "production" / "master"
CHARACTERS = MASTER / "player" / "player_character.orderedmap"
PARTIES = MASTER / "player" / "player_party.orderedmap"
STATE = ROOT / "tools" / "baseline" / "assign_character.state.json"

SLOTS = {
    "main1": 0, "main2": 1, "main3": 2,
    "unison1": 3, "unison2": 4, "unison3": 5,
}


def load(path):
    return orderedmap.decode(path.read_bytes())


def save(path, entries):
    path.write_bytes(orderedmap.encode(entries))


def find(entries, key):
    for entry in entries:
        if entry["key"] == key:
            return entry
    return None


def nested(entries, key):
    """The child list of a nested entry, or None if it is not a table."""
    entry = find(entries, key)
    if entry is None or entry["kind"] != "map":
        return None
    return entry["entries"]


def grant(player, character, level):
    entries = load(CHARACTERS)
    children = nested(entries, player)
    if children is None:
        sys.exit(f"player {player} not found in player_character")
    existing = find(children, character)
    if existing:
        existing["value"] = str(level)
        action = "updated"
    else:
        children.append({"key": character, "kind": "row", "value": str(level)})
        action = "granted"
    save(CHARACTERS, entries)
    print(f"  {action}  player {player} character {character} level {level}")


def revoke(player, character):
    entries = load(CHARACTERS)
    children = nested(entries, player)
    if children is None:
        return
    before = len(children)
    children[:] = [c for c in children if c["key"] != character]
    if len(children) != before:
        save(CHARACTERS, entries)
        print(f"  revoked  player {player} character {character}")


def set_slot(player, party, slot, character):
    """Write one party slot, returning what it held before."""
    entries = load(PARTIES)
    children = nested(entries, player)
    if children is None:
        sys.exit(f"player {player} not found in player_party")
    row = find(children, party)
    if row is None or row["kind"] != "row":
        sys.exit(f"party {player}/{party} not found")
    lines = row["value"].split("\n")
    columns = lines[0].split(",")
    index = SLOTS[slot]
    if index >= len(columns):
        sys.exit(f"party row has {len(columns)} columns, no slot {slot}")
    previous = columns[index]
    columns[index] = character
    lines[0] = ",".join(columns)
    row["value"] = "\n".join(lines)
    save(PARTIES, entries)
    print(f"  party {player}/{party} {slot}: {previous} -> {character}")
    return previous


def read_state():
    return json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}


def write_state(state):
    STATE.write_text(json.dumps(state, indent=1) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--player", default="4")
    ap.add_argument("--party", default="1")
    ap.add_argument("--slot", default="main1", choices=sorted(SLOTS))
    ap.add_argument("--character")
    ap.add_argument("--level", default="20")
    ap.add_argument("--restore", action="store_true")
    args = ap.parse_args()

    key = f"{args.player}/{args.party}/{args.slot}"
    state = read_state()

    if args.restore:
        record = state.get(key)
        if not record:
            sys.exit(f"nothing recorded for {key}")
        set_slot(args.player, args.party, args.slot, record["previous"])
        revoke(args.player, record["character"])
        state.pop(key)
        write_state(state)
        print(f"\nrestored {key}")
        return 0

    if not args.character:
        sys.exit("--character is required unless --restore is given")

    grant(args.player, args.character, args.level)
    previous = set_slot(args.player, args.party, args.slot, args.character)
    # Only record the original occupant, so repeated runs stay revertible.
    if key not in state:
        state[key] = {"previous": previous, "character": args.character}
        write_state(state)
    print(f"\nassigned {args.character} to {key}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
