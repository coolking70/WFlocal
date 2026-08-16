#!/usr/bin/env python3
"""Compare WFTest/ against the pristine official archive.

Answers one question: what does this tree change relative to the game as
shipped? Everything listed as MODIFIED or ADDED is a deliberate mod, and should
be explainable. Anything unexpected there is a bug or an accident.

    python3 tools/verify_tree.py            # summary
    python3 tools/verify_tree.py --list     # plus every differing path

The baseline is tools/baseline/MANIFEST.sha256, generated from WFDemo.zip
(see the header of that file for archive provenance).
"""

import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "tools" / "baseline" / "MANIFEST.sha256"
TREE = ROOT / "WFTest"
IGNORED = {".DS_Store"}

# Files this project intentionally changes or adds, with the reason. Deviations
# outside this set are reported as UNEXPECTED.
EXPECTED = {
    "world-flipper.js": "must stay pristine; all edits are runtime patches in game-index.html",
    "game-index.html": "mod bootstrap: declarative patch table",
    "index.html": "added: boot mode launcher",
    "assets/trial/production/master/quest/main_quest.orderedmap": "added quest 111001004 (custom stage slot)",
}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_manifest():
    if not MANIFEST.exists():
        sys.exit(f"missing baseline manifest: {MANIFEST}")
    entries = {}
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        digest, name = line.split("  ", 1)
        entries[name] = digest
    return entries


def describe(path):
    return EXPECTED.get(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="list every differing path")
    args = ap.parse_args()

    baseline = load_manifest()
    current = {}
    for path in TREE.rglob("*"):
        if path.is_dir() or path.name in IGNORED:
            continue
        current[str(path.relative_to(TREE))] = sha256(path)

    unchanged = sorted(p for p, d in current.items() if baseline.get(p) == d)
    modified = sorted(p for p, d in current.items() if p in baseline and baseline[p] != d)
    added = sorted(p for p in current if p not in baseline)
    missing = sorted(p for p in baseline if p not in current)

    print(f"baseline  {MANIFEST.relative_to(ROOT)} ({len(baseline)} entries)")
    print(f"tree      {TREE.relative_to(ROOT)} ({len(current)} files)\n")
    print(f"  unchanged {len(unchanged)}")
    print(f"  modified  {len(modified)}")
    print(f"  added     {len(added)}")
    print(f"  missing   {len(missing)}")

    unexpected = [p for p in modified + added if describe(p) is None]

    bundle = "world-flipper.js"
    if bundle in current:
        pristine = current[bundle] == baseline.get(bundle)
        print(f"\n  world-flipper.js pristine: {'yes' if pristine else 'NO'}")
        if not pristine:
            print("    the bundle must stay untouched; edits belong in the patch table")

    if args.list:
        for label, paths in (("modified", modified), ("added", added), ("missing", missing)):
            if not paths:
                continue
            print(f"\n--- {label} ---")
            for p in paths:
                note = describe(p) or "UNEXPECTED"
                print(f"  {p}\n      {note}")

    if missing:
        print(f"\n{len(missing)} file(s) missing from the tree; run with --list")
    if unexpected:
        print(f"\n{len(unexpected)} unexpected deviation(s); run with --list")

    bundle_dirty = bundle in current and current[bundle] != baseline.get(bundle)
    return 1 if (missing or unexpected or bundle_dirty) else 0


if __name__ == "__main__":
    sys.exit(main())
