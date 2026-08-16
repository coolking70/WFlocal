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
		applyHooks: applyHooks,
		classNames: classNames,
		get hooks() { return { applied: applied.slice(), failed: failed.slice() }; }
	};
})();
