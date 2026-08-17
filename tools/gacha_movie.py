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
PROD = ROOT / "WFTest" / "assets" / "production"
CONFIG = PROD / "gacha" / "tutorial_light.gacha.json"
MOVIE_DIR = PROD / "scene" / "gacha_movie"
BASELINE = ROOT / "tools" / "baseline"

# The shipped movie is a tutorial prop: one rarity, so several timelines carry only
# a `rarity3` sequence. Raising the rarity threshold makes the game ask for
# `rarity4`, and a missing sequence name is a hard crash, not a fallback.
RARITIES = ("rarity3", "rarity4", "rarity5")


def backup_of(path):
    return BASELINE / (path.name + ".original")


def keep(path):
    target = backup_of(path)
    if not target.exists():
        shutil.copyfile(path, target)
        print(f"  saved {target.name}")


def load():
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def save(config):
    keep(CONFIG)
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


def placeholder_rarities():
    """Alias the missing rarity sequences onto the one the file does have.

    A sequence is a named frame range, so an alias needs no new frames: every
    rarity plays the same animation. That is a placeholder and looks like one -
    the point is that the higher rarities stop crashing, not that they look right.
    """
    touched = 0
    for path in sorted(MOVIE_DIR.glob("*.timeline.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        sequences = data.get("sequences")
        if not isinstance(sequences, list):
            continue
        have = {s.get("name"): s for s in sequences if isinstance(s, dict)}
        if "rarity3" not in have:
            continue                       # not driven by rarity; leave it alone
        missing = [r for r in RARITIES if r not in have]
        if not missing:
            continue
        keep(path)
        for name in missing:
            clone = dict(have["rarity3"])
            clone["name"] = name
            sequences.append(clone)
        path.write_text(json.dumps(data, ensure_ascii=False, separators=(", ", ": ")) + "\n",
                        encoding="utf-8")
        print(f"  {path.name}: added {', '.join(missing)} "
              f"(same frames as rarity3: {have['rarity3']['begin']}..{have['rarity3']['end']})")
        touched += 1
    if not touched:
        print("  every rarity-driven timeline already has all three sequences")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--seed", help="'random' to remove the key, or an integer to pin it")
    ap.add_argument("--set", dest="assignments", action="append", default=[],
                    metavar="GROUP.KEY=VALUE")
    ap.add_argument("--placeholder-rarities", action="store_true",
                    help="alias missing rarity4/rarity5 sequences onto rarity3")
    ap.add_argument("--revert", action="store_true")
    args = ap.parse_args()

    if args.revert:
        restored = 0
        for original in sorted(BASELINE.glob("*.original")):
            name = original.name[: -len(".original")]
            for candidate in (CONFIG, *sorted(MOVIE_DIR.glob("*.timeline.json"))):
                if candidate.name == name:
                    shutil.copyfile(original, candidate)
                    original.unlink()
                    print(f"  restored {candidate.relative_to(ROOT)}")
                    restored += 1
                    break
        if not restored:
            sys.exit("no backup to restore; nothing here was changed by this tool")
        return 0

    if args.placeholder_rarities:
        return placeholder_rarities()

    config = load()

    if args.show or (not args.seed and not args.assignments and not args.placeholder_rarities):
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
