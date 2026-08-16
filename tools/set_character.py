#!/usr/bin/env python3
"""Edit a character's text and stat curve.

Two tables, both keyed by character id:

    character/character_text     name, description, nickname, skill text,
                                 leader ability name, voice actor
    character/character_status   nested <id>/<level> -> hp, atk

The stat table stores anchor levels only - the shipped characters use 1, 10, 80
and 100 - and the game interpolates between them.

    python3 tools/set_character.py --character 129001 --show
    python3 tools/set_character.py --character 129001 \
        --name "WFMOD 001" --nickname "試作体"
    python3 tools/set_character.py --character 129001 --stat 1=60/16 --stat 100=4000/500

Only the fields given are touched, so this is safe to run repeatedly.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import orderedmap  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MASTER = ROOT / "WFTest" / "assets" / "trial" / "production" / "master"
TEXT = MASTER / "character" / "character_text.orderedmap"
STATUS = MASTER / "character" / "character_status.orderedmap"

# CharacterTextValues column order, from reverse/master_schema.json.
TEXT_FIELDS = [
    "name", "description", "nickname",
    "skill_name_1", "skill_description_1",
    "skill_name_2", "skill_description_2",
    "leader_ability_name", "voice_actor",
]


def load(path):
    return orderedmap.decode(path.read_bytes())


def save(path, entries):
    path.write_bytes(orderedmap.encode(entries))


def find(entries, key):
    for entry in entries:
        if entry["key"] == key:
            return entry
    return None


def row_columns(entry):
    lines = entry["value"].split("\n")
    return lines, lines[0].split(",")


def write_columns(entry, lines, columns):
    lines[0] = ",".join(columns)
    entry["value"] = "\n".join(lines)


def show(character):
    entry = find(load(TEXT), character)
    if entry:
        _, columns = row_columns(entry)
        print(f"character_text  {character}")
        for i, field in enumerate(TEXT_FIELDS):
            print(f"  {field:<22} {columns[i] if i < len(columns) else ''}")
    status = find(load(STATUS), character)
    if status and status["kind"] == "map":
        print(f"\ncharacter_status  {character}")
        for level in status["entries"]:
            _, columns = row_columns(level)
            print(f"  level {level['key']:<6} hp={columns[0]:<8} atk={columns[1]}")


def set_text(character, values):
    entries = load(TEXT)
    entry = find(entries, character)
    if entry is None:
        sys.exit(f"{character} not found in character_text")
    lines, columns = row_columns(entry)
    for field, value in values.items():
        index = TEXT_FIELDS.index(field)
        while len(columns) <= index:
            columns.append("")
        if "," in value or '"' in value:
            sys.exit(f"{field}: commas and quotes would break the CSV row")
        columns[index] = value
        print(f"  {field} = {value}")
    write_columns(entry, lines, columns)
    save(TEXT, entries)


def set_stats(character, stats):
    entries = load(STATUS)
    entry = find(entries, character)
    if entry is None or entry["kind"] != "map":
        sys.exit(f"{character} not found in character_status")
    for level, (hp, atk) in stats.items():
        row = find(entry["entries"], level)
        if row is None:
            sys.exit(f"level {level} is not an anchor for {character}; "
                     f"have {[e['key'] for e in entry['entries']]}")
        lines, columns = row_columns(row)
        columns[0], columns[1] = hp, atk
        write_columns(row, lines, columns)
        print(f"  level {level}: hp={hp} atk={atk}")
    save(STATUS, entries)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", required=True)
    ap.add_argument("--show", action="store_true")
    for field in TEXT_FIELDS:
        ap.add_argument("--" + field.replace("_", "-"))
    ap.add_argument("--stat", action="append", default=[], metavar="LEVEL=HP/ATK")
    args = ap.parse_args()

    if args.show:
        show(args.character)
        return 0

    values = {}
    for field in TEXT_FIELDS:
        value = getattr(args, field)
        if value is not None:
            values[field] = value
    stats = {}
    for item in args.stat:
        level, _, pair = item.partition("=")
        hp, _, atk = pair.partition("/")
        if not (level and hp and atk):
            sys.exit(f"--stat wants LEVEL=HP/ATK, got {item!r}")
        stats[level] = (hp, atk)

    if not values and not stats:
        sys.exit("nothing to do; pass --show, a text field, or --stat")
    if values:
        set_text(args.character, values)
    if stats:
        set_stats(args.character, stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
