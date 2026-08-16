# v0.3.0：建立基线，补丁全部外置

这一版没有新功能，只做一件事：让"这棵树相对官方原档改了什么"变成一个能用一条命令回答的问题。

## 为什么要做

交接文档 §44 / §59 要求保留一份未修改的原档并记录 SHA，一直没做。到 v0.2.12 时的实际状态是：

- `world-flipper.js` 的 SHA 与交接文档记录的原档**不一致**——有 3 处改动被直接烤进了 29MB bundle；
- 44 张 master 被就地 merge；
- 初始提交里存的就已经是改过的版本，**git 里没有任何一份原档**。

也就是说，7 个运行时补丁全锚定在一个无法重新推导的 bundle 上。

## 做了什么

### 1. 原档核对

`~/Downloads/WFDemo.zip`：3453 entries，`zipfile.testzip()` 无 CRC 错误，三个关键文件 SHA 与交接文档记录**逐字一致**：

```
world-flipper.js  db5f3806599510ed3b6783ce5c4ccdac764eccbf4d297299af12eb902a814315
game-index.html   1b22dd159bc9a5202e93dfff39ffdc670089cf23325673e4bf67a5af486a7988
pako.min.js       7c86ec919f12342cd0ede0e0d198312b03d753457c7cd80e9dabe3e21e48ae8d
```

### 2. 切出被烤进 bundle 的 3 处改动

| 位置 | 改动 | 出处 |
| --- | --- | --- |
| `TitleScene.gotoTutorial()` | +1289 字符：读取 player 4 存档并直接跳 TrialQuestSelect | 挑战模式启动 |
| `BattleScene.get_autoPlayUnlocked()` | 200 字符 → `return!0x0` | 交接文档 §25 AUTO |
| `BattleViewInputSettings.get_autoplayButtonMode()` | `return 0x2`(Hidden) → `0x1`(OFF) | 同上 |

提取的正确性是**逐字节证明**的：原档 + 这 3 个补丁重新生成的文件，SHA 与改动前的
`world-flipper.js` 完全相同（`b3ae568a…b973a4a71`）。

顺带一个观察：`get_autoPlayUnlocked` 那个补丁把 `isGameSystemUnlocked('auto_play')`
整个绕过去了——它其实提前躲掉了我们后来在 8601 上踩的同一个空表坑。同一个 bug 类，
之前用"绕过"解决了 auto_play 一例，v0.2.10 用"缺行即未解锁"解决了通例。

### 3. `world-flipper.js` 还原为原档

现在磁盘上的 bundle SHA = `db5f3806…a814315`，与官方原档一致。

### 4. 补丁表

全部 8 个改动改写成 `game-index.html` 里的声明式补丁表：

```js
{ id, modes: ["tutorial","challenge"], find, replace, note }
```

规则：

- `find` 在原档中必须**恰好出现一次**，否则 bootstrap 抛错拒绝运行，不会拿一个没验证过的 bundle 去跑；
- `modes` 决定该补丁在哪个启动模式生效；
- 每条都带 `note` 说明为什么需要它。

现在两个模式都走 fetch → patch → blob。教程模式套用 3 条（AUTO 两条 + ClientError 报告器），
挑战模式套用全部 8 条。

| 补丁 | 模式 | 作用 |
| --- | --- | --- |
| `auto-unlock` | 两者 | AUTO 按钮解锁 |
| `auto-button-mode` | 两者 | AUTO 按钮由 Hidden 改为 OFF |
| `challenge-boot` | 挑战 | player 4 + 直接进 TrialQuestSelect |
| `master-policy` | 挑战 | 有 merged iosbundled 就不加载 full（7051） |
| `unlock-guard` | 挑战 | game_system_unlock 缺行即未解锁（8601） |
| `tips-fallback` | 挑战 | tips 空表回落 tutorial_tips（7011） |
| `report-off` | 挑战 | 关闭服务器上报 |
| `clienterror-reporter` | 两者 | 每个不同 ClientError 打一行 |

### 5. 两个校验脚本

```bash
python3 tools/verify_tree.py --list   # 树 vs 原档：哪些文件被改了，各自为什么
node tools/verify_patches.mjs         # 补丁表 vs bundle：锚点唯一性 + 打完能否解析
```

`verify_patches.mjs` 直接从 `game-index.html` 里读补丁定义执行，不另存一份，
所以校验脚本不会和实际代码走样。有问题时退出码非 0。

当前状态：

```
unchanged 2736 / modified 46 / added 1 / missing 0
world-flipper.js pristine: yes
0 处 UNEXPECTED
8 个补丁锚点全唯一，两个模式打完都能解析
```

46 处改动 = 44 张 merged master + `main_quest`（第 4 关）+ `game-index.html`。

## 行为等价性

重构没有改变游戏行为，这一点是验证过的，不是推断的：

**挑战模式**：新架构产出的 bundle 与 v0.2.12 产出的相比，只有**一处**差异：

```
旧: var _wfChallenge = (window.WF_DEMO_BOOT_MODE === "challenge");
    var _0x550674 = _wfChallenge ? (_wfHasIos ? A : B) : _0x3d4eef ? A : B
新: var _0x550674 = _wfHasIos ? A : B
```

挑战模式下 `_wfChallenge` 恒为真，旧式必然归约成新式；而新补丁只在挑战模式套用，
那个运行时判断本就冗余。

**教程模式**：相比之前多了 ClientError 报告器（仅控制台输出），少了那段挑战启动代码
（它在教程模式下本来就被 mode 判断挡住，是死代码）。字数对得上：
`+211 - 1289 = -1078`，与实测差值一致。

## 遗留

教程模式的 7051 隐患仍未处理：`master-policy` 目前只在挑战模式生效，教程打完走全量
`Global(false)` 时，full 与 merged-ios 仍会同时进同一张表。

这一项留给 M2——那一步会尝试彻底不要 merge（挑战模式启动即走全量 master），
如果可行，44 张 master 全部还原原档，这个隐患自然消失。
