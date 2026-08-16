# Battle Action DSL Capability Matrix

路线图 R2 的第一刀。回答的问题：**这个 Runtime 原生支持哪些技能行为。**

数据由 `python3 tools/analyze_dsl.py --write` 生成，机器可读版本在 `reverse/dsl.json`。
两个来源：

- **支持什么** — bundle 里的 `pinball.battle.action.dsl.ActionDslCommand` enum；
- **用到了什么** — 随 demo 发布的 62 个 `*.action.dsl.json`。

```
34 个命令引擎支持
22 个官方内容用到
12 个支持但没用过   ← 原创技能可以白拿
```

## DSL 结构

序列化成嵌套数组的 Haxe enum：

```json
["ActionDsl", 1, false, false,
  ["Block", [
    ["Command", ["SpawnFunnel", ["Funnel","avator_ghost_fox_avator_single"], 1, ["FunnelGroup",5]]]
  ]]
]
```

三种表达式（`ActionDslExpression`）：`Block` / `Event` / `Command`。

事件只有三种（`ActionDslEvent`）：

| 事件 | 含义 |
| --- | --- |
| `Wait` | 延迟后执行 |
| `Repeat` | 按间隔重复 |
| `CollisionOfBallAndEnemy` | 球与敌人碰撞时触发 |

**控制流就这么多**——没有条件分支、没有循环变量、没有算术表达式。技能是"时间轴上的命令序列"，
不是脚本语言。这条边界对设计原创技能很重要。

## 已用命令（22）

| 命令 | 次数 | 文件数 |
| --- | ---: | ---: |
| `ShowEffect` | 87 | 41 |
| `CreateNormalAttack` | 84 | 45 |
| `CreateHitArea` | 75 | 39 |
| `MoveHitArea` | 51 | 18 |
| `ShakeCamera` | 37 | 21 |
| `CreateCondition` | 28 | 14 |
| `SpawnFunnel` | 12 | 6 |
| `CreateTargetAttack` | 12 | 1 |
| `FindAllSubjects` | 11 | 10 |
| `StopBall` | 8 | 8 |
| `CreateShockWaveAttack` | 8 | 5 |
| `CreateRatioHeal` | 7 | 5 |
| `FindNearSubjects` | 5 | 5 |
| `MoveBall` | 4 | 4 |
| `CreateReferencePoint` | 4 | 4 |
| `HideEffect` | 3 | 3 |
| `AddFeverPoint` | 3 | 3 |
| 其余 | ≤3 | |

典型技能的骨架是：`CreateHitArea`（判定区，内嵌 `ShowEffect` + `MoveHitArea`）→ 命中时
`CreateNormalAttack` + `ShakeCamera`。

## 支持但从未使用（12）——原创技能的免费能力

```
CreateShield              CreateGravitationalField
CreateTornado             CreateWindAttack
CreateFixedAttack         CreateRatioAttack
CreateNormalHeal          DeleteCondition
RemoveEvent               SubtractFeverPoint
SubtractSkillPoint        Trace
```

这一栏直接影响路线图 R7 的范围。R7 列的"需要新增 primitive"里，有几项**已经原生存在**：

| R7 设想的新能力 | 实际情况 |
| --- | --- |
| orbiting projectile | `CreateShield` + `ShieldMovementKind`（Fixed / Smart / RotateClockwise / RotateAnticlockwise） |
| persistent field | `CreateGravitationalField` |
| clone ball | `CreateBombMultiball` / `CreateSummonsMultiball`（且已被官方使用） |
| custom status stack | `AdditionalConditionKind` 17 种 + `DeletionalConditionKind` 18 种 |

**建议 R7 相应缩小**：真正缺的是 time stop（现只有 `StopBall`，作用于球）、destructible object、
new flipper behavior、special terrain object 这类。

## 参数值空间

命中效果 `AttackHitEffect`（15）：`None, Fine, Coarse, Dark, Explosion, Fire, ...`

增益/状态 `AdditionalConditionKind`（17）：
`ACAttackPoint, ACSkillDamage, ACToleranceOfElement, ACDamageOfElement, ACSpecialEfficacy, ACRegeneration, ...`

移除 `DeletionalConditionKind`（18）：`DCAll, DCAttackPoint, ...`

其他关键值空间：

| enum | 数量 | 值 |
| --- | ---: | --- |
| `Shape` | 4 | Circle, Rectangle, Donut, Arc |
| `Formation` | 7 | Single, Line, File, Circle, AShaped, WShaped, … |
| `Easing` | 17 | Linear, QuadIn/Out, CubicIn/Out, … |
| `CoordSys` | 4 | AB, CD, EF, GH |
| `LayerZDepth` | 4 | ForesideOfCharacter, BacksideOfCharacter, SuperForesideOfCharacter, NonPixelArt |
| `ShieldMovementKind` | 4 | Fixed, Smart, RotateClockwise, RotateAnticlockwise |
| `EndingSpeedKind` | 4 | Stop, KeepGoing, RestoreToSpeedBefore{Command,Action}Execution |
| `IfTargetNotFound` | 2 | DoNothing, CreateImaginaryTarget |

完整清单见 `reverse/dsl.json` 的 `valueSpaces`。

## 这一刀没解决的

**参数语义还不知道。** 我们有命令名、有实际用过的参数形状（`reverse/dsl.json` 的
`signatures`），但不知道某个 `int` 到底是帧数、半径还是 ID。例如：

```
CreateHitArea(str, int, EF, int, int, float, bool, bool, Circle(int), Center, Center,
              Single, SpecifyHitAreaLifetimeDirectly(int), CalculatedUsingMaxNumOfHits(int),
              None, bool, bool, int, Block(...), int, int, Block(...))
```

22 个参数，只有带标签的那些能自解释。

要补上这一层，需要读 bundle 里的 DSL 解析器——`pinball.battle.action.dsl.*` 下的类，
入口可以用：

```bash
python3 tools/analyze_bundle.py find ActionDslCommand
python3 tools/analyze_bundle.py find HitArea
```

这是 R2 的第二刀。第三刀才是把 `action_skill` / `leader_ability` / `ability` 三张 master
和 DSL 接起来，回答"数据里怎么配"。
