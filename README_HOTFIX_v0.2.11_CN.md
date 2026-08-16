# v0.2.11：进入关卡卡死（ClientError 7011 TIPS）修复

## 症状

v0.2.10 已经能进入原生关卡选择界面，但点任何一关都卡死，控制台报：

```
[ClientError]:7011 表示可能なTIPSが1つもありません。
```

调用栈起点是 `buttonClicked → listSelected → start → startBattle → changeSceneWithDetail`，
即点击关卡后切进战斗加载画面时抛出。

（同时出现的 `POST https://api.worldflipper.jp/.../reproduce/post net::ERR_CONNECTION_CLOSED`
是本体的崩溃上报在尝试联网，离线环境下必然失败，不是原因，忽略即可。）

## 原因

加载画面要挑一条 TIPS 显示，`LoadingTipsLogic.getTipsTableStats()`：

```
var table = this.isDuringTutorial
    ? getMasterTable(tutorial_tips).get_data()
    : getMasterTable(tips).get_data();
// 逐条按 require_single_quest 过滤
if (一条都没有) throw ClientError 7011;
```

体验版数据实测：

| 文件 | 记录数 |
| --- | --- |
| `tips/tips.orderedmap` | **0** |
| `tips/tutorial_tips.orderedmap` | 0 |
| `tips/tutorial_tips_iosbundled.orderedmap` | **4** |

全部 TIPS 只有 `tutorial_tips` 的 4 条，内容是：

```
(None),,,dynamic/loading_tips/tips039
(None),,,dynamic/loading_tips/tips040
(None),,,dynamic/loading_tips/tips042
(None),,,dynamic/loading_tips/tips041
```

正好对应 assets 里仅有的 4 张 `loading_tips` PNG，且首列 `require_single_quest`
都是 `(None)`，即无解锁条件。

这和 v0.2.10 的 8601 是同一类问题：**体验版只填了教程用的那份数据，非教程分支的表是空的**。
挑战模式脱离教程状态后走进非教程分支，读到空表直接抛错。

## 处理方式

在挑战模式启动补丁里给 `getTipsTableStats` 加回落：正常表一条记录都没有时，
改用 `tutorial_tips`。表非空时行为完全不变。

没有直接把 `isDuringTutorial` 强制为 true —— 那个字段还影响别的判断，
只改 TIPS 这一处取表逻辑，影响面最小。

## 测试

进入挑战模式，控制台应看到：

```
[WFMod] build=0.2.11 mode=challenge ... unlock=guarded tips=fallback
[WFMod] v0.2.11 runtime patch applied: empty master tips falls back to tutorial_tips instead of ClientError 7011
```

点击关卡进入战斗加载时会出现一条
`[WFMod] master tips is empty, falling back to tutorial_tips for the loading screen`，
这是预期内的，表示回落生效。

重点验证：
- 原版 3 关是否能进入战斗；
- 第 4 张 CUSTOM STAGE PoC 是否能进入；
- 战斗结算返回关卡选择是否正常；
- AUTO 是否仍正常。

## 校验方式

启动页的补丁代码用 node 跑过一遍（直接从 `game-index.html` 抽出同一段代码执行，
避免验证脚本和实际代码走样）：4 个锚点各自唯一匹配，打完补丁的 29MB bundle
`node --check` 通过。

## 已知遗留问题（未改）

教程模式仍带着 v0.2.3 数据合并的隐患，详见 `README_HOTFIX_v0.2.10_CN.md` 末节。
