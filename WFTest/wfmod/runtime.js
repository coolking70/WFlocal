// WFMod runtime layer.
//
// The `expose-internals` patch publishes Haxe's own class and enum registries
// as window.WF_INTERNALS, keyed by real names ("pinball.scene.battle.BattleScene").
// That turns most behaviour changes into ordinary prototype patching, which is
// far easier to read and to keep working than another string replacement
// against a 29MB obfuscated bundle.
//
// What this can and cannot do:
//
//   can     replace or wrap a prototype method, read statics, read enums
//   cannot  intercept `new Foo(...)` where the bundle calls a class through its
//           own local variable, or reach a live instance that nothing hands us
//
// So patches that rewrite a whole method belong here. Patches that inject code
// mid-statement, or that must run before any instance exists, stay in the
// declarative table in game-index.html.
//
// Load this after world-flipper.js and call WFMod.runtime.applyHooks().

(function () {
	"use strict";

	var applied = [];
	var failed = [];

	function internals() {
		return typeof window !== "undefined" ? window.WF_INTERNALS : null;
	}

	function getClass(name) {
		var registry = internals();
		if (!registry || !registry.classes) return null;
		return registry.classes[name] || null;
	}

	function getEnum(name) {
		var registry = internals();
		if (!registry || !registry.enums) return null;
		return registry.enums[name] || null;
	}

	// Replace a prototype method outright. `factory` receives the original so a
	// hook can delegate to it.
	function hook(className, methodName, factory) {
		var clazz = getClass(className);
		if (!clazz || !clazz.prototype) {
			failed.push(className + "." + methodName + " (class not found)");
			return false;
		}
		var original = clazz.prototype[methodName];
		if (typeof original !== "function") {
			failed.push(className + "." + methodName + " (not a method)");
			return false;
		}
		clazz.prototype[methodName] = factory(original);
		applied.push(className + "." + methodName);
		return true;
	}

	// --- assets -----------------------------------------------------------
	//
	// The asset manifest is baked into the pristine bundle, so a path it does not
	// know cannot be loaded: pinball's readAssetFile() asks lime Assets.exists()
	// and throws ClientError 8100 when the answer is no. Rather than editing the
	// serialized manifest, register the path with the live AssetLibrary, which
	// keeps id -> url in `paths`, plus `types` and `sizes`.
	//
	// `like` is an existing asset of the same kind: its type is copied, because
	// the value is a Haxe enum we would otherwise have to reconstruct, and so is
	// its size, which lime only uses for load-progress accounting.
	function libraries() {
		var Assets = getClass("lime.utils.Assets");
		var map = Assets && Assets.libraries;
		if (!map) return [];
		var raw = map.h || map;          // Haxe StringMap keeps entries under .h
		return Object.keys(raw).map(function (k) { return raw[k]; });
	}

	function addAsset(path, like) {
		var added = 0;
		var seen = false;
		libraries().forEach(function (library) {
			if (!library || !library.paths || !library.types) return;
			var paths = library.paths.h || library.paths;
			var types = library.types.h || library.types;
			var sizes = (library.sizes && (library.sizes.h || library.sizes)) || {};
			if (!(like in paths)) return;    // not the library holding `like`
			seen = true;
			if (path in paths) return;       // already registered
			paths[path] = path;
			types[path] = types[like];
			sizes[path] = sizes[like];
			added++;
		});
		if (!seen) return false;
		return added > 0;
	}

	// Assets WFMod adds on top of the shipped package, as [path, modelled on].
	//
	// boss_shield is required by the CreateShield DSL command - the bundle names
	// it in a switch keyed by command index - but the demo does not ship it. These
	// four files are boss_target_sight renamed, which is enough to prove the
	// command runs; they are a placeholder, not artwork.
	var ADDED_ASSETS = [
		["battle/boss/common/boss_shield/boss_shield.timeline.json",
			"battle/boss/common/boss_target_sight/boss_target_sight.timeline.json"],
		["battle/boss/common/boss_shield/boss_shield.atlas.json",
			"battle/boss/common/boss_target_sight/boss_target_sight.atlas.json"],
		["battle/boss/common/boss_shield/boss_shield.parts.json",
			"battle/boss/common/boss_target_sight/boss_target_sight.parts.json"],
		["battle/boss/common/boss_shield/boss_shield.png",
			"battle/boss/common/boss_target_sight/boss_target_sight.png"]
	];

	function knows(like) {
		return libraries().some(function (library) {
			var paths = library && library.paths && (library.paths.h || library.paths);
			return paths && (like in paths);
		});
	}

	// lime.embed() only *starts* the app; the asset manifest is fetched after it
	// returns, so no library exists yet when hooks are installed. Keep retrying
	// until the library that owns the model asset shows up. The quest that needs
	// these is many menus away, so a short poll is ample.
	function registerAssets(intervalMs, timeoutMs) {
		intervalMs = intervalMs || 250;
		timeoutMs = timeoutMs || 60000;
		var pending = [];
		ADDED_ASSETS.forEach(function (pair) {
			// The game resolves names against devConfig.assetDirectories, so offer
			// the same candidates it will ask for.
			["assets/production/", "assets/trial/production/"].forEach(function (root) {
				pending.push({ path: root + pair[0], like: root + pair[1] });
			});
		});

		var deadline = Date.now() + timeoutMs;
		var registered = 0;
		var timer = setInterval(function () {
			pending = pending.filter(function (item) {
				if (!knows(item.like)) return true;          // library not loaded yet
				if (addAsset(item.path, item.like)) registered++;
				return false;
			});
			if (!pending.length) {
				clearInterval(timer);
				if (registered) {
					console.info("[WFMod] registered " + registered + " added assets with the lime library");
				}
				return;
			}
			if (Date.now() > deadline) {
				clearInterval(timer);
				console.error("[WFMod] gave up registering " + pending.length +
					" added assets; the lime library never reported: " +
					pending.map(function (i) { return i.like; }).join(", "));
			}
		}, intervalMs);
	}

	// --- development aids -------------------------------------------------
	//
	// Off unless the launcher URL asks for them: ?wfdev=fastskill, or
	// ?wfdev=fastskill:2000 to choose the bonus. They change how the game plays,
	// so they announce themselves loudly and never run by default.
	function devFlag(name) {
		var raw = (typeof window !== "undefined" && window.WF_DEV) || "";
		var found = null;
		raw.split(",").forEach(function (part) {
			var bits = part.split(":");
			if (bits[0].trim() === name) found = bits.length > 1 ? Number(bits[1]) : true;
		});
		return found;
	}

	function applyDevAids() {
		// Members take their opening gauge from the battle-continuation data:
		//   skillPoint.setRatio(restore.getSkillPointRatio(index))
		// A fresh battle has no entry, so that returns 0 and everyone starts empty.
		// Raising it fills the gauge once, at the start, and never again - unlike
		// fastskill, which keeps refilling it.
		var full = devFlag("fullskill");
		if (full !== null) {
			var ratio = typeof full === "number" ? full : 1.0;
			hook("pinball.common.data.battle.restore.BattleContinuationData",
				"getSkillPointRatio", function (original) {
					return function (index) {
						// Never reduce a real continuation, only raise the opening value.
						var actual = original.call(this, index);
						return actual > ratio ? actual : ratio;
					};
				});
			console.warn("[WFMod] DEV AID active: opening skill gauge set to " + ratio +
				" (?wfdev=fullskill)");
		}

		var fast = devFlag("fastskill");
		if (fast !== null) {
			// The skill gauge fills from MemberAbilityTotalizer.getTotalSkillGaugeCharging(),
			// which is the sum of every "skill gauge charging up" ability a member has.
			// Adding to it is the same lever those passives pull, so no data changes.
			var bonus = typeof fast === "number" ? fast : 1000;
			hook("pinball.scene.battle.battle.ability.MemberAbilityTotalizerImpl",
				"getTotalSkillGaugeCharging", function (original) {
					return function () { return original.call(this) + bonus; };
				});
			console.warn("[WFMod] DEV AID active: skill gauge charging +" + bonus +
				" for every member, continuously (?wfdev=fastskill)");
		}
	}

	// The hooks WFMod installs at startup, in order.
	function applyHooks() {
		applied = [];
		failed = [];

		// AUTO unlock. BattleScene.get_autoPlayUnlocked() asks
		// globalLogic.isGameSystemUnlocked('auto_play'), but master
		// game_system_unlock is empty in this Trial build, so AUTO could never
		// unlock. This was a string patch until v0.3.2; it is the proof that a
		// whole-method replacement does not need one.
		hook("pinball.scene.battle.BattleScene", "get_autoPlayUnlocked", function () {
			return function () { return true; };
		});

		registerAssets();
		applyDevAids();

		if (applied.length) {
			console.info("[WFMod] " + applied.length + " runtime hooks: " + applied.join(", "));
		}
		if (failed.length) {
			console.error("[WFMod] " + failed.length + " runtime hooks FAILED: " + failed.join(", "));
		}
		return { applied: applied.slice(), failed: failed.slice() };
	}

	function classNames(filter) {
		var registry = internals();
		if (!registry || !registry.classes) return [];
		var names = Object.keys(registry.classes);
		return filter ? names.filter(function (n) { return n.indexOf(filter) >= 0; }) : names;
	}

	window.WFMod = window.WFMod || {};
	window.WFMod.runtime = {
		getClass: getClass,
		getEnum: getEnum,
		hook: hook,
		addAsset: addAsset,
		applyHooks: applyHooks,
		classNames: classNames,
		get hooks() { return { applied: applied.slice(), failed: failed.slice() }; }
	};
})();
