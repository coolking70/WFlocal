# v0.3.1：取消 master 合并

实机验证通过。挑战模式 4 关正常，教程模式正常。

> 本版之后，`MASTER_MERGE_REPORT.txt` 与 `README_HOTFIX_v0.2.3_CN.md` 描述的合并方案**已作废**，
> 保留仅作历史记录。

## 背景

v0.2.3 为了让启动阶段能读到 Trial 完整数据，把 71 对 `foo.orderedmap` / `foo_iosbundled.orderedmap`
做了递归 union merge，实际改写了 44 张表。

这个方案能用，但破坏了官方数据的一个前提：**full / bundled / iosbundled 三个切片是互不相交的分区**。
merge 之后 full ⊂ merged-ios，于是任何同时加载两者的代码路径都会撞上
ClientError 7051（主键重复）。v0.2.9 的对策是"有 merged ios 就跳过 full"，能绕开，
但代价是 44 个二进制文件永久偏离原档，而且教程模式没打这个补丁，隐患仍在。

交接文档 §34 早就给过判断：不要把这个方案作为长期架构。

## 这一版的做法

不再改数据，改加载策略。

`GlobalAssetPathCollectionBuilder` 的第二个参数就是"启动数据集"开关：

```
true  -> new MasterGroupAssetPath(path, [], clazz)   // 空 filePaths，随后只推 bundled + iosbundled
false -> createFromMasterAssetPath(path)             // filePaths 含 full，随后再推 bundled + iosbundled
```

即 `true` = 教程切片，`false` = 完整数据集。

挑战模式本来就从教程结束后的存档起步，需要的正是完整 Trial 数据集——player 4、
18 个挑战角色、chapter 111 全都只在 full 切片里。所以补丁改成无条件走 full 分支：

```js
// 补丁 full-master-boot（仅挑战模式）
var _0x550674 = _0x4738f7['createFromMasterAssetPath'](_0x1b0e4b);
```

**这正是教程结束后游戏自己做的事**，我们只是把它提前到启动。三切片互斥，不会重复主键。

44 张 master 全部还原原档。

## 结果

```
unchanged 2780 / modified 2 / added 1 / missing 0
world-flipper.js pristine: yes
```

整棵树相对官方原档只剩三处改动，全部是我们自己的东西：

| 文件 | 说明 |
| --- | --- |
| `WFTest/game-index.html` | 补丁表 |
| `WFTest/index.html`（新增） | 启动模式选择页 |
| `master/quest/main_quest.orderedmap` | 第 4 关 `111001004` |

连带好处：

- 教程模式的 7051 隐患消失了——不是绕开，是前提恢复了，两个模式都不再可能撞；
- 交接文档 §45 那条 oracle 路线（打完教程观察官方 transition）重新可用；
- 自制关卡从此是在干净原档上做加法。

## 保留的两个补丁

`unlock-guard`（8601）和 `tips-fallback`（7011）**没有**因为取消 merge 而失效：
`game_system_unlock` 和 `tips` 在 full 切片里同样是 0 条记录。这两个是体验版数据本身
就没填的表，与合并无关。

## 当前补丁表

| 补丁 | 模式 | 作用 |
| --- | --- | --- |
| `auto-unlock` | 两者 | AUTO 按钮解锁 |
| `auto-button-mode` | 两者 | AUTO 按钮由 Hidden 改为 OFF |
| `challenge-boot` | 挑战 | player 4 + 直接进 TrialQuestSelect |
| `full-master-boot` | 挑战 | 启动即加载完整 Trial 数据集 |
| `unlock-guard` | 挑战 | game_system_unlock 缺行即未解锁 |
| `tips-fallback` | 挑战 | tips 空表回落 tutorial_tips |
| `report-off` | 挑战 | 关闭服务器上报 |
| `clienterror-reporter` | 两者 | 每个不同 ClientError 打一行 |

## 校验

```bash
python3 tools/verify_tree.py --list   # 树 vs 原档
node tools/verify_patches.mjs         # 锚点唯一性 + 打完能否解析
```
