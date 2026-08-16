// WFMod Hub - an overlay that shows the numbers the demo's own party screen does not.
//
// Opened with ?wfhub=1, or from the small button it puts in the corner. It reads
// the master tables straight off the server with wfmod/orderedmap.js, so it shows
// the *designed* values - what the data says - rather than whatever a battle
// happened to compute. Nothing here touches the game: no hooks, no patches, and
// the panel lives outside the canvas.
//
// Why an overlay rather than the game's own party screen: that screen is Starling
// and Flatomo inside a 29MB obfuscated bundle. An overlay can also show the whole
// character -> skill -> DSL chain on one surface, which the original never did,
// and it is the natural place to grow editing later.
//
// The data it joins, all keyed the way reverse/character-skill-chain.md describes:
//
//   player_party     <save>/<party>   3 main + 3 unison character ids
//   player_character <save>/<id>      level
//   character        <id>             rarity, element, action_skill key
//   character_text   <id>             name, nickname, skill text
//   character_status <id>/<level>     hp, atk - anchors only, at 1/10/80/100
//   action_skill     <key>/<level>    skill name, description, program_path

(function () {
	"use strict";

	var root = typeof window !== "undefined" ? window : globalThis;
	var log = (root.__wfConsole) || console;

	var ROOT = "assets/trial/production/master/";
	var TABLES = {
		party: ROOT + "player/player_party.orderedmap",
		owned: ROOT + "player/player_character.orderedmap",
		character: ROOT + "character/character.orderedmap",
		text: ROOT + "character/character_text.orderedmap",
		status: ROOT + "character/character_status.orderedmap",
		skill: ROOT + "skill/action_skill.orderedmap"
	};

	// The challenge boot path loads player save 4 (see game-index.html), so that
	// is the save whose parties are worth showing.
	var SAVE = "4";

	var ELEMENTS = { "0": "火", "1": "水", "2": "雷", "3": "風", "4": "光", "5": "闇" };

	var data = null;

	function url(path) {
		var build = root.WF_MOD_BUILD || "dev";
		return path + "?wfbuild=" + encodeURIComponent(build);
	}

	function load() {
		var names = Object.keys(TABLES);
		return Promise.all(names.map(function (name) {
			return fetch(url(TABLES[name]), { cache: "no-cache" }).then(function (response) {
				if (!response.ok) throw new Error(TABLES[name] + " -> HTTP " + response.status);
				return response.arrayBuffer();
			});
		})).then(function (buffers) {
			var out = {};
			names.forEach(function (name, i) {
				out[name] = root.WFMod.orderedmap.decode(new Uint8Array(buffers[i]));
			});
			return out;
		});
	}

	var om = function () { return root.WFMod.orderedmap; };

	function cells(entry) {
		var lines = entry && om().rows(entry);
		return (lines && lines[0]) || [];
	}

	function member(id) {
		var character = cells(om().get(data.character, id));
		var text = cells(om().get(data.text, id));
		var level = cells(om().get(data.owned, SAVE, id))[0] || null;
		var skillKey = character[8] || null;

		var anchors = [];
		var status = om().get(data.status, id);
		if (status && status.entries) {
			status.entries.forEach(function (row) {
				var value = cells(row);
				anchors.push({ level: Number(row.key), hp: Number(value[0]), atk: Number(value[1]) });
			});
			anchors.sort(function (a, b) { return a.level - b.level; });
		}

		var skill = null;
		if (skillKey) {
			var levels = om().get(data.skill, skillKey);
			var first = levels && levels.entries && levels.entries[0];
			if (first) {
				var s = cells(first);
				skill = {
					key: skillKey, level: first.key, name: s[0], description: s[1],
					unisonable: s[3], weight: s[4] + "/" + s[5], program: s[7]
				};
			}
		}

		return {
			id: id,
			name: text[0] || "(no character_text row)",
			nickname: text[2] || "",
			rarity: character[2] || "?",
			element: ELEMENTS[character[3]] || character[3] || "?",
			race: character[4] || "",
			level: level,
			anchors: anchors,
			skill: skill,
			missing: !character.length
		};
	}

	function parties() {
		var save = om().get(data.party, SAVE);
		if (!save || !save.entries) return [];
		return save.entries.map(function (entry) {
			var ids = cells(entry).filter(function (v) { return v && v !== "(None)"; });
			return { key: entry.key, ids: ids };
		}).filter(function (party) {
			return party.ids.length > 1;      // the empty slots are all a lone "1"
		});
	}

	function escape(value) {
		return String(value === null || value === undefined ? "" : value)
			.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
	}

	function anchorRow(member) {
		if (!member.anchors.length) return '<div class="wfhub-none">character_status has no rows for this id</div>';
		var head = "<tr><th>Lv</th>" + member.anchors.map(function (a) {
			return "<th>" + a.level + "</th>";
		}).join("") + "</tr>";
		var hp = "<tr><td>HP</td>" + member.anchors.map(function (a) {
			return "<td>" + a.hp + "</td>";
		}).join("") + "</tr>";
		var atk = "<tr><td>ATK</td>" + member.anchors.map(function (a) {
			return "<td>" + a.atk + "</td>";
		}).join("") + "</tr>";
		return "<table class=\"wfhub-anchors\">" + head + hp + atk + "</table>";
	}

	function card(m, role) {
		if (m.missing) {
			return '<article class="wfhub-card wfhub-missing"><h3>' + escape(m.id) +
				"</h3><p>no row in master character</p></article>";
		}
		var skill = m.skill
			? '<div class="wfhub-skill"><div class="wfhub-skill-name">' + escape(m.skill.name) +
				'<span class="wfhub-tag">Lv' + escape(m.skill.level) + "</span></div>" +
				"<p>" + escape(m.skill.description) + "</p>" +
				'<code>' + escape(m.skill.key) + " &rarr; " + escape(m.skill.program) + "</code>" +
				'<div class="wfhub-meta">unisonable ' + escape(m.skill.unisonable) +
				" &middot; weight " + escape(m.skill.weight) + "</div></div>"
			: '<div class="wfhub-none">character.action_skill points nowhere</div>';

		return '<article class="wfhub-card">' +
			'<header><span class="wfhub-role">' + escape(role) + "</span>" +
			"<h3>" + escape(m.name) + "</h3>" +
			'<div class="wfhub-sub">' + escape(m.nickname) + "</div>" +
			'<div class="wfhub-meta">' + escape(m.id) + " &middot; " + escape(m.element) +
			" &middot; &#9733;" + escape(m.rarity) + " &middot; " + escape(m.race) +
			" &middot; Lv " + escape(m.level === null ? "not owned" : m.level) + "</div></header>" +
			anchorRow(m) + skill + "</article>";
	}

	function render(container, partyKey) {
		var all = parties();
		if (!all.length) {
			container.innerHTML = '<p class="wfhub-none">save ' + SAVE + " has no populated party</p>";
			return;
		}
		var chosen = all.filter(function (p) { return p.key === partyKey; })[0] || all[0];

		var tabs = all.map(function (p) {
			return '<button class="wfhub-tab' + (p === chosen ? " wfhub-on" : "") +
				'" data-party="' + escape(p.key) + '">Party ' + escape(p.key) + "</button>";
		}).join("");

		var cards = chosen.ids.map(function (id, i) {
			return card(member(id), i === 0 ? "leader" : (i < 3 ? "main " + (i + 1) : "unison " + (i - 2)));
		}).join("");

		container.innerHTML =
			'<div class="wfhub-tabs">' + tabs + "</div>" +
			'<div class="wfhub-grid">' + cards + "</div>" +
			'<footer class="wfhub-foot">character_status ships four anchor levels ' +
			"(1 / 10 / 80 / 100). The value at any other level is interpolated by the " +
			"game and the curve has not been established here, so this shows the anchors " +
			"rather than a number it cannot justify. In-battle values also carry leader " +
			"and ability bonuses on top.</footer>";

		Array.prototype.forEach.call(container.querySelectorAll(".wfhub-tab"), function (button) {
			button.addEventListener("click", function () {
				render(container, button.getAttribute("data-party"));
			});
		});
	}

	var CSS = [
		".wfhub{position:fixed;top:0;right:0;bottom:0;width:min(560px,100vw);z-index:99999;",
		"background:#12141a;color:#e6e8ee;font:13px/1.55 system-ui,-apple-system,'Segoe UI',sans-serif;",
		"box-shadow:-8px 0 32px rgba(0,0,0,.55);display:flex;flex-direction:column}",
		".wfhub[hidden]{display:none}",
		".wfhub-bar{display:flex;align-items:center;gap:10px;padding:12px 16px;border-bottom:1px solid #262a35}",
		".wfhub-bar h2{margin:0;font-size:14px;font-weight:600;letter-spacing:.02em}",
		".wfhub-bar .wfhub-meta{margin-left:auto}",
		".wfhub-body{overflow:auto;padding:12px 16px 24px}",
		".wfhub-tabs{display:flex;gap:6px;margin-bottom:12px;flex-wrap:wrap}",
		".wfhub-tab{background:#1b1f29;color:#9aa3b5;border:1px solid #2b3140;border-radius:6px;",
		"padding:4px 10px;font:inherit;cursor:pointer}",
		".wfhub-tab.wfhub-on{background:#2b3550;color:#e6e8ee;border-color:#3d4a6b}",
		".wfhub-card{background:#181c25;border:1px solid #252b38;border-radius:8px;padding:12px 14px;margin-bottom:10px}",
		".wfhub-card h3{margin:2px 0 0;font-size:15px}",
		".wfhub-role{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:#6f7a90}",
		".wfhub-sub{color:#9aa3b5}",
		".wfhub-meta{color:#6f7a90;font-size:12px}",
		".wfhub-anchors{border-collapse:collapse;margin:10px 0;font-variant-numeric:tabular-nums}",
		".wfhub-anchors th,.wfhub-anchors td{border:1px solid #262c3a;padding:2px 10px;text-align:right}",
		".wfhub-anchors th:first-child,.wfhub-anchors td:first-child{text-align:left;color:#6f7a90}",
		".wfhub-skill{border-top:1px solid #262c3a;padding-top:8px}",
		".wfhub-skill-name{font-weight:600}",
		".wfhub-skill p{margin:4px 0;color:#c2c8d6}",
		".wfhub-skill code{display:block;color:#8fa6d8;font-size:11px;word-break:break-all;margin:6px 0}",
		".wfhub-tag{margin-left:6px;font-size:11px;color:#6f7a90;font-weight:400}",
		".wfhub-none{color:#c98b8b}",
		".wfhub-missing{border-color:#5a2b2b}",
		".wfhub-foot{color:#6f7a90;font-size:12px;margin-top:8px}",
		".wfhub-x{background:none;border:1px solid #2b3140;color:#9aa3b5;border-radius:6px;cursor:pointer;",
		"padding:2px 9px;font:inherit}",
		".wfhub-open{position:fixed;right:12px;bottom:12px;z-index:99998;background:#2b3550;color:#e6e8ee;",
		"border:1px solid #3d4a6b;border-radius:6px;padding:6px 12px;cursor:pointer;",
		"font:13px system-ui,-apple-system,sans-serif}"
	].join("");

	var panel = null;

	function build() {
		if (panel) return panel;
		var style = document.createElement("style");
		style.textContent = CSS;
		document.head.appendChild(style);

		panel = document.createElement("aside");
		panel.className = "wfhub";
		panel.hidden = true;
		panel.innerHTML =
			'<div class="wfhub-bar"><h2>WFMod Hub</h2>' +
			'<span class="wfhub-meta">save ' + SAVE + " &middot; master data</span>" +
			'<button class="wfhub-x" type="button">close</button></div>' +
			'<div class="wfhub-body">loading master tables&hellip;</div>';
		document.body.appendChild(panel);
		panel.querySelector(".wfhub-x").addEventListener("click", close);

		var opener = document.createElement("button");
		opener.className = "wfhub-open";
		opener.type = "button";
		opener.textContent = "WFMod Hub";
		opener.addEventListener("click", open);
		document.body.appendChild(opener);
		return panel;
	}

	function open() {
		build();
		panel.hidden = false;
		var body = panel.querySelector(".wfhub-body");
		if (data) { render(body, null); return; }
		body.textContent = "loading master tables…";
		load().then(function (loaded) {
			data = loaded;
			render(body, null);
			log.info("[WFMod] hub loaded " + Object.keys(TABLES).length + " master tables");
		}).catch(function (error) {
			body.innerHTML = '<p class="wfhub-none">could not read the master tables: ' +
				escape(error.message) + "</p>";
			log.error("[WFMod] hub failed to load master tables", error);
		});
	}

	function close() {
		if (panel) panel.hidden = true;
	}

	function autoOpen() {
		build();
		var params = new URLSearchParams(root.location ? root.location.search : "");
		if (params.get("wfhub")) open();
	}

	// `ready` and `render` are the testable surface: tools/verify_hub.mjs loads the
	// tables and renders into its own node, so a broken join fails a check here
	// instead of showing a confident, wrong screen in the browser.
	function ready() {
		if (data) return Promise.resolve(data);
		return load().then(function (loaded) { data = loaded; return data; });
	}

	root.WFMod = root.WFMod || {};
	root.WFMod.hub = {
		open: open, close: close, ready: ready, render: render,
		reload: function () { data = null; open(); }
	};

	if (typeof document !== "undefined") {
		if (document.readyState === "loading") {
			document.addEventListener("DOMContentLoaded", autoOpen);
		} else {
			autoOpen();
		}
	}
})();
