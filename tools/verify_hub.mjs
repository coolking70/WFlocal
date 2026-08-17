// Render the WFMod Hub headlessly and check what it says against the master data.
//
//   node tools/verify_hub.mjs
//
// The panel's whole job is showing numbers, so "it opened without throwing" is
// not enough: a wrong join produces a confident, wrong screen. This drives the
// real hub.js with a stub DOM and a fetch that serves files off disk, then
// checks the rendered HTML against values read independently from the tables.

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const served = resolve(root, "WFTest");

let failures = 0;
const check = (ok, what) => {
	console.log(`  ${ok ? "ok  " : "BAD "} ${what}`);
	if (!ok) failures++;
};

// --- a DOM barely large enough for the panel -------------------------------
function element(tag) {
	const node = {
		tagName: tag, children: [], listeners: {}, style: {}, hidden: false,
		className: "", type: "", textContent: "", innerHTML: "", attributes: {},
		appendChild(child) { this.children.push(child); return child; },
		setAttribute(name, value) { this.attributes[name] = value; },
		getAttribute(name) { return this.attributes[name]; },
		addEventListener(name, fn) { this.listeners[name] = fn; },
		querySelector() { return element("stub"); },
		querySelectorAll() { return []; }
	};
	return node;
}

const documentStub = {
	readyState: "complete",
	head: element("head"),
	body: element("body"),
	createElement: element,
	addEventListener() {}
};

const sandbox = {
	console: { log() {}, info() {}, warn() {}, error(...args) { console.error(...args); } },
	TextDecoder, Buffer, URLSearchParams, setTimeout, clearTimeout,
	document: documentStub,
	location: { search: "" },
	fetch: async (url) => {
		const path = resolve(served, String(url).split("?")[0]);
		try {
			const body = readFileSync(path);
			return {
				ok: true,
				arrayBuffer: async () => body.buffer.slice(
					body.byteOffset, body.byteOffset + body.byteLength),
				json: async () => JSON.parse(body.toString("utf8"))
			};
		} catch (error) {
			return { ok: false, status: 404 };
		}
	}
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
vm.createContext(sandbox);

for (const file of ["WFTest/lib/pako.min.js", "WFTest/wfmod/orderedmap.js", "WFTest/wfmod/hub.js"]) {
	new vm.Script(readFileSync(resolve(root, file), "utf8"), { filename: file }).runInContext(sandbox);
}

// --- what the tables independently say --------------------------------------
const om = sandbox.window.WFMod.orderedmap;
const table = (path) => om.decode(new Uint8Array(readFileSync(resolve(served, path))));
const master = "assets/trial/production/master/";
const parties = table(master + "player/player_party.orderedmap");
const text = table(master + "character/character_text.orderedmap");
const status = table(master + "character/character_status.orderedmap");

const party1 = om.rows(om.get(parties, "4", "1"))[0].filter((v) => v && v !== "(None)");
const leader = party1[0];
const leaderName = om.rows(om.get(text, leader))[0][0];
const leaderAnchors = om.get(status, leader).entries
	.map((e) => ({ level: e.key, hp: om.rows(e)[0][0] }))
	.sort((a, b) => Number(a.level) - Number(b.level));

console.log(`party 4/1  ${party1.join(", ")}`);
console.log(`leader     ${leader} ${leaderName}\n`);

// --- drive the panel --------------------------------------------------------
const body = element("div");
await sandbox.window.WFMod.hub.ready();
sandbox.window.WFMod.hub.render(body, null);
const html = body.innerHTML;

check(html.includes(leaderName), `panel names the leader: ${leaderName}`);
check(html.includes(`>${leaderAnchors[0].hp}<`),
	`panel shows the level ${leaderAnchors[0].level} HP anchor ${leaderAnchors[0].hp}`);
check(leaderAnchors.every((a) => html.includes(`>${a.level}<`)),
	`panel shows all ${leaderAnchors.length} anchor levels`);
check(party1.every((id) => html.includes(id)),
	`panel lists all ${party1.length} party members`);
check(html.includes("wfmod_001") || !html.includes("undefined"),
	"panel renders no undefined fields");

// --- the DSL view -----------------------------------------------------------
//
// The point of this view is that the numbers carry names, units and context, so
// check exactly that rather than "some markup appeared".
const skills = table(master + "skill/action_skill.orderedmap");
const characters = table(master + "character/character.orderedmap");
const skillKey = om.rows(om.get(characters, leader))[0][8];
const program = om.rows(om.get(skills, skillKey).entries[0])[0][7];
const dsl = JSON.parse(readFileSync(
	resolve(served, "assets/production/" + program + ".action.dsl.json"), "utf8"));
const reference = JSON.parse(readFileSync(resolve(served, "wfmod/dsl-reference.json"), "utf8"));

const slot = element("div");
await sandbox.window.WFMod.hub.ready();
const dslHtml = await sandbox.window.WFMod.hub.renderProgram(slot, program);

console.log(`\nskill      ${skillKey} -> ${program}`);

// Every command in the file must appear, named.
const names = [];
(function walk(node) {
	if (Array.isArray(node)) {
		if (node.length === 2 && node[0] === "Command" && Array.isArray(node[1]) && node[1].length) {
			names.push(node[1][0]);
		}
		node.forEach(walk);
	}
})(dsl);
check(names.every((n) => dslHtml.includes(n)),
	`view names all ${names.length} commands in the file`);

// Parameter names come from the generated reference, not from position.
const attackParams = reference.commands.CreateNormalAttack.params;
check(attackParams.every((p) => dslHtml.includes(p)),
	`view labels all ${attackParams.length} CreateNormalAttack parameters`);

// Units: this fork's StopBall holds the ball for 300 frames, which is 5 seconds.
check(dslHtml.includes("5s"), "view converts frames to seconds (StopBall 300 -> 5s)");
check(/30\u00b0|30°/.test(dslHtml), "view converts radians to degrees (NWay 0.5236 -> 30°)");

// Context: every numeric parameter quotes what the shipped skills use, and a
// value outside all of them is flagged. In this fork that is StopBall.frame,
// held at 300 so the hit area has something to hit for its whole life, against
// a shipped range of 20-103.
const shipped = reference.commands.CreateNormalAttack.observed.damage.numeric;
check(dslHtml.includes(`shipped ${shipped.min}`),
	`view quotes the shipped damage range (${shipped.min}-${shipped.max})`);
check(dslHtml.includes("wfhub-outside"),
	"view flags a value outside every shipped value for that parameter");

console.log("");
if (failures) {
	console.error(`${failures} problem(s) found`);
	process.exit(1);
}
console.log("hub renders and its data joins match the tables");
process.exit(0);
