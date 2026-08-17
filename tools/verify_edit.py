#!/usr/bin/env python3
"""Check the Hub's edit path end to end, then put the file back.

    python3 tools/verify_edit.py

This is the only part of WFMod that writes data on a request from the browser,
so it gets checked the way a writer should be: apply a real edit, prove the file
changed exactly where it was meant to, apply the original value back, and prove
the file is byte-identical to how it started. If that last step ever fails,
editing is lossy and the tooling has a bug worth more than the feature.

Also checks that the requests which must be refused are refused - an edit
outside the fork directory, a bad command name, a value that is not JSON.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import apply_edit  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PROGRAM = "battle/action/skill/action/wfmod/wfmod_001$wfmod_001_1"
TARGET = ROOT / "WFTest" / "assets" / "production" / (PROGRAM + ".action.dsl.json")

failures = 0


def check(ok, what):
    global failures
    print(f"  {'ok  ' if ok else 'BAD '} {what}")
    if not ok:
        failures += 1


def value_of(command, param):
    reference = json.loads((ROOT / "WFTest" / "wfmod" / "dsl-reference.json")
                           .read_text(encoding="utf-8"))
    fields = reference["commands"][command]["params"]
    found = []

    def walk(node):
        if isinstance(node, list):
            if len(node) == 2 and node[0] == "Command" and isinstance(node[1], list) \
                    and node[1] and node[1][0] == command:
                found.append(node[1])
            for item in node:
                walk(item)

    walk(json.loads(TARGET.read_text(encoding="utf-8")))
    if not found:
        sys.exit(f"{PROGRAM} has no {command}")
    return found[0][fields.index(param) + 1]


def main():
    if not TARGET.exists():
        sys.exit(f"{TARGET.relative_to(ROOT)} does not exist; "
                 f"run tools/fork_skill.py first")

    before = TARGET.read_bytes()
    original = value_of("CreateNormalAttack", "damage")
    print(f"file    {TARGET.relative_to(ROOT)}")
    print(f"damage  {original}\n")

    apply_edit.apply(PROGRAM, "CreateNormalAttack", "damage", "1234")
    check(value_of("CreateNormalAttack", "damage") == 1234, "an edit is written")
    check(TARGET.read_bytes() != before, "the file on disk changed")

    apply_edit.apply(PROGRAM, "CreateNormalAttack", "damage", json.dumps(original))
    check(value_of("CreateNormalAttack", "damage") == original, "the original value is restored")
    check(TARGET.read_bytes() == before,
          "the file is byte-identical after the round trip")

    refusals = [
        (("battle/action/skill/action/rare5/brown_fighter$brown_fighter_1",
          "CreateNormalAttack", "damage", "1"), "a shipped skill outside the fork directory"),
        ((PROGRAM, "../../etc/passwd", "damage", "1"), "a command name that is not a name"),
        ((PROGRAM, "CreateNormalAttack", "damage", "not json"), "a value that is not JSON"),
        (("../../../etc/passwd", "CreateNormalAttack", "damage", "1"), "a path escaping the tree"),
    ]
    for args, what in refusals:
        try:
            apply_edit.apply(*args)
            check(False, f"refuses {what}")
        except apply_edit.EditError:
            check(True, f"refuses {what}")

    check(TARGET.read_bytes() == before, "no refused request touched the file")

    print("")
    if failures:
        print(f"{failures} problem(s) found")
        return 1
    print("the edit path writes, restores byte-identically, and refuses the rest")
    return 0


if __name__ == "__main__":
    sys.exit(main())
