# 自制关卡：房间从哪来

回答："怎么让一个关卡先有小怪房间、打完再进 boss 房间。"实测跑通。

起因是判定几何**天生不可见**（`ActionHitArea` 建的是物理形状，不进显示列表），
只有一个 boss 时任何形状都罩得住它，所以技能范围在屏幕上留不下痕迹。
要观察范围，得有**分散的多个敌人**。

## 一个关卡由四处数据拼成

```
main_quest 行  ──► zone key（例：main_2_9_5）
                     │
      ┌──────────────┼───────────────────────┐
      ▼              ▼                       ▼
 field_data      zone.orderedmap        terrain .json
 (field, terrain,  key/0, key/1 …        layers[0], layers[1] …
  zone)            每波一行                每波一个房间
      │
      ▼
 field.orderedmap
 背景、门、传送舱等场地对象
```

**波次 = zone 表的嵌套键 = terrain 的图层**，三者按序号对应。官方样板：

```
tutorial_5 terrain  layer '0'  BOUNDS y=366..686  SPAWN3/SPAWN6 ×7, GATE, TRANSIT
                    layer '1'  BOUNDS y=16..336   CUSTOM_POSITION p0..p3
tutorial_5 zone     wave 0     objective ZakoKill(10) + zako01..06
                    wave 1     objective BossClear   + boss1 maou_tutorial
```

`ZoneManagerImpl.totalZones` 就是 `zones.length`，而 zone 列表由
`ZoneMapTools.createOrderedMapFromValues` 遍历 `zone[key].keys()` 建出。
**想知道实际跑的是哪张表，trace 这个静态函数的 `arg0` 即可。**

## 三个必须知道的坑

**一、菜单里的第几关 ≠ 哪个 zone。** 数据里没有任何东西提示这件事：

```
quest 111/1/1  VS ガーディアンゴーレム   main_2_9_5
quest 111/1/2  VS クラーケン            main_3_6_2_trial
quest 111/1/3  VS 妖狐                 main_6_6_2
```

我按"关卡 1 = 第一个查到的 zone"改了三轮，改的全是没人在玩的关卡——
磁盘上全对，游戏里全不存在。**先 trace 出 zone key，再动手。**

**二、两个资源根是逐文件互斥的。**

```
battle/terrain/main_quest/chapter_02、chapter_06   只在 assets/production
battle/terrain/main_quest/chapter_03              只在 assets/trial/production
battle/terrain/tutorial/*                         只在 assets/production
```

分叉件必须和它替换的文件在**同一个根**，否则游戏照旧加载原版——
**没有 8100、控制台没有一行、就是旧内容**。`verify_patches.mjs` 现在会拦。

**三、场地只自带它本来那关用得到的东西。** `sand_ruins` 原本是单房间，
所以**没有 gate、没有 transit_pod**——恰恰是负责换房间的那两样。
从有的场地借（`evil_tower_top`）即可，改 `field` 表的列，不复制文件。

小怪也一样：`general_zako` 里只有两条指向缺失素材的 skill_preview 条目，
真正可用的四个在 **`general_zako_iosbundled`**（与 `tips` /
`tutorial_tips_iosbundled` 同一个分裂模式），素材齐全：

```
curse_eye_tutorial  enemy_demonspider_tutorial
enemy_evilgiant_tutorial  enemy_eviltower_tutorial
```

## 用法：它是第 4 个关卡槽位，不动关卡 1~3

```bash
python3 tools/dummy_stage.py --build --count 10       # 装到「WFMOD 練習場」
python3 tools/dummy_stage.py --revert                 # 四张表 + 分叉件一起退回
```

训练场占用 demo 自带的备用关卡 `111/1/4`（原名 CUSTOM STAGE PoC），
用**自己的 zone key `wfmod_training`**，boss 房间和场地从 `main_2_9_5` 复制。
关卡 1~3 保持原样——它们是验证别的东西时的基准，不能被测试装置污染。

接线点是 main_quest 行的第 **74** 列 `battle_field_data_id`：它指向 `field_data`
的键，`field_data` 再给出 zone 键。main_quest 行有 85 列而**没有任何 `*Values` 类是这个宽度**，
实际布局是 `BossBattleQuestValues` 整体偏移 1 列——这一列是这么认出来的，不是数出来的。

`main_quest` 是**三层嵌套**表（`111` / `1` / `4`），按单层去查会找不到。

## 小怪数量的上限

| | 上限 | 由什么决定 |
| --- | --- | --- |
| 同屏 | **10** | `ZoneValues` 只解析 `zako01..zako10`（列 2..21） |
| 总数 | 不限 | 每个槽位是一个 `ZakoEmitter`，按 `interval` 帧反复生成；`(None)` 只生成一次 |
| 波次 | 不限 | zone 表的嵌套键 0/1/2… |

`--count` 最多 10，再多就写进 boss 列了，工具会拒绝。要更高密度用 `interval`。

小怪房间是 `tutorial_5` 那间**整间照搬**——墙、边界、棺材、门、传送舱，
每个对象都出自游戏真正在跑的房间。手搭的话是对一堆未确认语义的连续猜测。

原版 terrain 一字未动：分叉件放在 `battle/terrain/wfmod/`（自动选根）并在运行时注册；
`zone` / `field_data` / `field` 三张 master 表的原件存在 `WFTest/` 之外，`--revert` 一起退回。

已知取舍：背景是沙漠遗迹、房间零件是邪塔的，**美术串味**。这是测试台。

## 方法论

这条线连着四轮没跑通，四轮各有各的原因，但只有最后一个是真正的阻塞：

| 轮次 | 现象 | 真实原因 |
| --- | --- | --- |
| 一 | 小怪没出现，控制台干净 | terrain 没有 SPAWN 对象 |
| 二 | 直接进 boss 房 | 分叉件放错资源根 |
| 三 | 直接进 boss 房 | **改错了关卡** |
| 四 | 8100 gate | 场地缺 gate / transit_pod |

第二轮修掉的是真实缺陷，但**它不是当时那个现象的原因**——第三轮证明了这一点。
把"修好了一个真实缺陷"当成"找到了原因"，是这段过程里最花时间的一次误判。
现象没有随修复而改变时，说明原因还在别处，不要因为修的东西确实有问题就停止追查。

## 坐标系与可用区域（实测）

terrain 单位 × **6** = 世界坐标。用 `?wfdev=trace` 读判定区位置逐位验证过：

```
房间 BOUNDS  x 46..226  y 366..686  →  中心 (136, 526)
136 × 6 = 816      526 × 6 = 3156      ← trace 报的判定区坐标
```

**mob 能站的地方不是整个房间。** 官方那间房的出生点只占：

```
纵向  房间高度的 0.38 ~ 0.50
横向  房间宽度的 0.27 ~ 0.67
```

房间下半部是弹板和落球口，**放在那里的出生点不会产生小怪**——把网格铺满整个 BOUNDS
时，最下面一行就是这么消失的。`dummy_stage.py` 现在把网格限制在
`X_BAND = (0.18, 0.82)`、`Y_BAND = (0.36, 0.64)`，比官方略宽以便罩住技能范围，
但不进入下半部。

## DSL 的负数 id 是绑定好的固定点

`ActionEvaluator` 建全局环境时绑的：

```js
env.bind(-1,  specialPointZoneBoundsCC);   // 房间 BOUNDS 中心
env.bind(-2,  specialPointZoneBoundsLT);   // 左上角
env.bind(-17, getMyself());                // 角色（HideCharacter -17 即此）
```

把 `CreateHitArea.symbol` 从 `-18`（弹珠）改成 `-1`，判定区就钉在场地中心，
与弹珠位置无关——实测坐标恒为 `(816, 3156)`，一帧都不漂。

这对测试很关键：弹珠台没法精确瞄准，而钉住的判定区让"范围"变成可重复的读数。
它同时也是个说得通的设计：定点范围技。

安全前提：该判定区的 `coordSys` 是 `AB`，`ActionHitArea.calcDir` 在 `AB` 下返回常量
`-π/2`，**不会向目标索取朝向**，所以一个没有朝向的"点"不会引发 INTERNAL ERROR。
