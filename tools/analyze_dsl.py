#!/usr/bin/env python3
"""Inventory the battle action DSL.

Two sources, and the gap between them is the interesting part:

  supported   pinball.battle.action.dsl.ActionDslCommand in the bundle - what the
              engine can execute at all (read from reverse/enums.json)
  used        the *.action.dsl.json files that ship with the demo - what official
              content actually asks for

A command that is supported but unused is a capability available to original
skills for free. A behaviour that is neither is what needs a new engine
primitive, which is the question R2 exists to answer.

    python3 tools/analyze_dsl.py            # summary to stdout
    python3 tools/analyze_dsl.py --write    # also write reverse/dsl.json

Run tools/analyze_bundle.py index first; this reads its enum output.
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "WFTest" / "assets"
ENUMS = ROOT / "reverse" / "enums.json"
PARAMS = ROOT / "reverse" / "enum_params.json"
OUT = ROOT / "reverse" / "dsl.json"

COMMAND_ENUM = "pinball.battle.action.dsl.ActionDslCommand"
DSL_PREFIX = "pinball.battle.action.dsl."


def load_enums():
    if not ENUMS.exists():
        sys.exit("no enum index; run: python3 tools/analyze_bundle.py index")
    data = json.loads(ENUMS.read_text(encoding="utf-8"))["enums"]
    return {e["name"]: e["constructs"] for e in data if e["name"].startswith(DSL_PREFIX)}


def shape(node, depth=0):
    """A compact description of a value's shape, for grouping argument forms.

    Nested Blocks are elided: a command's own parameters are the useful part,
    and the commands inside its body are counted in their own right anyway.
    """
    if isinstance(node, list):
        if node and isinstance(node[0], str):
            if depth >= 2 or node[0] in ("Block", "Event"):
                return node[0] + "(...)" if len(node) > 1 else node[0]
            if len(node) > 1:
                return node[0] + "(" + ",".join(shape(a, depth + 1) for a in node[1:]) + ")"
            return node[0]
        return "[" + ",".join(shape(a, depth + 1) for a in node) + "]"
    if isinstance(node, bool):
        return "bool"
    if isinstance(node, int):
        return "int"
    if isinstance(node, float):
        return "float"
    if isinstance(node, str):
        return "str"
    if node is None:
        return "null"
    return type(node).__name__


def walk(node, path, tags, commands, source):
    """Collect every tagged node, and every Command's inner command name."""
    if isinstance(node, list):
        if node and isinstance(node[0], str):
            tag = node[0]
            tags[tag] += 1
            if tag == "Command" and len(node) > 1 and isinstance(node[1], list) and node[1]:
                inner = node[1]
                name = inner[0]
                record = commands[name]
                record["count"] += 1
                record["files"].add(source)
                record["signatures"][tuple(shape(a) for a in inner[1:])] += 1
        for child in node:
            walk(child, path, tags, commands, source)
    elif isinstance(node, dict):
        for child in node.values():
            walk(child, path, tags, commands, source)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="write reverse/dsl.json")
    args = ap.parse_args()

    enums = load_enums()
    # Haxe records each enum constructor's parameter names on the constructor
    # itself, so argument semantics come straight from the bundle rather than
    # from reading the parser. See tools/dump_runtime_enums.mjs.
    params = {}
    if PARAMS.exists():
        params = json.loads(PARAMS.read_text(encoding="utf-8")).get(COMMAND_ENUM, {})
    else:
        print("note: reverse/enum_params.json missing; run node tools/dump_runtime_enums.mjs --write")
    supported = enums.get(COMMAND_ENUM)
    if not supported:
        sys.exit(f"{COMMAND_ENUM} not found in the enum index")

    files = sorted(ASSETS.rglob("*.action.dsl.json"))
    tags = Counter()
    commands = defaultdict(lambda: {"count": 0, "files": set(), "signatures": Counter()})
    for path in files:
        walk(json.loads(path.read_text(encoding="utf-8")), path, tags, commands,
             str(path.relative_to(ASSETS)))

    used = {name for name in commands}
    unknown = sorted(used - set(supported))
    unused = sorted(set(supported) - used)

    print(f"dsl files   {len(files)}")
    print(f"commands    {len(supported)} supported by the engine, {len(used)} used by shipped content")
    if unknown:
        print(f"WARNING: used but not in {COMMAND_ENUM}: {unknown}")

    def named(name, signature):
        """Pair declared parameter names with the shapes actually observed."""
        names = params.get(name)
        if not names:
            return ", ".join(signature)
        pairs = []
        for i, param in enumerate(names):
            pairs.append(f"{param}: {signature[i]}" if i < len(signature) else f"{param}: ?")
        return ", ".join(pairs)

    print("\n--- used ---")
    for name in sorted(used, key=lambda n: -commands[n]["count"]):
        record = commands[name]
        print(f"\n  {name}  {record['count']}x in {len(record['files'])} files")
        if params.get(name) is not None:
            print(f"    declared: {name}({', '.join(params[name])})")
        for signature, count in record["signatures"].most_common(2):
            print(f"    seen x{count}: {named(name, signature)}")

    print(f"\n--- supported but unused ({len(unused)}) ---")
    print("  these are free capabilities for original skills")
    for name in unused:
        declared = params.get(name)
        print(f"  {name}({', '.join(declared)})" if declared is not None else f"  {name}")

    print(f"\n--- parameter value spaces ({len(enums) - 1} enums) ---")
    for name in sorted(enums):
        if name == COMMAND_ENUM:
            continue
        values = enums[name]
        short = name[len(DSL_PREFIX):]
        print(f"  {short:<40} {len(values):>2}  {', '.join(values[:6])}{' ...' if len(values) > 6 else ''}")

    if args.write:
        payload = {
            "commandEnum": COMMAND_ENUM,
            "supported": supported,
            "used": {
                name: {
                    "count": record["count"],
                    "files": sorted(record["files"]),
                    "params": params.get(name, []),
                    "signatures": [[list(sig), n] for sig, n in record["signatures"].most_common()],
                }
                for name, record in sorted(commands.items())
            },
            "unused": [{"name": n, "params": params.get(n, [])} for n in unused],
            "nodeTags": tags.most_common(),
            "valueSpaces": {name[len(DSL_PREFIX):]: values for name, values in sorted(enums.items())
                            if name != COMMAND_ENUM},
        }
        OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"\nwrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
