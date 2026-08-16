// Check the browser orderedmap reader against the Python one, table by table.
//
// The browser side of the Mod Hub reads the same master tables the Python tools
// do. Two decoders of the same format drift, and a decoder that is subtly wrong
// produces plausible-looking numbers rather than an error - so compare them over
// every shipped table instead of trusting a sample.
//
//   node tools/verify_orderedmap_js.mjs
//
// Exits non-zero on the first difference.

import { execFileSync } from "node:child_process";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const assets = resolve(root, "WFTest/assets");

function tables(dir) {
	const out = [];
	for (const name of readdirSync(dir)) {
		const path = join(dir, name);
		if (statSync(path).isDirectory()) out.push(...tables(path));
		else if (name.endsWith(".orderedmap")) out.push(path);
	}
	return out;
}

// Load pako and the reader the same way the page does: as plain scripts sharing
// one global. Testing what the browser actually loads beats testing a bespoke
// module wrapper that only exists here.
const sandbox = { console, TextDecoder, Buffer };
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
for (const file of ["WFTest/lib/pako.min.js", "WFTest/wfmod/orderedmap.js"]) {
	new vm.Script(readFileSync(resolve(root, file), "utf8"), { filename: file }).runInContext(sandbox);
}
const orderedmap = sandbox.window.WFMod.orderedmap;

const files = tables(assets).sort();
console.log(`tables  ${files.length}`);

let failures = 0;
for (const file of files) {
	const shown = relative(root, file);
	let expected;
	try {
		expected = JSON.parse(execFileSync("python3", [
			"-c",
			"import sys,json; sys.path.insert(0,'tools'); import orderedmap;" +
			"sys.stdout.write(json.dumps(orderedmap.decode(open(sys.argv[1],'rb').read()), ensure_ascii=False))",
			file
		], { cwd: root, maxBuffer: 1 << 28 }).toString("utf8"));
	} catch (error) {
		console.error(`FAIL ${shown}: python decoder errored: ${error.message}`);
		failures++;
		continue;
	}

	let actual;
	try {
		actual = orderedmap.decode(new Uint8Array(readFileSync(file)));
	} catch (error) {
		console.error(`FAIL ${shown}: js decoder threw: ${error.message}`);
		failures++;
		continue;
	}

	// Python emits key first, the reader attaches it last; compare by value, not
	// by key order.
	const normalise = (node) => node.map((entry) => {
		const out = { key: entry.key, kind: entry.kind };
		if (entry.kind === "row") out.value = entry.value;
		else if (entry.kind === "map") out.entries = normalise(entry.entries);
		else out.base64 = entry.base64;
		return out;
	});

	const a = JSON.stringify(normalise(expected));
	const b = JSON.stringify(normalise(actual));
	if (a !== b) {
		console.error(`FAIL ${shown}: decoders disagree`);
		for (let i = 0; i < Math.min(a.length, b.length); i++) {
			if (a[i] !== b[i]) {
				console.error(`  first difference at ${i}`);
				console.error(`  python: ${a.slice(Math.max(0, i - 60), i + 60)}`);
				console.error(`  js    : ${b.slice(Math.max(0, i - 60), i + 60)}`);
				break;
			}
		}
		failures++;
	}
}

if (failures) {
	console.error(`\n${failures} table(s) decoded differently`);
	process.exit(1);
}
console.log(`${files.length}/${files.length} tables decode identically in both readers`);
process.exit(0);
