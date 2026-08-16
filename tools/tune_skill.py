#!/usr/bin/env python3
"""Edit command parameters inside a forked .action.dsl.json, by name.

A skill's behaviour lives entirely in its DSL file (see reverse/character-skill-chain.md).
The file is a nested array where every command is positional:

    ["Command", ["CreateNormalAttack", 2, 255, [], [], 4, {"min":0.4,"max":0.4}, ...]]

The names of those positions come from the Haxe enum constructor's __params__,
extracted into reverse/enum_params.json, so edits can be written as
`damage=999999` instead of "the sixth element".

    python3 tools/tune_skill.py --dsl <path> --show
    python3 tools/tune_skill.py --dsl <path> --command CreateNormalAttack --set damage=999999
    python3 tools/tune_skill.py --dsl <path> --restore --from <shipped path>

Only files under battle/action/skill/action/wfmod/ may be written: the shipped
DSL files are part of the pristine tree and must stay byte-identical.

Formatting is reproduced exactly - arrays use ", " between elements, objects are
compact - so a one-parameter change produces a one-parameter diff. All 63 shipped
DSL files re-encode byte-identically under this encoder, which is what makes that
claim checkable rather than hopeful.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "WFTest" / "assets" / "production"
PARAMS = ROOT / "reverse" / "enum_params.json"
COMMAND_ENUM = "pinball.battle.action.dsl.ActionDslCommand"
WRITABLE = "battle/action/skill/action/wfmod/"


def encode(value):
    """Re-emit JSON the way the shipped DSL files are written."""
    if isinstance(value, list):
        return "[" + ", ".join(encode(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{" + ",".join(json.dumps(k, ensure_ascii=False) + ":" + encode(v)
                              for k, v in value.items()) + "}"
    return json.dumps(value, ensure_ascii=False)


def commands(node, path=()):
    """Yield (path, command list) for every ["Command", [...]] in the tree."""
    if isinstance(node, list):
        if len(node) == 2 and node[0] == "Command" and isinstance(node[1], list) and node[1]:
            yield path, node[1]
        for i, item in enumerate(node):
            yield from commands(item, path + (i,))


def parameter_names():
    names = json.loads(PARAMS.read_text(encoding="utf-8")).get(COMMAND_ENUM)
    if not names:
        sys.exit(f"{PARAMS.name} has no {COMMAND_ENUM}; run tools/dump_runtime_enums.mjs")
    return names


def literal(text):
    """`999999`, `0.4`, `true`, `{"min":9,"max":9}`, or a bare string."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsl", required=True, help="path under WFTest/assets/production")
    ap.add_argument("--command", help="command name, e.g. CreateNormalAttack")
    ap.add_argument("--set", dest="assignments", action="append", default=[],
                    metavar="NAME=VALUE")
    ap.add_argument("--index", type=int, help="edit only the Nth matching command (0-based)")
    ap.add_argument("--show", action="store_true", help="print every command with parameter names")
    ap.add_argument("--restore", metavar="SOURCE",
                    help="copy a shipped DSL back over the fork, undoing every edit")
    args = ap.parse_args()

    target = ASSETS / args.dsl
    if not target.exists():
        sys.exit(f"{target} does not exist")

    if args.restore:
        source = ASSETS / args.restore
        if not source.exists():
            sys.exit(f"{source} does not exist")
        if WRITABLE not in str(target):
            sys.exit(f"refusing to write outside {WRITABLE}: {args.dsl}")
        shutil.copyfile(source, target)
        print(f"restored {args.dsl}\n     from {args.restore}")
        return 0

    raw = target.read_text(encoding="utf-8")
    tree = json.loads(raw)
    if encode(tree) != raw:
        sys.exit("this file does not re-encode byte-identically; refusing to rewrite it")
    names = parameter_names()

    if args.show:
        for _, command in commands(tree):
            fields = names.get(command[0])
            print(f"\n{command[0]}")
            for i, value in enumerate(command[1:]):
                label = fields[i] if fields and i < len(fields) else f"[{i}]"
                print(f"  {label:<32} {encode(value)}")
        return 0

    if not args.command or not args.assignments:
        sys.exit("nothing to do: pass --show, or --command with at least one --set")

    fields = names.get(args.command)
    if not fields:
        sys.exit(f"{args.command} is not a known command in {COMMAND_ENUM}")

    edits = []
    for assignment in args.assignments:
        if "=" not in assignment:
            sys.exit(f"--set expects NAME=VALUE, got {assignment!r}")
        name, _, text = assignment.partition("=")
        name = name.strip()
        if name not in fields:
            sys.exit(f"{args.command} has no parameter {name!r}; it has: {', '.join(fields)}")
        edits.append((fields.index(name) + 1, name, literal(text)))

    matches = [c for _, c in commands(tree) if c[0] == args.command]
    if not matches:
        sys.exit(f"no {args.command} in {args.dsl}")
    if args.index is not None:
        if args.index >= len(matches):
            sys.exit(f"--index {args.index} but only {len(matches)} {args.command} present")
        matches = [matches[args.index]]

    for n, command in enumerate(matches):
        for position, name, value in edits:
            if position >= len(command):
                sys.exit(f"{args.command} in this file has only {len(command) - 1} parameters")
            print(f"  {args.command}[{n}].{name}: {encode(command[position])} -> {encode(value)}")
            command[position] = value

    if WRITABLE not in str(target):
        sys.exit(f"refusing to write outside {WRITABLE}: {args.dsl}")
    out = encode(tree)
    if json.loads(out) != tree:
        sys.exit("internal error: re-encoded file does not parse back to the same tree")
    target.write_text(out, encoding="utf-8")
    print(f"\nwrote {args.dsl}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
