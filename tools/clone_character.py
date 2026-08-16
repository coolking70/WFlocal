#!/usr/bin/env python3
"""Clone an official character to a WFMod id, across every table that keys on it.

The point is the minimal loop for roadmap R3: get a new character id all the way
into a battle before any original art or skill data exists. The clone keeps the
source's string_id, so every asset path still resolves to shipped art and no new
files are needed.

Tables that key on a character id (found by scanning, not assumed):

    character/character                     the row itself
    character/character_text                name and flavour text
    character/character_status              stat curve, keyed <id>/<level>
    character/character_speech              voice lines
    character/character_gacha_sound         gacha audio
    character/full_shot_image_attribute     portrait metadata
    generated/character_image               image references
    generated/mana_board                    board layout
    mana_board/mana_node                    board nodes
    mana_board/upskill                      board skill upgrades
    ability/leader_ability                  leader ability, keyed by character id
    skill_preview/skill_preview_character   preview scene

    python3 tools/clone_character.py --from 121001 --to 129001 --name-prefix "WFMOD "
    python3 tools/clone_character.py --from 121001 --to 129001 --revert

Writes the master tables in place. `tools/verify_tree.py` will list them as
modified; that is expected and the reason is recorded there.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import orderedmap  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MASTER = ROOT / "WFTest" / "assets" / "trial" / "production" / "master"

# Every table whose keys start with a character id.
TABLES = [
    "character/character.orderedmap",
    "character/character_text.orderedmap",
    "character/character_status.orderedmap",
    "character/character_speech.orderedmap",
    "character/character_gacha_sound.orderedmap",
    "character/full_shot_image_attribute.orderedmap",
    "generated/character_image.orderedmap",
    "generated/mana_board.orderedmap",
    "mana_board/mana_node.orderedmap",
    "mana_board/upskill.orderedmap",
    "ability/leader_ability.orderedmap",
    "skill_preview/skill_preview_character.orderedmap",
]

# character.orderedmap columns, from reverse/master_schema.json (CharacterValues).
COL_LEADER_ABILITY_ID = 9
COL_IDENTITY_CHARACTER_ID = 15


def load(path):
    return orderedmap.decode(path.read_bytes())


def save(path, entries):
    path.write_bytes(orderedmap.encode(entries))


def clone_entries(entries, source, target, transform=None):
    """Copy every entry keyed `source` (or `source/...`) to the target id.

    Returns (new entries, how many were copied). Existing target entries are
    replaced so the tool is idempotent.
    """
    kept = [e for e in entries if e["key"] != target and not e["key"].startswith(target + "/")]
    copies = []
    for entry in kept:
        key = entry["key"]
        if key != source and not key.startswith(source + "/"):
            continue
        copy = json_clone(entry)
        copy["key"] = target + key[len(source):]
        if transform:
            transform(copy)
        copies.append(copy)
    return kept + copies, len(copies)


def json_clone(entry):
    import copy as _copy
    return _copy.deepcopy(entry)


def edit_row(entry, index, value):
    """Set one CSV column of a `row` entry, leaving everything else untouched."""
    if entry["kind"] != "row":
        return
    lines = entry["value"].split("\n")
    columns = lines[0].split(",")
    if index < len(columns):
        columns[index] = value
        lines[0] = ",".join(columns)
        entry["value"] = "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="source", required=True)
    ap.add_argument("--to", dest="target", required=True)
    ap.add_argument("--name-prefix", default="",
                    help="prepended to the cloned character's name so it is identifiable in game")
    ap.add_argument("--revert", action="store_true", help="remove the clone instead")
    args = ap.parse_args()

    total = 0
    for relative in TABLES:
        path = MASTER / relative
        if not path.exists():
            print(f"  skip   {relative} (missing)")
            continue
        entries = load(path)
        before = len(entries)

        if args.revert:
            entries = [e for e in entries
                       if e["key"] != args.target and not e["key"].startswith(args.target + "/")]
            removed = before - len(entries)
            if removed:
                save(path, entries)
                print(f"  -{removed:<4} {relative}")
                total += removed
            continue

        def transform(entry, relative=relative):
            if relative == "character/character.orderedmap":
                edit_row(entry, COL_LEADER_ABILITY_ID, args.target)
                edit_row(entry, COL_IDENTITY_CHARACTER_ID, args.target)
            if relative == "character/character_text.orderedmap" and args.name_prefix:
                if entry["kind"] == "row":
                    columns = entry["value"].split("\n")[0].split(",")
                    if columns and not columns[0].startswith(args.name_prefix):
                        edit_row(entry, 0, args.name_prefix + columns[0])

        entries, copied = clone_entries(entries, args.source, args.target, transform)
        if copied:
            save(path, entries)
            print(f"  +{copied:<4} {relative}")
            total += copied
        else:
            print(f"  0     {relative} (no entries for {args.source})")

    verb = "removed" if args.revert else "cloned"
    print(f"\n{verb} {total} entries  {args.source} -> {args.target}")
    if not args.revert:
        print("\nThe clone keeps the source string_id, so it reuses the shipped art.")
        print("Put it in a party to see it in battle, e.g. with tools/set_party.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
