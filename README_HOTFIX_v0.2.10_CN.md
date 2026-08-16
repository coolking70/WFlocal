# v0.2.10：挑战模式 ClientError 8601（key=attention）修复

## 症状

v0.2.9 进入「挑战 / 自制关卡」后，加载走到场景切换阶段抛出：

```
[ClientError]:8601 指定されたキーは存在しません。
key=attention, assets/trial/production/master/.../game_system_unlock/game_system_unlock.orderedmap
```

调用栈：`changeSceneWithDetail → internalChangeScene → changeLogicState →
notifyTransitionStarting → isActive → isGameSystemUnlocked → get → getIndex`。

## 原因

这一次和 master 分片策略无关。

`assets/trial/production/master/game_system_unlock/game_system_unlock.orderedmap`
在体验版数据里是**空表**（解压后记录数为 0），任何 key 都查不到。

原版流程不会踩到，是因为逻辑层的包装函数：

```
isGameSystemUnlocked(kind) {
    if (logicStatus.isDuringTutorial()) return false;   // ← 体验版永远停在这里
    return getGameSystemUnlockRepository().isGameSystemUnlocked(...);
}
```

Web 体验版从不离开「教程进行中」状态，所以这张空表永远查不到。
而挑战模式套用了教程结束后的存档（`getPlayerSaveData(4)` + `forcesFullTutorial=false`），
`isDuringTutorial()` 变成 false，进入 TrialQuestSelect 的第一次场景切换就会去问
「attention（お知らせ）系统是否已解锁」，直接撞上空表并在场景切换过程中抛错。

后续那一长串 SipoError / 事件错误都是这一次抛错的连锁反应。

## 处理方式

在挑战模式的启动补丁里，给 `GameSystemUnlockRepository.isGameSystemUnlocked`
加一层保护：查不到记录时返回「未解锁」，而不是抛 ClientError。

「表里没有这条解锁配置」语义上就等于「该系统没有开放」，这和教程路径返回 false
是同一个答案，所以不会放行任何本来不该出现的 UI。

没有采用 `devConfig.allGameSystemAlwaysUnlocked = true`（本体自带的开关，同样能
绕过查表）：那会把所有系统都标成已解锁，反而会打开一批体验版没有数据的界面。

同时本版加了一个精简的 ClientError 报告器：每个不同的 `code:message` 只打印一行，
带调用栈。首个真实错误不会再被后面的连锁报错淹没。

## 测试

运行 `run_windows.bat` 或 `run_macos_linux.sh`，进入挑战模式。控制台应看到：

```
[WFMod] build=0.2.10 mode=challenge master=merged-trial global=consistent-merged-policy unlock=guarded
[WFMod] v0.2.10 runtime patch applied: consistent merged-master policy ...
[WFMod] v0.2.10 runtime patch applied: missing game_system_unlock rows resolve to locked ...
[WFMod] v0.2.10 ClientError reporter installed
```

进入关卡选择时可能出现一条 `[WFMod] game system treated as locked ... key=attention`，
这是预期内的，表示保护生效。

重点验证：
- 是否进入原生 3 个挑战关列表；
- 是否出现第 4 个 CUSTOM STAGE PoC；
- 原版三关与第 4 关是否可进入；
- AUTO 是否仍正常。

如果还有错误，现在只需要把 `[WFMod] ClientError ...` 那一行（含调用栈）发回即可。

## 已知遗留问题（本版未改）

教程模式仍然带着 v0.2.3 数据合并留下的隐患：合并把每张 full 表并进了对应的
`_iosbundled` 表，而三个分片（full / bundled / iosbundled）在原版里是**互不相交**的分区。
已实测确认 `character.orderedmap` 的 18 个 key 全部包含在
`character_iosbundled.orderedmap` 的 22 个 key 里。

挑战模式已由 v0.2.9 的策略规避（有 merged ios 就不加载 full），但教程模式没有打补丁
（`Tutorial mode is untouched`）。教程跑完后走全量 `Global(false)` 加载时，full 与
merged-ios 会同时进入同一张表，触发 ClientError 7051 主键重复。

修法是把同一套策略去掉 `mode === "challenge"` 条件，两个模式都用。因为会改动原版教程
的行为，本版没有动，等确认挑战模式跑通后再定。
