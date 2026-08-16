// Checks the patch table in WFTest/game-index.html against the bundle it targets.
//
// Loads the bootstrap's own patch definitions (no second copy to drift out of
// sync), applies them per boot mode, and reports anchor uniqueness plus whether
// the patched bundle still parses.
//
//   node tools/verify_patches.mjs
//
// Exits non-zero on the first problem.

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const bundlePath = resolve(root, "WFTest/world-flipper.js");
const launcherPath = resolve(root, "WFTest/game-index.html");
const MODES = ["tutorial", "challenge"];

function loadBootstrap() {
	const html = readFileSync(launcherPath, "utf8");
	// The bootstrap is the last <script> block; it defines the patch table and
	// publishes it on window before it touches the network.
	const blocks = [...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].map((m) => m[1]);
	const body = blocks.filter((b) => b.includes("window.WF_PATCHES")).pop();
	if (!body) throw new Error("no bootstrap block defining window.WF_PATCHES in " + launcherPath);

	const win = { WF_MOD_BUILD: "verify", WF_DEMO_BOOT_MODE: "tutorial" };
	const noop = () => {};
	const sandbox = {
		window: win,
		console: { info: noop, warn: noop, error: noop },
		// Stall the fetch so the bootstrap defines its patches and then does nothing.
		fetch: () => new Promise(() => {}),
		URL: { createObjectURL: () => "blob:verify", revokeObjectURL: noop },
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

	if (!Array.isArray(win.WF_PATCHES) || typeof win.WF_APPLY_PATCHES !== "function") {
		throw new Error("bootstrap did not publish WF_PATCHES / WF_APPLY_PATCHES");
	}
	return win;
}

let failures = 0;
function fail(message) {
	console.error("FAIL " + message);
	failures++;
}

const win = loadBootstrap();
const patches = win.WF_PATCHES;
const pristine = readFileSync(bundlePath, "utf8");

console.log(`bundle   ${bundlePath} (${pristine.length} chars)`);
console.log(`patches  ${patches.length} defined\n`);

const ids = new Set();
for (const patch of patches) {
	for (const field of ["id", "modes", "find", "replace", "note"]) {
		if (!patch[field]) fail(`patch ${patch.id || "?"}: missing '${field}'`);
	}
	if (ids.has(patch.id)) fail(`duplicate patch id '${patch.id}'`);
	ids.add(patch.id);
	for (const mode of patch.modes) {
		if (!MODES.includes(mode)) fail(`patch ${patch.id}: unknown mode '${mode}'`);
	}

	// Anchors are matched against the pristine bundle. Patches never overlap, so
	// each must already be unique before any of them is applied.
	let count = 0;
	for (let at = pristine.indexOf(patch.find); at >= 0; at = pristine.indexOf(patch.find, at + 1)) count++;
	const status = count === 1 ? "ok  " : "BAD ";
	console.log(`  ${status} ${patch.id.padEnd(22)} anchors=${count}  modes=${patch.modes.join(",")}`);
	if (count !== 1) fail(`patch ${patch.id}: expected exactly 1 anchor, found ${count}`);
}

// Hooks must not be tied to the bundle's load event. The bundle boots itself and
// its script never fires onload, so anything waiting on that never runs - which
// is how the dev aids silently did nothing. The launcher has to wait for
// WF_INTERNALS instead.
{
	const html = readFileSync(launcherPath, "utf8");
	if (!html.includes("window.WF_INTERNALS")) {
		fail("launcher: hooks are not gated on window.WF_INTERNALS appearing");
	} else if (/onload[\s\S]{0,200}applyHooks\(\)/.test(html)) {
		fail("launcher: applyHooks() is driven by a script load event again");
	} else {
		console.log("\n  ok   hooks wait for window.WF_INTERNALS, not a load event");
	}
}

console.log("");
for (const mode of MODES) {
	let result;
	try {
		result = win.WF_APPLY_PATCHES(pristine, mode);
	} catch (error) {
		fail(`${mode}: applying patches threw: ${error.message}`);
		continue;
	}
	const expected = patches.filter((p) => p.modes.includes(mode)).map((p) => p.id);
	if (result.applied.join(",") !== expected.join(",")) {
		fail(`${mode}: applied [${result.applied}] but expected [${expected}]`);
	}
	try {
		new vm.Script(result.source, { filename: `world-flipper.${mode}.js` });
	} catch (error) {
		fail(`${mode}: patched bundle does not parse: ${error.message}`);
		continue;
	}
	console.log(`  ok   ${mode.padEnd(10)} ${result.applied.length} patches, ${result.source.length} chars, parses`);
}

// Integration check for the runtime bridge, against the real bundle.
//
// A stand-in registry is not good enough here: it was a fake registry that let
// a broken build pass, because the real question is *when* WF_INTERNALS exists.
// The bundle registers itself as lime.$scripts["world-flipper"] and only runs
// when that factory is invoked, so this runs it for real, then hooks the real
// prototypes and calls the hooked method.
console.log("");
{
	const patched = win.WF_APPLY_PATCHES(pristine, "challenge").source;
	const stubElement = () => ({
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
		createElement: stubElement, getElementById: stubElement, getElementsByTagName: () => [],
		addEventListener() {}, body: stubElement(), documentElement: stubElement(), head: stubElement()
	};
	vm.createContext(sandbox);

	try {
		new vm.Script(patched, { filename: "world-flipper.patched.js" }).runInContext(sandbox);
		const factory = sandbox.lime && sandbox.lime.$scripts && sandbox.lime.$scripts["world-flipper"];
		if (typeof factory !== "function") {
			throw new Error('lime.$scripts["world-flipper"] is not a function');
		}
		// The factory registers every class, then tries to start the app and dies on
		// the stub canvas. Everything this check needs is registered by then.
		try { factory(); } catch (expected) { /* DOM stub is not a browser */ }

		const internals = sandbox.window.WF_INTERNALS;
		if (!internals || !internals.classes) {
			fail("expose-internals: WF_INTERNALS missing after the module factory ran");
		} else {
			const classCount = Object.keys(internals.classes).length;
			console.log(`  ok   WF_INTERNALS published (${classCount} classes, ` +
				`${Object.keys(internals.enums).length} enums)`);

			new vm.Script(readFileSync(resolve(root, "WFTest/wfmod/runtime.js"), "utf8"), {
				filename: "wfmod/runtime.js"
			}).runInContext(sandbox);
			const result = sandbox.window.WFMod.runtime.applyHooks();
			if (result.failed.length) {
				fail(`runtime hooks failed against the real bundle: ${result.failed.join(", ")}`);
			} else {
				const scene = internals.classes["pinball.scene.battle.BattleScene"];
				const value = scene.prototype.get_autoPlayUnlocked.call({});
				if (value !== true) {
					fail(`hooked get_autoPlayUnlocked returned ${value}, expected true`);
				} else {
					console.log(`  ok   runtime hooks applied to the real prototypes ` +
						`(${result.applied.join(", ")})`);
				}
			}
		}
	} catch (error) {
		fail(`runtime bridge check could not run: ${error.message}`);
	}
}

console.log("");
if (failures) {
	console.error(`${failures} problem(s) found`);
	process.exit(1);
}
console.log("all checks passed");
