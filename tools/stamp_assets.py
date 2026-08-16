#!/usr/bin/env python3
"""Stamp the launcher's cache-buster from wfmod/runtime.js's modification time.

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
RUNTIME = ROOT / "WFTest" / "wfmod" / "runtime.js"


def main():
    stamp = int(RUNTIME.stat().st_mtime)
    text = LAUNCHER.read_text(encoding="utf-8")
    new, count = re.subn(r'(runtime\.js\?wfbuild=[0-9.]+&amp;r=)\d+', rf'\g<1>{stamp}', text)
    if count != 1:
        sys.exit(f"expected exactly one runtime.js cache-buster, found {count}")
    if new != text:
        LAUNCHER.write_text(new, encoding="utf-8")
        print(f"stamped runtime.js cache-buster: r={stamp}")
    else:
        print(f"cache-buster already current: r={stamp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
