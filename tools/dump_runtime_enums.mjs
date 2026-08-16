// Dump every Haxe enum constructor and its parameter names.
//
// Haxe records constructor parameter names on the constructor function itself
// as __params__, so the DSL's argument semantics do not need the parser to be
// read - they are in the bundle at runtime. Getting at them means actually
// running the bundle, because it registers itself as a lime script and only
// executes when that factory is invoked.
//
//   node tools/dump_runtime_enums.mjs          # summary
//   node tools/dump_runtime_enums.mjs --write  # write reverse/enum_params.json
//
// The bundle is patched in memory only, exactly as the launcher does.

import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const OUT = resolve(root, "reverse/enum_params.json");
const write = process.argv.includes("--write");

// Reuse the launcher's own patch table so this cannot drift from what ships.
function loadBootstrap() {
	const html = readFileSync(resolve(root, "WFTest/game-index.html"), "utf8");
	const blocks = [...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].map((m) => m[1]);
	const body = blocks.filter((b) => b.includes("window.WF_PATCHES")).pop();
	if (!body) throw new Error("no bootstrap block defining window.WF_PATCHES");
	const noop = () => {};
	const sandbox = {
		window: { WF_MOD_BUILD: "dump", WF_DEMO_BOOT_MODE: "challenge" },
		console: { info: noop, warn: noop, error: noop },
		fetch: () => new Promise(() => {}),
		URL: { createObjectURL: () => "blob:dump", revokeObjectURL: noop },
		Blob: class {},
		document: {
			createElement: () => ({ style: {}, setAttribute: noop }),
			getElementById: () => ({ style: {}, remove: noop, setAttribute: noop }),
			body: { appendChild: noop }
		},
		onApplicationLoaded: noop,
		handledApplicationError: noop,
		lime: { embed: noop }
	};
	sandbox.globalThis = sandbox;
	vm.createContext(sandbox);
	new vm.Script(body, { filename: "game-index.html:bootstrap" }).runInContext(sandbox);
	return sandbox.window;
}

function runBundle(source) {
	const stub = () => ({
		style: {}, setAttribute() {}, appendChild() {}, addEventListener() {},
		getContext: () => null, remove() {}, classList: { add() {}, remove() {} }
	});
	const sandbox = {
		console: { log() {}, info() {}, warn() {}, error() {}, debug() {} },
		setTimeout, clearTimeout, setInterval, clearInterval,
		navigator: { userAgent: "node", platform: "node", language: "en" },
		location: { href: "http://localhost/", search: "" },
		performance: { now: () => Date.now() },
		requestAnimationFrame: () => 0,
		XMLHttpRequest: class { open() {} send() {} setRequestHeader() {} addEventListener() {} },
		Image: class {}, Audio: class {}
	};
	sandbox.window = sandbox;
	sandbox.self = sandbox;
	sandbox.globalThis = sandbox;
	sandbox.document = {
		createElement: stub, getElementById: stub, getElementsByTagName: () => [],
		addEventListener() {}, body: stub(), documentElement: stub(), head: stub()
	};
	vm.createContext(sandbox);
	new vm.Script(source, { filename: "world-flipper.patched.js" }).runInContext(sandbox);
	const factory = sandbox.lime?.$scripts?.["world-flipper"];
	if (typeof factory !== "function") throw new Error('lime.$scripts["world-flipper"] missing');
	// Registers every class and enum, then dies starting the app on a stub canvas.
	try { factory(); } catch { /* expected: the DOM stub is not a browser */ }
	const internals = sandbox.window.WF_INTERNALS;
	if (!internals) throw new Error("WF_INTERNALS missing; is the expose-internals patch present?");
	return internals;
}

const win = loadBootstrap();
const pristine = readFileSync(resolve(root, "WFTest/world-flipper.js"), "utf8");
const internals = runBundle(win.WF_APPLY_PATCHES(pristine, "challenge").source);

const out = {};
let constructorCount = 0;
let withParams = 0;
for (const [name, definition] of Object.entries(internals.enums)) {
	const constructs = definition.__constructs__ || [];
	const entry = {};
	for (const key of constructs) {
		const ctor = definition[key];
		constructorCount++;
		if (typeof ctor === "function" && Array.isArray(ctor.__params__)) {
			entry[key] = ctor.__params__;
			withParams++;
		} else {
			entry[key] = [];   // constant constructor, no payload
		}
	}
	out[name] = entry;
}

console.log(`enums        ${Object.keys(out).length}`);
console.log(`constructors ${constructorCount} (${withParams} carry parameters)`);

const dsl = out["pinball.battle.action.dsl.ActionDslCommand"];
if (dsl) {
	console.log("\nActionDslCommand:");
	for (const [name, params] of Object.entries(dsl)) {
		console.log(`  ${name}(${params.join(", ")})`);
	}
}

if (write) {
	writeFileSync(OUT, JSON.stringify(out, null, 1) + "\n", "utf8");
	console.log(`\nwrote ${OUT.replace(root + "/", "")}`);
}
