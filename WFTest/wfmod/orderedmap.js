// Read `.orderedmap` master tables in the browser.
//
// Same format tools/orderedmap.py documents and round-trips byte-identically on
// all 286 shipped tables:
//
//     file   := u32 index_len, zlib(index), record_bytes
//     index  := u32 count, (u32 key_end, u32 record_end) * count, key_bytes
//     record := zlib(csv_row) | nested orderedmap | opaque bytes
//
// Offsets are cumulative ends, so entry i spans [end(i-1), end(i)).
//
// This is read-only on purpose. Writing tables belongs in the Python tools,
// where the round-trip test lives; the browser side only needs to look.
//
// Decoding matches the Python decoder entry for entry - tools/verify_orderedmap_js.mjs
// compares the two over every shipped table and fails on any difference.

(function () {
	"use strict";

	var root = typeof window !== "undefined" ? window : globalThis;

	function inflate(bytes) {
		var pako = root.pako;
		if (!pako) throw new Error("pako is not loaded; orderedmap.js needs it to inflate");
		return pako.inflate(bytes);
	}

	function u32(bytes, at) {
		return (bytes[at] | (bytes[at + 1] << 8) | (bytes[at + 2] << 16) |
			(bytes[at + 3] << 24)) >>> 0;
	}

	var utf8 = typeof TextDecoder !== "undefined" ? new TextDecoder("utf-8", { fatal: true }) : null;

	function text(bytes) {
		if (!utf8) throw new Error("TextDecoder is unavailable");
		return utf8.decode(bytes);
	}

	// [{key, record}] for one table, or throws if `data` is not one. The throw is
	// load-bearing: it is how a nested table is told apart from an opaque blob.
	function entries(data) {
		if (data.length < 4) throw new Error("too short to hold an index length");
		var indexLength = u32(data, 0);
		if (4 + indexLength > data.length) throw new Error("index length runs past end of data");
		var index = inflate(data.subarray(4, 4 + indexLength));
		var body = data.subarray(4 + indexLength);

		if (index.length < 4) throw new Error("index is missing its count");
		var count = u32(index, 0);
		var need = 4 + count * 8;
		if (index.length < need) throw new Error("index declares " + count + " entries but is too short");
		var keys = index.subarray(need);

		var out = [];
		var keyPos = 0, recordPos = 0;
		for (var i = 0; i < count; i++) {
			var keyEnd = u32(index, 4 + i * 8);
			var recordEnd = u32(index, 8 + i * 8);
			if (keyEnd < keyPos || recordEnd < recordPos) throw new Error("offsets are not monotonic");
			if (keyEnd > keys.length || recordEnd > body.length) {
				throw new Error("offsets run past end of data");
			}
			out.push({
				key: text(keys.subarray(keyPos, keyEnd)),
				record: body.subarray(recordPos, recordEnd)
			});
			keyPos = keyEnd;
			recordPos = recordEnd;
		}
		if (keyPos !== keys.length) throw new Error("trailing bytes in key blob");
		if (recordPos !== body.length) throw new Error("trailing bytes in record region");
		return out;
	}

	function base64(bytes) {
		var binary = "";
		for (var i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
		return typeof btoa === "function" ? btoa(binary) : Buffer.from(bytes).toString("base64");
	}

	function decodeValue(record) {
		// A row is one zlib stream covering the whole record, which is what makes
		// it distinguishable from a nested table without guessing at header bytes.
		if (record.length >= 2 && record[0] === 0x78 && record[1] === 0xda) {
			var raw = null;
			try {
				raw = inflate(record);
			} catch (notZlib) {
				raw = null;
			}
			if (raw) {
				try {
					return { kind: "row", value: text(raw) };
				} catch (notText) {
					return { kind: "blob", base64: base64(record) };
				}
			}
		}
		try {
			return {
				kind: "map",
				entries: entries(record).map(function (item) {
					var value = decodeValue(item.record);
					value.key = item.key;
					return value;
				})
			};
		} catch (notATable) {
			return { kind: "blob", base64: base64(record) };
		}
	}

	function decode(data) {
		var bytes = data instanceof Uint8Array ? data : new Uint8Array(data);
		return entries(bytes).map(function (item) {
			var value = decodeValue(item.record);
			value.key = item.key;
			return value;
		});
	}

	// Master rows are CSV with no header; a record can hold several lines, which
	// is how one row packs a list (leader_ability packs one line per slot).
	function rows(entry) {
		if (entry.kind !== "row") return [];
		return entry.value.split("\n").filter(function (line) { return line.length; })
			.map(function (line) { return line.split(","); });
	}

	// Walk to a nested entry: get(table, "111", "1", "4"). main_quest nests three
	// deep, so a flat lookup silently finds nothing.
	function get(list, /* ...path */) {
		var path = Array.prototype.slice.call(arguments, 1);
		var node = list;
		var found = null;
		for (var i = 0; i < path.length; i++) {
			found = null;
			for (var j = 0; j < node.length; j++) {
				if (node[j].key === path[i]) { found = node[j]; break; }
			}
			if (!found) return null;
			node = found.entries || [];
		}
		return found;
	}

	var api = { decode: decode, rows: rows, get: get };
	root.WFMod = root.WFMod || {};
	root.WFMod.orderedmap = api;
	if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
