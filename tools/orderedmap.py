#!/usr/bin/env python3
"""Read and write World Flipper `.orderedmap` master tables.

Format (verified against all 286 tables in the Trial build):

    file   := u32 index_len, zlib(index), record_bytes
    index  := u32 count, (u32 key_end, u32 record_end) * count, key_bytes
    record := zlib(csv_row) | nested orderedmap | opaque bytes

`key_end` and `record_end` are cumulative end offsets into the concatenated key
blob and the record region, so entry i spans [end(i-1), end(i)).

Values are one of three kinds:

    row   a single zlib stream holding one CSV-like UTF-8 line
    map   a nested orderedmap, same layout all the way down
    blob  anything else, preserved verbatim

Every zlib stream in the shipped data recompresses byte-identically at level 9,
so decode -> encode is lossless without stashing the original bytes. `roundtrip`
proves that per file; run it after touching anything in here.

Commands:

    inspect   <file>...              structure and key summary
    dump      <file> [-o out.json]   decode to JSON
    build     <in.json> <out>        encode JSON back to .orderedmap
    diff      <a> <b>                compare two tables by key
    roundtrip <file>...              decode, re-encode, require identical bytes
"""

import argparse
import base64
import json
import struct
import sys
import zlib
from pathlib import Path

ZLIB_LEVEL = 9
ZLIB_MAGIC = b"x\xda"
FORMAT = "wf-orderedmap/1"


class OrderedMapError(Exception):
    pass


# ---------------------------------------------------------------- decoding


def _split(data):
    if len(data) < 4:
        raise OrderedMapError("too short to hold an index length")
    index_len = struct.unpack("<I", data[:4])[0]
    if 4 + index_len > len(data):
        raise OrderedMapError("index length runs past end of data")
    try:
        index = zlib.decompress(data[4 : 4 + index_len])
    except zlib.error as exc:
        raise OrderedMapError(f"index is not zlib data: {exc}") from exc
    return index, data[4 + index_len :]


def parse_bytes(data):
    """Public alias: [(key, record_bytes)] for one table."""
    return _entries(data)


def _entries(data):
    """Yield (key, record_bytes). Raises OrderedMapError if `data` is not a table."""
    index, body = _split(data)
    if len(index) < 4:
        raise OrderedMapError("index is missing its count")
    count = struct.unpack("<I", index[:4])[0]
    need = 4 + count * 8
    if len(index) < need:
        raise OrderedMapError(f"index declares {count} entries but is too short")
    keys = index[need:]

    out = []
    key_pos = record_pos = 0
    for i in range(count):
        key_end, record_end = struct.unpack("<II", index[4 + i * 8 : 12 + i * 8])
        if key_end < key_pos or record_end < record_pos:
            raise OrderedMapError("offsets are not monotonic")
        if key_end > len(keys) or record_end > len(body):
            raise OrderedMapError("offsets run past end of data")
        out.append((keys[key_pos:key_end].decode("utf-8"), body[record_pos:record_end]))
        key_pos, record_pos = key_end, record_end
    if key_pos != len(keys):
        raise OrderedMapError("trailing bytes in key blob")
    if record_pos != len(body):
        raise OrderedMapError("trailing bytes in record region")
    return out


def _decode_value(record):
    # A row is one zlib stream covering the whole record, which is what makes it
    # distinguishable from a nested table without guessing at header bytes.
    if record[:2] == ZLIB_MAGIC:
        decompressor = zlib.decompressobj()
        try:
            raw = decompressor.decompress(record)
            if not decompressor.unused_data:
                try:
                    return {"kind": "row", "value": raw.decode("utf-8")}
                except UnicodeDecodeError:
                    return {"kind": "blob", "base64": base64.b64encode(record).decode("ascii")}
        except zlib.error:
            pass
    try:
        return {"kind": "map", "entries": [
            dict(key=key, **_decode_value(value)) for key, value in _entries(record)
        ]}
    except (OrderedMapError, UnicodeDecodeError, zlib.error):
        return {"kind": "blob", "base64": base64.b64encode(record).decode("ascii")}


def decode(data):
    return [dict(key=key, **_decode_value(value)) for key, value in _entries(data)]


# ---------------------------------------------------------------- encoding


def _encode_value(entry):
    kind = entry.get("kind")
    if kind == "row":
        return zlib.compress(entry["value"].encode("utf-8"), ZLIB_LEVEL)
    if kind == "map":
        return encode(entry["entries"])
    if kind == "blob":
        return base64.b64decode(entry["base64"])
    raise OrderedMapError(f"unknown value kind {kind!r}")


def encode(entries):
    keys = bytearray()
    records = bytearray()
    offsets = bytearray()
    for entry in entries:
        keys += entry["key"].encode("utf-8")
        records += _encode_value(entry)
        offsets += struct.pack("<II", len(keys), len(records))
    index = struct.pack("<I", len(entries)) + bytes(offsets) + bytes(keys)
    packed = zlib.compress(index, ZLIB_LEVEL)
    return struct.pack("<I", len(packed)) + packed + bytes(records)


# ---------------------------------------------------------------- commands


def _read(path):
    return Path(path).read_bytes()


def _summarize(entries, depth=0, limit=6):
    kinds = {}
    for entry in entries:
        kinds[entry["kind"]] = kinds.get(entry["kind"], 0) + 1
    pad = "  " * (depth + 1)
    shape = ", ".join(f"{v} {k}" for k, v in sorted(kinds.items()))
    print(f"{pad}{len(entries)} entries ({shape})")
    for entry in entries[:limit]:
        if entry["kind"] == "row":
            preview = entry["value"]
            if len(preview) > 100:
                preview = preview[:100] + "..."
            print(f"{pad}  {entry['key']!r} -> {preview}")
        elif entry["kind"] == "map":
            print(f"{pad}  {entry['key']!r} ->")
            _summarize(entry["entries"], depth + 2, limit)
        else:
            print(f"{pad}  {entry['key']!r} -> <blob>")
    if len(entries) > limit:
        print(f"{pad}  ... {len(entries) - limit} more")


def cmd_inspect(args):
    for path in args.files:
        print(f"== {path}")
        try:
            _summarize(decode(_read(path)))
        except OrderedMapError as exc:
            print(f"  ERROR {exc}")
    return 0


def cmd_dump(args):
    payload = {"format": FORMAT, "source": str(args.file), "entries": decode(_read(args.file))}
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
        print(f"wrote {args.output}")
    else:
        print(text)
    return 0


def cmd_build(args):
    payload = json.loads(Path(args.json).read_text(encoding="utf-8"))
    if payload.get("format") != FORMAT:
        sys.exit(f"unexpected format {payload.get('format')!r}, expected {FORMAT!r}")
    Path(args.output).write_bytes(encode(payload["entries"]))
    print(f"wrote {args.output}")
    return 0


def _flatten(entries, prefix=""):
    out = {}
    for entry in entries:
        path = f"{prefix}/{entry['key']}" if prefix else entry["key"]
        if entry["kind"] == "map":
            out.update(_flatten(entry["entries"], path))
        elif entry["kind"] == "row":
            out[path] = entry["value"]
        else:
            out[path] = "<blob>"
    return out


def cmd_diff(args):
    left = _flatten(decode(_read(args.a)))
    right = _flatten(decode(_read(args.b)))
    only_left = sorted(set(left) - set(right))
    only_right = sorted(set(right) - set(left))
    changed = sorted(k for k in set(left) & set(right) if left[k] != right[k])

    print(f"a: {args.a} ({len(left)} rows)")
    print(f"b: {args.b} ({len(right)} rows)\n")
    print(f"  only in a  {len(only_left)}")
    print(f"  only in b  {len(only_right)}")
    print(f"  changed    {len(changed)}")
    for label, keys in (("only in a", only_left), ("only in b", only_right)):
        if keys:
            print(f"\n--- {label} ---")
            for key in keys:
                print(f"  {key}")
    if changed:
        print("\n--- changed ---")
        for key in changed:
            print(f"  {key}\n    a: {left[key]}\n    b: {right[key]}")
    return 1 if (only_left or only_right or changed) else 0


def cmd_roundtrip(args):
    failures = 0
    for path in args.files:
        original = _read(path)
        try:
            rebuilt = encode(decode(original))
        except OrderedMapError as exc:
            print(f"ERROR {path}: {exc}")
            failures += 1
            continue
        if rebuilt != original:
            print(f"DIFFERS {path}: {len(original)} -> {len(rebuilt)} bytes")
            failures += 1
        elif args.verbose:
            print(f"ok {path}")
    print(f"\n{len(args.files) - failures}/{len(args.files)} files round-trip byte-identical")
    return 1 if failures else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("inspect", help="print structure and sample rows")
    p.add_argument("files", nargs="+")
    p.set_defaults(func=cmd_inspect)

    p = sub.add_parser("dump", help="decode to JSON")
    p.add_argument("file")
    p.add_argument("-o", "--output")
    p.set_defaults(func=cmd_dump)

    p = sub.add_parser("build", help="encode JSON back to .orderedmap")
    p.add_argument("json")
    p.add_argument("output")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("diff", help="compare two tables by key")
    p.add_argument("a")
    p.add_argument("b")
    p.set_defaults(func=cmd_diff)

    p = sub.add_parser("roundtrip", help="decode, re-encode, require identical bytes")
    p.add_argument("files", nargs="+")
    p.add_argument("-v", "--verbose", action="store_true")
    p.set_defaults(func=cmd_roundtrip)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
