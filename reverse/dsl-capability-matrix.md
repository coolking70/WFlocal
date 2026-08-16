# Battle Action DSL Capability Matrix

路线图 R2 的产出。回答的问题：**这个 Runtime 原生支持哪些技能行为、每个命令怎么配参数。**

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

## 支持但从未使用（12）

```
CreateShield(radius, u, v, lifetime, movementKind)
CreateGravitationalField(pointName, gravity, frame, width, height, u, v, hAlign, vAlign, canceledByStunOrWince)
CreateTornado(pointName, u, v, speed, frame, interval, action, canceledByStunOrWince)
CreateWindAttack(kind, speed, frame)
CreateFixedAttack(id, damage, hitEffect)
CreateRatioAttack(id, kind, sLvRateOfHealthPoint)
CreateNormalHeal(id, sLvBasicCure, specialEfficacies, sLvMultiplierOfSpecialEfficacy, hitEffect)
DeleteCondition(id, condition, limit)
RemoveEvent(name)
SubtractFeverPoint(value)
SubtractSkillPoint(target, value)
Trace(message)
```

### 其中 4 个用不了：资源不在这个包里

> **更正。** 本文最初把这 12 个称为"原创技能可以白拿的免费能力"。实机测试推翻了其中一部分。

把 `CreateShield` 加进一个技能后，进关卡直接在读取阶段崩：

```
ClientError 8100: 素材 battle/boss/common/boss_shield/boss_shield.timeline.json が見つかりませんでした
```

**命令本身是活的**——DSL 解析通过、引擎认得它、走到了加载它的视觉资源那一步。挡住的是资源。

bundle 里有一张按命令序号写死的资源依赖表（`addAnimationLayout`），挖出来是：

| 序号 | 命令 | 依赖资源 | 包内 |
| ---: | --- | --- | --- |
| 28 | `CreateWindAttack` | `battle/boss/common/boss_wind/boss_wind` | **缺** |
| 29 | `CreateGravitationalField` | `battle/boss/common/boss_gravity_field/boss_gravity_field` | **缺** |
| 30 | `CreateTornado` | `battle/boss/common/boss_tornado/boss_tornado` | **缺** |
| 31 | `CreateTargetAttack` | `battle/boss/common/boss_target_sight/boss_target_sight` | 有（官方在用） |
| 33 | `CreateShield` | `battle/boss/common/boss_shield/boss_shield` | **缺** |

所以 12 个里有 **4 个被缺失资源挡住**：`CreateShield` / `CreateGravitationalField` /
`CreateTornado` / `CreateWindAttack`。要用它们，必须自己补出对应的 animation layout
（timeline + parts + atlas + png），而新资源路径还需要改 bundle 里的 asset manifest。

剩下 8 个（`CreateFixedAttack` / `CreateRatioAttack` / `CreateNormalHeal` /
`DeleteCondition` / `RemoveEvent` / `SubtractFeverPoint` / `SubtractSkillPoint` / `Trace`）
**没有 boss/common 依赖**。但注意：它们是否牵连别的资源（例如 hit effect）**尚未逐一核查**，
不要再当成"确定可用"。

### 两条通用教训

1. **资源依赖在关卡读取阶段就解析**，不是放技能时才解析。一条坏 DSL 会让整个关卡进不去，
   而不只是技能失效。
2. **能力 = 命令 + 资源。** 只看 enum 会高估可用范围。判断一个命令能不能用，必须同时查
   它在依赖表里声明了什么、以及那个资源在不在包里。

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

## 参数语义（第二刀）

**不需要读解析器。** Haxe 把每个 enum 构造子的参数名记在构造子函数的 `__params__` 上，
所以参数语义直接在 bundle 里。取法是把 bundle 跑起来读注册表：

```bash
node tools/dump_runtime_enums.mjs --write   # 写 reverse/enum_params.json
python3 tools/analyze_dsl.py                # 合并进签名输出
```

覆盖全部 729 个 enum、3784 个构造子（其中 2303 个带参数），不止 DSL。

于是之前那条 22 个 `int` 的签名现在是：

```
CreateHitArea(id, symbol, coordSys, u, v, w, trackingPosition, trackingDirection,
              shape, hAlign, vAlign, formation, lifetime, minHitInterval, maxNumOfHits,
              eliminatedOnHit, cracksWeakPoint, param11, exprs11, param21, param22, exprs21)
```

`analyze_dsl.py` 会把声明的参数名和实际观测到的取值形状配对输出：

```
seen x14: id: str, symbol: int, coordSys: EF, u: int, v: int, w: float,
          trackingPosition: bool, trackingDirection: bool, shape: Circle(int),
          hAlign: Center, vAlign: Center, formation: Single,
          lifetime: SpecifyHitAreaLifetimeDirectly(int),
          minHitInterval: CalculatedUsingMaxNumOfHits(int), ...
```

几个立刻有用的读数：

- `u, v, w` 是坐标三元组，配合 `coordSys`（AB / CD / EF / GH 四套坐标系）使用；
- `CreateNormalAttack` 的伤害由 `damage` 和一组 `sLvMultiplierOf*` 系数决定
  （攻击力、特效、韧性削减、Fever 槽），`sLv` 应指技能等级；
- `CreateHitArea` 的 `exprs11` / `exprs21` 是两个内嵌 Block。从实例推断（**未经确认**）
  前者是生成时、后者是命中时执行：`exprs11` 里放的都是 `ShowEffect` / `MoveHitArea`，
  `exprs21` 里放的都是 `CreateNormalAttack` / `ShakeCamera`。这解释了为什么典型技能一层套一层；
- `CreateShield` 只要 5 个参数就能做出环绕护盾，`movementKind` 直接支持顺/逆时针旋转。

### 仍然未知的

参数**名**有了，参数的**单位和取值范围**还没有：`frame` 大概率是帧，`w` 是角度还是标量、
`symbol` 指向什么资源、`param11 / param21 / param22` 具体含义，都还得靠对照实例反推
或读解析器。这层留给需要时再补。

## 下一刀

把 `action_skill` / `leader_ability` / `ability` 三张 master 和 DSL 接起来，回答
"数据里怎么配一个技能"。现在这三张表可以直接 dump：

```bash
python3 tools/orderedmap.py inspect WFTest/assets/trial/production/master/skill/action_skill.orderedmap
```

到那时 R3（原创角色 001）才有完整依据。
