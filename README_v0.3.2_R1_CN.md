# v0.3.2：Reverse Atlas 与 Runtime Bridge（路线图 R1）

对应 `WFlocal-Development-Roadmap-v1.0` 的 R1 阶段。目标不是反编译，而是让 29MB 的黑盒
变成**可检索、可 hook** 的引擎。

## 1. Reverse Atlas

```bash
python3 tools/analyze_bundle.py index    # 约 2 秒
python3 tools/analyze_bundle.py find <query>
python3 tools/analyze_bundle.py show <offset>
```

产出 `reverse/`（全部由工具生成，勿手改）：

```
classes  3282   （32569 个 prototype 方法）
enums    729
errors   285    ClientError 码 → 消息 + 全部抛出点
scenes   878
masters  431
remotes  51
assets   1016
```

关键发现：`$hxClasses` / `$hxEnums` 这两个注册表在 bundle 里是**局部变量**（`_0x2cc772`
写入 3342 次、`_0x7f6db2` 写入 1159 次），键是真实类名。整个索引就是从这里恢复的，
不需要反编译。

### 两处偏离路线图

- **不做 `callgraph.json`**（§5.2）。混淆 bundle 上的调用图节点全是 `_0x` 局部名，
  成本高、可读性接近零。等确有需求再做。
- **错误码索引存表达式，不只存字面量。** 8601（117 个抛出点）和 2340 的消息是运行时
  拼出来的，只认字面量的话这两个码根本不会进索引——而它们正是本项目排障时追得最多的。

## 2. Runtime Bridge

新补丁 `expose-internals`（两个模式）在注册表声明处插一句：

```js
window.WF_INTERNALS = { classes: _0x2cc772, enums: _0x7f6db2 };
```

一行，换来 3282 个按真名索引的类和 729 个 enum。

> 路线图 §5.4 建议"暴露 3～5 个已确认内部对象"。实测发现整个注册表就是现成的，
> 所以直接暴露注册表，不做人工挑选。

`WFTest/wfmod/runtime.js` 提供包装层：

```js
WFMod.runtime.getClass(name)
WFMod.runtime.getEnum(name)
WFMod.runtime.hook(className, methodName, factory)   // factory 收到原方法，可委托
WFMod.runtime.classNames(filter)
```

### 能力边界（重要）

| 能做 | 不能做 |
| --- | --- |
| 替换/包装 prototype 方法 | 拦截 `new Foo(...)`——bundle 内部走的是局部变量绑定，改注册表无效 |
| 读静态成员、读 enum | 拿到运行中的实例——除非有东西把它交出来 |

所以路线图 §5.6 那句"逐步减少字符串替换型 patch"要打个折：**整方法替换的可以转，
注入语句中间的转不了**。当前 7 个字符串补丁里，`unlock-guard` 和 `tips-fallback`
属于可转的（都是整方法），`challenge-boot` / `full-master-boot` / `report-off` /
`clienterror-reporter` 属于不可转的。

## 3. PoC：auto-unlock 从字符串补丁变成运行时 hook

```js
// wfmod/runtime.js
hook("pinball.scene.battle.BattleScene", "get_autoPlayUnlocked", function () {
    return function () { return true; };
});
```

目标类是查索引确定的，不是猜的——`get_autoPlayUnlocked` 有 4 个类声明
（BattleScene / BattlePauseMenu / IBattleScene / SkillPreviewBattle），原字符串补丁命中的
是 `BattleScene`，hook 打的是同一个。

补丁表从 8 条变成 8 条：去掉 `auto-unlock`，加上 `expose-internals`。

这个 hook 有**真实单元测试**：`verify_patches.mjs` 构造一个形状相同的假注册表，
跑真实的 `runtime.js`，断言 prototype 上的方法确实被替换、且返回 true。

## 4. 一条命令的静态校验

```bash
./tools/verify_all.sh
```

串起三项：树 vs 原档、补丁表 + runtime hook、orderedmap 无损 round-trip。

**它不覆盖需要真正跑起来的部分**——教程能否启动、挑战模式 4 关能否进、AUTO 是否工作、
战斗能否结算、控制台有无 ClientError，这些仍然只能人工验。脚本结尾会明说这一点，
不把它包装成"自动化验收"。

## 5. ID 命名决定

**自制内容走独立 chapter / stage node 命名空间**（路线图 §17.3）。

需要记下的后果：现在的第 4 关 `111001004` 是**借用官方 ID 空间的过渡态**——它被故意
放进官方 chapter 111 / stage node 111001，因为这正是 TrialQuestSelect 原生枚举到它的原因。
按独立命名的决定，R6 时它要迁移到自建 chapter + stage node，并**另做入口**
（原生 TrialQuestSelect 只枚举 `devConfig.trialStageNodeId` 指向的那一个 stage node）。

这条不要被当成既定做法沿用。

## 6. 回归

静态：`./tools/verify_all.sh` 全过，`world-flipper.js` SHA 不变。

浏览器：需人工确认教程 / 挑战 / AUTO / 4 关 / 无 ClientError。

控制台现在会多一行：

```
[WFMod] 1 runtime hooks: pinball.scene.battle.BattleScene.get_autoPlayUnlocked
```

## 7. 给 R2 的入口

Character / Skill Capability Census 要从这些类查起：

```bash
python3 tools/analyze_bundle.py find BattleCharacter
python3 tools/analyze_bundle.py find ActionSkill
python3 tools/analyze_bundle.py find PowerFlip
python3 tools/analyze_bundle.py find HitArea
python3 tools/analyze_bundle.py find LeaderAbility
```

`*.action.dsl.json` 共 62 个，是 R2 的 DSL schema 主要素材。
