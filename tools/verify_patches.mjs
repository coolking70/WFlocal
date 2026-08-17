// Checks the patch table in WFTest/game-index.html against the bundle it targets.
//
// Loads the bootstrap's own patch definitions (no second copy to drift out of
// sync), applies them per boot mode, and reports anchor uniqueness plus whether
// the patched bundle still parses.
//
//   node tools/verify_patches.mjs
//
// Exits non-zero on the first problem.

import { existsSync, readFileSync, statSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const bundlePath = resolve(root, "WFTest/world-flipper.js");
const launcherPath = resolve(root, "WFTest/game-index.html");
const MODES = ["tutorial", "challenge", "gacha"];

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

// A patch whose injected code reads WF_INTERNALS only works in the modes where
// expose-internals is applied. The gacha boot router read the enum registry and
// was listed for a mode that did not publish it - the patch table looked fine and
// the mode would have died at the first scene change.
{
	const publisher = patches.find((p) => p.id === "expose-internals");
	if (!publisher) {
		fail("no expose-internals patch: nothing publishes WF_INTERNALS");
	} else {
		let bad = 0;
		for (const patch of patches) {
			if (patch.id === publisher.id || !patch.replace.includes("WF_INTERNALS")) continue;
			const orphans = patch.modes.filter((m) => !publisher.modes.includes(m));
			if (orphans.length) {
				fail(`patch ${patch.id} reads WF_INTERNALS in mode(s) ${orphans.join(", ")} ` +
					`where expose-internals is not applied`);
				bad++;
			}
		}
		if (!bad) console.log("  ok   every patch reading WF_INTERNALS runs where it is published");
	}
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

// The launcher's ?r= on runtime.js must track that file's mtime. A stale stamp
// means the browser can run an older runtime.js than the data expects, which is
// indistinguishable from a broken feature.
{
	const html = readFileSync(launcherPath, "utf8");
	let stale = 0;
	for (const name of ["runtime.js", "orderedmap.js", "hub.js"]) {
		const file = resolve(root, "WFTest/wfmod", name);
		const stamped = new RegExp(name.replace(".", "\\.") + "\\?wfbuild=[0-9.]+&amp;r=(\\d+)").exec(html);
		const mtime = Math.floor(statSync(file).mtimeMs / 1000);
		if (!stamped) {
			fail(`launcher: no cache-buster on wfmod/${name}`);
			stale++;
		} else if (Number(stamped[1]) !== mtime) {
			fail(`launcher: ${name} cache-buster is ${stamped[1]} but the file's mtime is ` +
				`${mtime}; run python3 tools/stamp_assets.py`);
			stale++;
		}
	}
	if (!stale) console.log("  ok   every wfmod script's cache-buster matches its mtime");
}

// Every ADDED_ASSETS entry must name a file that exists and model itself on a
// path the bundle's manifest actually knows. Registration silently no-ops when
// the model is unknown, so catching it here beats catching it as a ClientError
// 8100 in the middle of a quest load.
{
	let decoded = null;
	const manifestText = () => {
		if (decoded === null) {
			decoded = pristine.replace(/\\x([0-9a-fA-F]{2})/g,
				(_, hex) => String.fromCharCode(parseInt(hex, 16)));
		}
		return decoded;
	};
	const runtime = readFileSync(resolve(root, "WFTest/wfmod/runtime.js"), "utf8");
	const block = /var ADDED_ASSETS = \[([\s\S]*?)\n\t\];/.exec(runtime);
	if (!block) {
		fail("runtime.js: could not find ADDED_ASSETS");
	} else {
		const pairs = [...block[1].matchAll(/\["([^"]+)",\s*\n?\s*"([^"]+)"\]/g)];
		let bad = 0;
		for (const [, added, model] of pairs) {
			// Entries are root-relative; runtime.js prepends each asset root. A
			// fully-qualified path here gets the root prepended twice, the model is
			// never found, and registration silently does nothing - which is exactly
			// how a forked skill DSL failed to load.
			if (added.startsWith("assets/") || model.startsWith("assets/")) {
				fail(`ADDED_ASSETS: ${added} must be root-relative, not start with assets/`);
				bad++;
				continue;
			}
			// The added file has to sit in the same asset root as the file it is
			// modelled on. The roots are disjoint for some asset kinds - tutorial
			// terrains exist only under assets/production, main_quest terrains only
			// under assets/trial/production - and a fork written to the wrong root
			// is invisible to the game however correct its contents are. That
			// failure is silent: no 8100, no console line, the shipped file just
			// loads instead, which cost a browser run to notice.
			const roots = ["WFTest/assets/production", "WFTest/assets/trial/production"];
			const modelRoots = roots.filter((r) => existsSync(resolve(root, r, model)));
			if (!modelRoots.length) {
				fail(`ADDED_ASSETS: model ${model} is on disk in neither asset root`);
				bad++;
				continue;
			}
			if (!modelRoots.some((r) => existsSync(resolve(root, r, added)))) {
				fail(`ADDED_ASSETS: ${added} is not in the same asset root as its model ` +
					`${model}, which lives in ${modelRoots.join(", ")}`);
				bad++;
				continue;
			}
			// The manifest lives in the bundle with \xNN-escaped, URL-encoded paths.
			const known = modelRoots.some((r) => manifestText().includes(
				(r.replace("WFTest/", "") + "/" + model).split("/").map(encodeURIComponent).join("%2F")));
			if (!known) {
				fail(`ADDED_ASSETS: model ${model} is not in the bundle manifest`);
				bad++;
			}
		}
		if (!bad) console.log(`  ok   ADDED_ASSETS: ${pairs.length} entries reference real files and known models`);
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
// Exit explicitly. Running runtime.js in the sandbox leaves its polling timers
// pending, and node would otherwise sit on a live event loop for two minutes
// after the last check - which looked like the launcher hanging.
process.exit(0);
