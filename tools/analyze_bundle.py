#!/usr/bin/env python3
"""Build a searchable index of the official world-flipper.js bundle.

The bundle is one 29MB obfuscated IIFE: locals are `_0xXXXXXX` and every
property name is written as \\xNN escapes. But Haxe leaves two registries
behind - $hxClasses and $hxEnums - keyed by real class names, and every class
records __name__ / __super__. That is enough to recover a class and method map
without decompiling anything.

Everything here works on a *decoded view* of the bundle: the \\xNN escapes are
expanded in memory, so offsets in the generated index refer to that view, not
to the file on disk. Use `show` to read source around an offset. Patch anchors
still have to be built with esc() as game-index.html does.

    python3 tools/analyze_bundle.py index          # regenerate reverse/*.json
    python3 tools/analyze_bundle.py find <query>   # search classes and methods
    python3 tools/analyze_bundle.py show <offset>  # print decoded source there

The bundle is never modified.
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUNDLE = ROOT / "WFTest" / "world-flipper.js"
OUT = ROOT / "reverse"

# Property names are \xNN, Japanese text is \uNNNN. Expanding both makes the
# whole bundle searchable by real names and real messages.
ESCAPES = re.compile(r"(?:\\x[0-9a-fA-F]{2}|\\u[0-9a-fA-F]{4})+")


def decode(src):
    """Expand \\xNN / \\uNNNN escape runs. Read-only view; the bundle is never rewritten."""
    def expand(match):
        run = match.group(0)
        out = []
        i = 0
        while i < len(run):
            width = 4 if run[i + 1] == "x" else 6
            out.append(chr(int(run[i + 2: i + width], 16)))
            i += width
        return "".join(out)
    return ESCAPES.sub(expand, src)


def object_span(text, open_index):
    """Return the index just past the object literal starting at `open_index`.

    Skips over string literals so braces inside them do not unbalance the scan.
    """
    depth = 0
    i = open_index
    quote = None
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return -1


MEMBER = re.compile(r"'([A-Za-z_$][A-Za-z0-9_$]*)':\s*(function|null|\[|\{|_0x)")


def members_of(text, start):
    """Names declared in the object literal beginning at `start`."""
    end = object_span(text, start)
    if end < 0:
        return [], start
    body = text[start:end]
    names, seen = [], set()
    for match in MEMBER.finditer(body):
        name = match.group(1)
        if name not in seen:
            seen.add(name)
            names.append(name)
    return names, end


CLASS_WRITE = re.compile(r"_0x2cc772\['([A-Za-z0-9_.$]+)'\]\s*=\s*(_0x[0-9a-f]+)\s*;")
ENUM_WRITE = re.compile(r"(_0x[0-9a-f]+)\s*=\s*_0x7f6db2\['([A-Za-z0-9_.$]+)'\]\s*=\s*\{")
CONSTRUCTS = re.compile(r"'__constructs__':\s*\[([^\]]*)\]")


def collect_classes(text):
    classes = {}
    for match in CLASS_WRITE.finditer(text):
        name, var = match.group(1), match.group(2)
        entry = classes.setdefault(name, {
            "name": name,
            "var": var,
            "offset": match.start(),
            "methods": [],
            "statics": [],
            "super": None,
        })
        entry["var"] = var
        entry["offset"] = match.start()

        # Look ahead a bounded window for this class's prototype and statics.
        window = text[match.end(): match.end() + 200_000]
        sup = re.search(re.escape(var) + r"\['__super__'\]\s*=\s*(_0x[0-9a-f]+)", window)
        if sup:
            entry["super_var"] = sup.group(1)
        proto = re.search(re.escape(var) + r"\['prototype'\]\s*=\s*(?:_0x[0-9a-f]+\([^,]+,\s*)?\{", window)
        if proto:
            names, _ = members_of(window, window.index("{", proto.start()))
            entry["methods"] = names
        entry["statics"] = sorted(set(
            re.findall(re.escape(var) + r"\['([A-Za-z_$][A-Za-z0-9_$]*)'\]\s*=\s*function", window)
        ))

    # Resolve __super__ variables to class names now that every var is known.
    by_var = {c["var"]: c["name"] for c in classes.values()}
    for entry in classes.values():
        entry["super"] = by_var.get(entry.pop("super_var", None))
    return classes


def collect_enums(text):
    enums = {}
    for match in ENUM_WRITE.finditer(text):
        name = match.group(2)
        body_end = object_span(text, text.index("{", match.end() - 1))
        body = text[match.start(): body_end if body_end > 0 else match.end() + 4000]
        constructs = CONSTRUCTS.search(body)
        values = []
        if constructs:
            values = [v.strip().strip("'\"") for v in constructs.group(1).split(",") if v.strip()]
        enums[name] = {"name": name, "offset": match.start(), "constructs": values}
    return enums


def call_span(text, open_index):
    """Index just past the call argument list opening at `open_index`."""
    depth = 0
    i = open_index
    quote = None
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def collect_errors(text, classes):
    """Every `new ClientError(code, message)` site, by numeric code.

    Plenty of messages are built at runtime (8601 appends the key and the master
    path, for instance), so the message argument is captured as an expression
    rather than assumed to be a string literal.
    """
    entry = classes.get("pinball.error.ClientError")
    if not entry:
        return {}
    pattern = re.compile(r"new " + re.escape(entry["var"]) + r"\((0x[0-9a-f]+),")
    found = {}
    for match in pattern.finditer(text):
        code = int(match.group(1), 16)
        end = call_span(text, match.end() - 1 - len(match.group(1)) - 1)
        message = text[match.end(): end] if end > 0 else ""
        literal = re.fullmatch(r"'((?:[^'\\]|\\.)*)'", message.strip())
        record = found.setdefault(str(code), {"code": code, "message": None, "sites": []})
        if literal:
            # decode() already expanded \xNN / \uNNNN, so only source-level
            # backslash escapes are left. Decoding again would mangle the text.
            record["message"] = literal.group(1).replace("\\'", "'").replace("\\\\", "\\")
        elif record["message"] is None:
            # Keep the expression so the code is still searchable and its shape visible.
            record["message"] = re.sub(r"\s+", " ", message.strip())[:300]
        record["sites"].append(match.start())
    return found


ASSET = re.compile(r"'((?:assets/|production/|trial/|scene/|battle/|character/|master/)[A-Za-z0-9_./-]{4,})'")


def collect_assets(text):
    return sorted({m.group(1) for m in ASSET.finditer(text)})


def cmd_index(args):
    src = BUNDLE.read_text(encoding="utf-8", errors="replace")
    text = decode(src)
    print(f"bundle {BUNDLE} ({len(src)} chars, {len(text)} decoded)")

    classes = collect_classes(text)
    enums = collect_enums(text)
    errors = collect_errors(text, classes)
    assets = collect_assets(text)

    def subset(prefix_test):
        return sorted(name for name in classes if prefix_test(name))

    scenes = subset(lambda n: ".scene." in n)
    masters = subset(lambda n: ".master." in n)
    remotes = subset(lambda n: "remote" in n.lower())

    OUT.mkdir(exist_ok=True)
    written = {
        "classes.json": {"count": len(classes), "classes": [classes[k] for k in sorted(classes)]},
        "enums.json": {"count": len(enums), "enums": [enums[k] for k in sorted(enums)]},
        "errors.json": {"count": len(errors), "errors": [errors[k] for k in sorted(errors, key=int)]},
        "assets.json": {"count": len(assets), "assets": assets},
        "scenes.json": {"count": len(scenes), "scenes": scenes},
        "masters.json": {"count": len(masters), "masters": masters},
        "remotes.json": {"count": len(remotes), "remotes": remotes},
    }
    for filename, payload in written.items():
        (OUT / filename).write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    method_total = sum(len(c["methods"]) for c in classes.values())
    print(f"\n  classes  {len(classes)}  ({method_total} prototype methods)")
    print(f"  enums    {len(enums)}")
    print(f"  errors   {len(errors)} distinct ClientError codes")
    print(f"  scenes   {len(scenes)}")
    print(f"  masters  {len(masters)}")
    print(f"  remotes  {len(remotes)}")
    print(f"  assets   {len(assets)}")
    print(f"\nwrote {len(written)} files to {OUT.relative_to(ROOT)}/")
    return 0


def cmd_find(args):
    path = OUT / "classes.json"
    if not path.exists():
        sys.exit("no index yet; run: python3 tools/analyze_bundle.py index")
    classes = json.loads(path.read_text(encoding="utf-8"))["classes"]
    needle = args.query.lower()
    hits = 0
    for entry in classes:
        name_hit = needle in entry["name"].lower()
        methods = [m for m in entry["methods"] + entry["statics"] if needle in m.lower()]
        if not name_hit and not methods:
            continue
        hits += 1
        print(f"\n{entry['name']}  @{entry['offset']}")
        if entry["super"]:
            print(f"  extends {entry['super']}")
        for method in (methods if not name_hit else entry["methods"] + entry["statics"])[: args.limit]:
            print(f"    {method}")
        if hits >= args.max:
            print(f"\n... stopping at {args.max} classes")
            break
    if not hits:
        print("no match")
    return 0


def cmd_show(args):
    text = decode(BUNDLE.read_text(encoding="utf-8", errors="replace"))
    start = max(0, args.offset - args.before)
    print(text[start: args.offset + args.after])
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("index", help="regenerate reverse/*.json")
    p.set_defaults(func=cmd_index)

    p = sub.add_parser("find", help="search class and method names")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=40, help="methods printed per class")
    p.add_argument("--max", type=int, default=25, help="classes printed")
    p.set_defaults(func=cmd_find)

    p = sub.add_parser("show", help="print decoded source around an offset")
    p.add_argument("offset", type=int)
    p.add_argument("--before", type=int, default=200)
    p.add_argument("--after", type=int, default=800)
    p.set_defaults(func=cmd_show)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
