#!/usr/bin/env python3
"""Stamp the launcher's cache-busters from each wfmod script's modification time.

The launcher loads runtime.js with a ?r= parameter so a changed file is fetched
rather than served from cache. Bumping that by hand does not survive contact
with reality: tools that edit runtime.js (fork_skill.py) forgot to, the URL
stayed the same, and the browser ran a stale copy whose registered assets did
not match the master data - which looked exactly like a broken feature.

Deriving the stamp from mtime makes staleness impossible. verify_patches.mjs
checks it, so a forgotten stamp fails the checks instead of shipping.

    python3 tools/stamp_assets.py
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LAUNCHER = ROOT / "WFTest" / "game-index.html"
WFMOD = ROOT / "WFTest" / "wfmod"

# Every script the launcher loads from wfmod/ gets its own stamp. One shared
# stamp would mean editing any of them re-fetches all of them, and worse, that a
# tool editing one file could leave another's stamp looking fresh.
SCRIPTS = ("runtime.js", "orderedmap.js", "hub.js")


def main():
    text = LAUNCHER.read_text(encoding="utf-8")
    changed = []
    for name in SCRIPTS:
        path = WFMOD / name
        if not path.exists():
            sys.exit(f"{path.relative_to(ROOT)} does not exist")
        stamp = int(path.stat().st_mtime)
        pattern = re.escape(name) + r'(\?wfbuild=[0-9.]+&amp;r=)\d+'
        text, count = re.subn(pattern, rf'{name}\g<1>{stamp}', text)
        if count != 1:
            sys.exit(f"expected exactly one {name} cache-buster in the launcher, found {count}")
        changed.append(f"{name}={stamp}")
    if text != LAUNCHER.read_text(encoding="utf-8"):
        LAUNCHER.write_text(text, encoding="utf-8")
        print("stamped cache-busters: " + ", ".join(changed))
    else:
        print("cache-busters already current: " + ", ".join(changed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
