#!/usr/bin/env python3
"""Recover the column layout of every generated master table.

Master rows are CSV with no header. The generated `*Values` classes in the
bundle parse them, and their constructors index the row explicitly:

    this['action_skill'] = row[0x8];
    var a = row[0x9]; var b = row[0xa];
    this['leader_ability'] = a == '(None)' ? None : Some({id: parseInt(a), name: b});

So the authoritative schema is the constructor, not the field order. Field order
alone is wrong: leader_ability above consumes *two* columns, which is why
CharacterValues declares 19 fields for a 20 column row.

    python3 tools/master_schema.py                      # summary
    python3 tools/master_schema.py --write              # write reverse/master_schema.json
    python3 tools/master_schema.py --show CharacterValues
    python3 tools/master_schema.py --decode <file.orderedmap> --as CharacterValues

`--decode` prints real rows with their column names attached, which is the point
of the whole exercise.
"""

import argparse
import csv
import io
import json
import re
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_bundle import BUNDLE, decode  # noqa: E402
from orderedmap import parse_bytes  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "reverse" / "master_schema.json"

REGISTER = re.compile(r"_0x2cc772\['pinball\.master\.generated\.(\w+Values)'\]\s*=\s*(_0x[0-9a-f]+)\s*;")
ASSIGN = re.compile(r"this\['([A-Za-z_][A-Za-z0-9_]*)'\]\s*=")


def constructor_body(text, var, end):
    """Source of `var <var> = function(<arg>) { ... }` that precedes `end`."""
    start = text.rfind(f"var {var}=function(", 0, end)
    if start < 0:
        return None, None
    head = text.index("{", start)
    arg_match = re.match(r"var " + re.escape(var) + r"=function\((_0x[0-9a-f]+)\)", text[start:])
    if not arg_match:
        return None, None
    depth, i, quote = 0, head, None
    while i < end:
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
                return text[head: i + 1], arg_match.group(1)
        i += 1
    return None, None


def schema_of(body, arg):
    """[{field, columns}] in declaration order, by attributing row[i] reads."""
    column = re.compile(re.escape(arg) + r"\[(0x[0-9a-f]+|\d+)\]")
    fields, cursor = [], 0
    for match in ASSIGN.finditer(body):
        # Everything since the previous field, including this assignment's own
        # expression, is the code that produced this field.
        end = body.find(";", match.end())
        end = len(body) if end < 0 else end
        segment = body[cursor:end]
        columns = sorted({int(c, 16) if c.startswith("0x") else int(c)
                          for c in column.findall(segment)})
        fields.append({"field": match.group(1), "columns": columns})
        cursor = end
    return fields


def build():
    text = decode(BUNDLE.read_text(encoding="utf-8", errors="replace"))
    out = {}
    for match in REGISTER.finditer(text):
        name, var = match.group(1), match.group(2)
        body, arg = constructor_body(text, var, match.start())
        if not body:
            continue
        fields = schema_of(body, arg)
        if fields:
            width = max((c for f in fields for c in f["columns"]), default=-1) + 1
            out[name] = {"columns": width, "fields": fields}
    return out


def load():
    if OUT.exists():
        return json.loads(OUT.read_text(encoding="utf-8"))
    return build()


def read_rows(path_or_bytes, prefix=""):
    """Yield (path, [csv line, ...]). Tables nest, and one record can hold
    several CSV lines - leader_ability packs one line per ability slot."""
    data = Path(path_or_bytes).read_bytes() if isinstance(path_or_bytes, (str, Path)) else path_or_bytes
    for key, record in parse_bytes(data):
        path = f"{prefix}/{key}" if prefix else key
        if record[:2] == b"x\xda":
            try:
                text = zlib.decompress(record).decode("utf-8")
            except zlib.error:
                continue
            lines = [line for line in csv.reader(io.StringIO(text)) if line]
            yield path, lines
        else:
            try:
                yield from read_rows(record, path)
            except Exception:
                continue


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--show", metavar="CLASS")
    ap.add_argument("--decode", metavar="ORDEREDMAP")
    ap.add_argument("--as", dest="as_class", metavar="CLASS")
    ap.add_argument("--limit", type=int, default=3)
    args = ap.parse_args()

    schema = build() if (args.write or not OUT.exists()) else load()

    if args.show:
        entry = schema.get(args.show)
        if not entry:
            sys.exit(f"unknown class {args.show!r}")
        print(f"{args.show}  {entry['columns']} columns")
        for field in entry["fields"]:
            print(f"  [{', '.join(str(c) for c in field['columns']) or '-'}]  {field['field']}")
        return 0

    if args.decode:
        if not args.as_class:
            sys.exit("--decode needs --as <ValuesClass>")
        entry = schema.get(args.as_class)
        if not entry:
            sys.exit(f"unknown class {args.as_class!r}")
        for i, (key, lines) in enumerate(read_rows(args.decode)):
            if i >= args.limit:
                break
            for n, row in enumerate(lines):
                label = f"{key}" if len(lines) == 1 else f"{key}  line {n + 1}/{len(lines)}"
                print(f"\n{label}  ({len(row)} columns, schema expects {entry['columns']})")
                for field in entry["fields"]:
                    values = [row[c] if c < len(row) else "<missing>" for c in field["columns"]]
                    print(f"  {field['field']:<28} {' | '.join(values)}")
        return 0

    total = sum(len(v["fields"]) for v in schema.values())
    print(f"generated master value classes  {len(schema)}")
    print(f"fields                          {total}")
    multi = [(n, f["field"], f["columns"]) for n, v in schema.items()
             for f in v["fields"] if len(f["columns"]) > 1]
    print(f"fields spanning >1 column       {len(multi)}  (why field order alone is not a schema)")
    for name, field, columns in multi[:8]:
        print(f"  {name}.{field} -> columns {columns}")

    if args.write:
        OUT.write_text(json.dumps(schema, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"\nwrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
