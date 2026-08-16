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

## 支持但从未使用（12）——原创技能的免费能力

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
