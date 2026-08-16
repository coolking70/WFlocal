#!/usr/bin/env python3
"""Give a character its own action skill entry and its own DSL files.

Until this runs, a cloned character shares its source's skill: character.action_skill
points at the source's key in master action_skill, whose program_path points at a
shipped .action.dsl.json. Editing that file would change the original character too.

This forks the whole chain:

    character[<id>].action_skill  ->  <new key>
    action_skill[<new key>]/<lv>  ->  program_path = <new dsl path>
    <new dsl path>.action.dsl.json    a byte-identical copy to start from

New asset paths are unknown to the manifest baked into the bundle, so the copies
are also registered with wfmod/runtime.js, which adds them to the live lime
AssetLibrary at startup.

    python3 tools/fork_skill.py --character 129001 --from brown_fighter --key wfmod_001

Re-running replaces the fork. `--revert` puts the character back on its source.
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import orderedmap  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MASTER = ROOT / "WFTest" / "assets" / "trial" / "production" / "master"
ASSETS = ROOT / "WFTest" / "assets" / "production"
RUNTIME = ROOT / "WFTest" / "wfmod" / "runtime.js"

CHARACTER = MASTER / "character" / "character.orderedmap"
ACTION_SKILL = MASTER / "skill" / "action_skill.orderedmap"

COL_ACTION_SKILL = 8      # CharacterValues.action_skill
COL_PROGRAM_PATH = 7      # ActionSkillValues.program_path
DSL_SUFFIX = ".action.dsl.json"
FORK_DIR = "battle/action/skill/action/wfmod"


def load(path):
    return orderedmap.decode(path.read_bytes())


def save(path, entries):
    path.write_bytes(orderedmap.encode(entries))


def find(entries, key):
    for entry in entries:
        if entry["key"] == key:
            return entry
    return None


def columns_of(entry):
    lines = entry["value"].split("\n")
    return lines, lines[0].split(",")


def set_column(entry, index, value):
    lines, columns = columns_of(entry)
    while len(columns) <= index:
        columns.append("")
    columns[index] = value
    lines[0] = ",".join(columns)
    entry["value"] = "\n".join(lines)


def register_assets(paths):
    """Add the forked DSL files to runtime.js's ADDED_ASSETS list."""
    text = RUNTIME.read_text(encoding="utf-8")
    marker = "\tvar ADDED_ASSETS = ["
    start = text.index(marker)
    end = text.index("\t];", start)
    body = text[start + len(marker): end]
    lines = []
    for new_path, model in paths:
        entry = f'\n\t\t["{new_path}",\n\t\t\t"{model}"],'
        if new_path not in body:
            lines.append(entry)
    if not lines:
        print("  runtime.js already registers these assets")
        return
    RUNTIME.write_text(text[:start + len(marker)] + "".join(lines) + body + text[end:], encoding="utf-8")
    print(f"  registered {len(lines)} asset(s) in wfmod/runtime.js")
    # Editing runtime.js without re-stamping the launcher's cache-buster ships a
    # stale file to the browser, which looks exactly like a broken feature.
    subprocess.run([sys.executable, str(ROOT / "tools" / "stamp_assets.py")], check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", required=True)
    ap.add_argument("--from", dest="source", required=True, help="source action_skill key")
    ap.add_argument("--key", help="new action_skill key (default wfmod_<character>)")
    ap.add_argument("--revert", action="store_true")
    args = ap.parse_args()
    new_key = args.key or f"wfmod_{args.character}"

    characters = load(CHARACTER)
    character = find(characters, args.character)
    if character is None:
        sys.exit(f"character {args.character} not found")

    if args.revert:
        set_column(character, COL_ACTION_SKILL, args.source)
        save(CHARACTER, characters)
        skills = load(ACTION_SKILL)
        skills = [e for e in skills if e["key"] != new_key]
        save(ACTION_SKILL, skills)
        print(f"  character {args.character}.action_skill = {args.source}")
        print(f"  removed action_skill[{new_key}]")
        print("\nThe forked .action.dsl.json files and their runtime.js entries are left in "
              "place; delete them by hand if you want them gone.")
        return 0

    skills = load(ACTION_SKILL)
    source = find(skills, args.source)
    if source is None or source["kind"] != "map":
        sys.exit(f"action_skill[{args.source}] not found (or not a nested table)")

    import copy
    fork = copy.deepcopy(source)
    fork["key"] = new_key

    registrations = []
    for level in fork["entries"]:
        _, columns = columns_of(level)
        original = columns[COL_PROGRAM_PATH]
        source_file = ASSETS / (original + DSL_SUFFIX)
        if not source_file.exists():
            # The shipped data has dangling references - brown_fighter level 2
            # names a file the demo does not include. Leave such levels pointing
            # where they already point rather than inventing a file.
            print(f"  level {level['key']}: source DSL missing, left as {original}")
            continue
        new_relative = f"{FORK_DIR}/{new_key}${new_key}_{level['key']}"
        target = ASSETS / (new_relative + DSL_SUFFIX)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_file, target)
        set_column(level, COL_PROGRAM_PATH, new_relative)
        print(f"  level {level['key']}: {original}")
        print(f"        -> {new_relative}")
        # ADDED_ASSETS holds root-relative paths; runtime.js prepends each asset
        # root itself. Writing fully-qualified paths here made it prepend twice,
        # so the model was never found and registration silently did nothing.
        registrations.append((new_relative + DSL_SUFFIX, original + DSL_SUFFIX))

    skills = [e for e in skills if e["key"] != new_key] + [fork]
    save(ACTION_SKILL, skills)
    set_column(character, COL_ACTION_SKILL, new_key)
    save(CHARACTER, characters)
    print(f"  character {args.character}.action_skill = {new_key}")
    register_assets(registrations)
    print("\nThe copies start byte-identical, so behaviour should not change. "
          "Edit them to change the skill.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
