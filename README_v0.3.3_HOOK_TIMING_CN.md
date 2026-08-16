# v0.3.3：修复 v0.3.2 的 hook 时序回归

v0.3.2 引入了两个回归，根因是同一个。

## 症状

- 教程模式点击后卡死，控制台 `Uncaught _0x34e26d`（ClientError）；
- 挑战模式 AUTO 按钮变回锁定，提示"体验版无法使用"；
- 控制台**没有** `[WFMod] N runtime hooks:` 那一行。

## 根因：bundle 不是加载即执行

`world-flipper.js` 的结构是：

```js
var _0x11c446 = function (a, b) { /* 整个 Haxe bundle */ };
...
lime['$scripts']['world-flipper'] = _0x11c446;
lime['embed'] = function (...) { /* 这里才调用工厂 */ };
```

也就是说，bundle 把自己**注册成 lime 的模块工厂**，只有 `lime.embed()` 调用它时才真正执行。
类注册表要到那时才被填充，`window.WF_INTERNALS` 在 embed 之前根本不存在。

v0.3.2 把 `applyHooks()` 放在了 `lime.embed()` **之前**，于是：

```
applyHooks()  →  WF_INTERNALS undefined  →  getClass 返回 null  →  hook 失败
```

AUTO 解锁失效直接可解释。教程模式的崩溃是连锁反应：v0.3.1 之前 AUTO 解锁是**字符串补丁**，
它把 `get_autoPlayUnlocked` 整个换掉了，从不碰空表；改成 hook 之后 hook 又没生效，
于是调用退回原实现，去查那张 0 条记录的 `game_system_unlock` —— 而 `unlock-guard`
补丁只在挑战模式生效，教程模式没有保护，直接抛 8601。

## 修复

`applyHooks()` 移到 `lime.embed()` 之后。启动流程先进公司 logo，被 hook 的类离实例化还很远，
时机是安全的。

## 测试方法的失误，以及改法

v0.3.2 的验证里，我给 hook 写的是"形状相同的**假注册表**"单元测试：

```js
class FakeBattleScene { get_autoPlayUnlocked() { return false; } }
```

它测通了 hook 机制，却**恰好绕开了真正的问题**——`WF_INTERNALS` 什么时候存在。
假注册表永远是现成的，所以测试永远通过，而真实环境永远失败。这是这次回归能溜进去的直接原因。

现在换成真集成测试，`node tools/verify_patches.mjs` 会：

1. 对**真 bundle** 套用补丁；
2. 在 node 沙箱里执行它；
3. 取出 `lime.$scripts["world-flipper"]` 并**真的调用工厂**（工厂最后会在 stub canvas 上抛错，
   但那时所有类已注册完毕，不影响断言）；
4. 断言 `window.WF_INTERNALS` 存在（实测 3286 类 / 729 enum）；
5. 跑真实的 `wfmod/runtime.js`，hook **真 prototype**；
6. 调用被替换的方法，断言返回 `true`。

另外加了一条针对性检查——正是这次出错的那一点：

```
ok   applyHooks() runs after lime.embed()
```

这条检查用"把 bug 放回去"验证过：把顺序改回 v0.3.2 的写法，它会报

```
FAIL launcher: applyHooks() runs before lime.embed(); WF_INTERNALS will not exist yet
```

## 顺带修正的文档

- `reverse/README.md`：静态索引 3282 个类，运行时注册表实测 3286 个。差的 4 个是静态正则
  没匹配到的注册形式；运行时以 `WF_INTERNALS.classes` 为准。
- `README_v0.3.2_R1_CN.md`：原文把假注册表测试当作优点描述，已加更正说明。

## 需要回归

`./tools/verify_all.sh` 全过。浏览器侧仍需人工确认：

- 教程模式能进、点击不崩；
- 挑战模式 4 关能进；
- **AUTO 按钮出现且可开关**（这是本版的重点）；
- 控制台出现 `[WFMod] 1 runtime hooks: pinball.scene.battle.BattleScene.get_autoPlayUnlocked`。
