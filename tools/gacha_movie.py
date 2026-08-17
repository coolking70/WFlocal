#!/usr/bin/env python3
"""Read and tune the gacha ball-movie config, including its fixed seed.

The whole drop animation is data. `assets/production/gacha/tutorial_light.gacha.json`
holds the field, the ball's ejection, the pin and amulet grids, the camera, and
the rarity thresholds - and a `seed`.

The seed is what makes every play identical, and it is optional rather than
hardcoded. FallingField's constructor:

    if (Object.prototype.hasOwnProperty.call(config, 'seed')) seed = config.seed;
    else                                                     seed = Date.getTime();

So removing the key is the whole change: no patch, no hook.

    python3 tools/gacha_movie.py --show
    python3 tools/gacha_movie.py --seed random      # drop the key -> time-seeded
    python3 tools/gacha_movie.py --seed 12345       # pin it again, for repeatable runs
    python3 tools/gacha_movie.py --set pin.lineCount=16
    python3 tools/gacha_movie.py --revert           # back to the shipped file

A repeatable seed is worth keeping available: when a change to the physics needs
judging, two runs with the same seed differ only by the change.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "WFTest" / "assets" / "production" / "gacha" / "tutorial_light.gacha.json"
BACKUP = ROOT / "tools" / "baseline" / "tutorial_light.gacha.json.original"


def load():
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def save(config):
    if not BACKUP.exists():
        shutil.copyfile(CONFIG, BACKUP)
        print(f"  saved {BACKUP.name}")
    # The shipped file is one line; keep it that way so a diff stays readable.
    CONFIG.write_text(json.dumps(config, ensure_ascii=False, separators=(", ", ": ")) + "\n",
                      encoding="utf-8")


def show(config):
    print(f"{CONFIG.relative_to(ROOT)}\n")
    seed = config.get("seed")
    print(f"  seed        {seed if seed is not None else 'absent -> seeded from the clock'}")
    for group in ("field", "ball", "pin", "amulet", "barAmulet", "camera", "threshold"):
        if group not in config:
            continue
        print(f"  {group}")
        for key, value in config[group].items():
            print(f"    {key:<24} {json.dumps(value, ensure_ascii=False)}")


def set_path(config, assignment):
    if "=" not in assignment:
        sys.exit(f"--set expects group.key=VALUE, got {assignment!r}")
    path, _, raw = assignment.partition("=")
    parts = path.strip().split(".")
    node = config
    for part in parts[:-1]:
        if part not in node or not isinstance(node[part], dict):
            sys.exit(f"{path}: {part!r} is not a group in this config")
        node = node[part]
    leaf = parts[-1]
    if leaf not in node:
        sys.exit(f"{path}: no such key (this refuses to invent keys the game will ignore)")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        sys.exit(f"{raw!r} is not a JSON value")
    print(f"  {path}: {json.dumps(node[leaf], ensure_ascii=False)} -> "
          f"{json.dumps(value, ensure_ascii=False)}")
    node[leaf] = value


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--seed", help="'random' to remove the key, or an integer to pin it")
    ap.add_argument("--set", dest="assignments", action="append", default=[],
                    metavar="GROUP.KEY=VALUE")
    ap.add_argument("--revert", action="store_true")
    args = ap.parse_args()

    if args.revert:
        if not BACKUP.exists():
            sys.exit("no backup to restore; this config was never changed by this tool")
        shutil.copyfile(BACKUP, CONFIG)
        BACKUP.unlink()
        print(f"restored {CONFIG.relative_to(ROOT)}")
        return 0

    config = load()

    if args.show or (not args.seed and not args.assignments):
        show(config)
        return 0

    if args.seed is not None:
        if args.seed == "random":
            if "seed" in config:
                del config["seed"]
                print("  seed removed - FallingField will seed from Date.getTime()")
            else:
                print("  seed was already absent")
        else:
            try:
                config["seed"] = int(args.seed)
            except ValueError:
                sys.exit(f"--seed takes 'random' or an integer, got {args.seed!r}")
            print(f"  seed = {config['seed']}")

    for assignment in args.assignments:
        set_path(config, assignment)

    save(config)
    print(f"\nwrote {CONFIG.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
