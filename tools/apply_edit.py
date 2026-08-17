#!/usr/bin/env python3
"""Apply one Hub edit. The dev server calls this; nothing else may write.

The browser cannot write files, and it should not learn how: the .orderedmap
round-trip test and the DSL re-encoder both live on the Python side, and one
writer is what keeps them meaningful. So the Hub sends an edit here and this
shells out to tools/tune_skill.py, which is the same path a person editing by
hand takes.

    python3 tools/apply_edit.py --program battle/action/skill/action/wfmod/x \\
        --command CreateNormalAttack --param damage --value 4

Validation is deliberately narrow. An edit may only touch a forked DSL under
battle/action/skill/action/wfmod/ - tune_skill.py refuses anything else too, but
a request that never reaches it is easier to explain than one that fails inside.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FORK_PREFIX = "battle/action/skill/action/wfmod/"
DSL_SUFFIX = ".action.dsl.json"
NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class EditError(Exception):
    pass


def apply(program, command, param, value, index=None):
    """Run one edit and return tune_skill.py's output. Raises EditError."""
    if not isinstance(program, str) or not program.startswith(FORK_PREFIX):
        raise EditError(f"only forked skills may be edited, under {FORK_PREFIX}")
    if ".." in program or program.startswith("/"):
        raise EditError("program path may not escape the fork directory")
    if not (isinstance(command, str) and NAME.match(command)):
        raise EditError(f"{command!r} is not a command name")
    if not (isinstance(param, str) and NAME.match(param)):
        raise EditError(f"{param!r} is not a parameter name")
    if not isinstance(value, str) or not value.strip():
        raise EditError("value must be a non-empty string holding a JSON literal")
    try:
        json.loads(value)
    except json.JSONDecodeError as error:
        raise EditError(f"value is not valid JSON: {error}") from error

    target = ROOT / "WFTest" / "assets" / "production" / (program + DSL_SUFFIX)
    if not target.exists():
        raise EditError(f"{program + DSL_SUFFIX} does not exist")

    args = [sys.executable, str(ROOT / "tools" / "tune_skill.py"),
            "--dsl", program + DSL_SUFFIX, "--command", command,
            "--set", f"{param}={value}"]
    if index is not None:
        args += ["--index", str(int(index))]

    done = subprocess.run(args, cwd=str(ROOT), capture_output=True, text=True)
    if done.returncode != 0:
        raise EditError((done.stderr or done.stdout).strip() or "tune_skill.py failed")
    return done.stdout.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--program", required=True)
    ap.add_argument("--command", required=True)
    ap.add_argument("--param", required=True)
    ap.add_argument("--value", required=True)
    ap.add_argument("--index", type=int)
    args = ap.parse_args()
    try:
        print(apply(args.program, args.command, args.param, args.value, args.index))
    except EditError as error:
        sys.exit(str(error))
    return 0


if __name__ == "__main__":
    sys.exit(main())
