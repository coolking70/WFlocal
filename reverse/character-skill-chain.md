# 角色 → 技能 → DSL 数据链

路线图 R2 第三刀。回答："数据里怎么配一个技能、技能怎么绑到角色。"

## master 行没有表头，schema 在构造函数里

master 行是无表头 CSV。bundle 里的 `pinball.master.generated.*Values` 类负责解析，
而它们的构造函数用**显式下标**读列：

```js
this['action_skill'] = row[0x8];
var a = row[0x9]; var b = row[0xa];
this['leader_ability'] = a == '(None)' ? None : Some({ id: parseInt(a), name: b });
```

所以权威 schema 是构造函数，**不是字段顺序**。字段顺序会错：上面 `leader_ability`
一个字段吃**两列**，这正是 `CharacterValues` 声明 19 个字段却对应 20 列的原因。

全量统计：171 个 Values 类、1635 个字段，其中 **199 个字段跨多列**。

```bash
python3 tools/master_schema.py --write                 # 生成 reverse/master_schema.json
python3 tools/master_schema.py --show CharacterValues
python3 tools/master_schema.py --decode <file.orderedmap> --as CharacterValues
```

`--decode` 直接把真实行按列名打出来，嵌套表和多行记录都能处理。

## 完整链路（用 brown_fighter 实测）

```
character.orderedmap  key=121001
  string_id       brown_fighter
  rarity          5
  element         1
  race            Human
  action_skill    brown_fighter          ← 指向技能表的 key
  leader_ability  121001 | 幽幻の舞踏      ← id + 名字，两列
  ability_1..3    1210011 / 1210012 / 1210013
        │
        ▼
action_skill.orderedmap  key=brown_fighter  →  嵌套一层技能等级  key=1
  name            シャムシール・バラディ
  description     華麗な剣舞で、しばらくの間ぶつかった敵に水ダメージ…
  icon_id         dynamic/skill/atk_surround
  unisonable      true
  min/max_skill_weight  500 / 500
  program_path    battle/action/skill/action/rare5/brown_fighter$brown_fighter_1
        │
        ▼
assets/production/battle/action/skill/action/rare5/brown_fighter$brown_fighter_1.action.dsl.json
        │
        ▼
DSL 命令序列（见 dsl-capability-matrix.md）
```

**`program_path` 就是接缝**：master 侧配的是元数据（名字、图标、权重、解锁条件），
实际行为完全在 DSL 文件里。这意味着做原创技能时，两侧可以独立推进——
先用现有 DSL 文件挂一个新角色跑通链路，再单独迭代 DSL。

`action_skill` 表是**两层嵌套**：技能 key → 技能等级 → 行。同一技能的不同等级
可以指向不同的 `program_path`（也可以相同）。

## 一个必须知道的坑

`action_skill` 的行实际有 **16 列**，但这个体验版的解析器只读前 **9** 列：

```
tail columns 9..: ['0', '250', '', '0', '0', '', '']
```

后面 7 列是数据里带着、但当前 build 不解析的字段（很可能是更新版本的）。

含义：**自制行至少要凑够解析器读的那些列，多出来的列会被忽略**。所以照抄官方行再改，
比从零拼安全。

## 相关 schema 速查

```bash
python3 tools/master_schema.py --show CharacterValues
python3 tools/master_schema.py --show ActionSkillValues
python3 tools/master_schema.py --show LeaderAbilityValues
python3 tools/master_schema.py --show CharacterStatusValues
```

## R2 完成情况

| 刀 | 产出 |
| --- | --- |
| 一 | 命令清单：34 支持 / 22 已用 / 12 未用（`dsl-capability-matrix.md`） |
| 二 | 参数名：从 `__params__` 运行时提取（`reverse/enum_params.json`） |
| 三 | master schema + 数据链（`reverse/master_schema.json`、本文） |

R3（原创角色 001）需要的依据齐了。还缺的是**参数单位**（帧/像素/角度）和
`character_status` 的数值曲线含义，这两项建议在 R3 做第一个角色时按需反推，
比现在空推更有效。

## 改技能：按参数名改，不按下标改

技能行为全在 DSL 文件里，而 DSL 是**位置数组**——`["CreateNormalAttack", 2, 255, [], [], 4, …]`。
参数名在 `reverse/enum_params.json`（来自 Haxe 构造函数的 `__params__`），
`tools/tune_skill.py` 用名字寻址：

```bash
python3 tools/tune_skill.py --dsl '<fork>.action.dsl.json' --show
python3 tools/tune_skill.py --dsl '<fork>.action.dsl.json' \
        --command CreateNormalAttack --set damage=999999
python3 tools/tune_skill.py --dsl '<fork>' --restore --from '<官方原文件>'
```

工具复现官方排版（数组 `", "`、对象紧凑），**63 个官方 DSL 全部逐字节重编码一致**，
所以改一个参数只产生一个 token 的 diff；并且拒绝写 `wfmod/` 分叉目录以外的文件。

### `CreateNormalAttack.damage` 是固定伤害（实证）

`4 → 999999`，**倍率 `sLvMultiplierOfAttackPoint` 保持 0.4 不动作为对照**，
实机结果：技能一击秒杀 boss，控制台无报错。

一次改动同时结论了两件事：分叉出来的 DSL 文件**确实被读取**（不是还在跑官方那份），
且这个字段是与攻击力无关的**平砍固定伤害**。官方数据里它的取值范围是 0～1150
（85 处 `CreateNormalAttack` 中 53 处为 0），999999 明显越界于正常范围，无法被误读。

秒杀是测试便利，不是设计值。改回去：`--set damage=4`。

## 被动（ability）的设计边界

做原创角色时会撞到的一条限制，实测确认：

`AbilityTriggerConditionKind` 只有三种：`Instant` / `During` / `Opening`。

- `Opening`（开场）的效果种类是 `OpeningAbilityKind`，只有
  `MyselfExpBoost` / `AllyExpBoost` / `ManaBoost`——**都是战斗外的养成收益**；
- `Instant` 的触发器是 `Fever` / `SkillInvoke` / `SkillMax` / `Condition*`，
  **没有"战斗开始"**；
- 与技能槽相关的效果是 `SkillGauge`（一次性）和 `SkillGaugeCharging`（持续速率），
  但它们只能挂在上面那些触发器上。

结论：**"开场获得满能量"在这个 build 的数据模型里做不成被动**。原版里类似的效果，
要么走的是这个 build 没有的触发器，要么是别的机制。

测试需要这个效果时，用运行时开关（见下），不要试图硬凑 ability 数据。

## 开发用开关

都默认关闭，从启动 URL 打开，开启时控制台会打 `[WFMod] DEV AID active`：

| 开关 | 效果 | 实现入口 |
| --- | --- | --- |
| `?wfdev=fullskill` | 开场满技能槽，之后正常充能 | `BattleContinuationData.getSkillPointRatio` |
| `?wfdev=fastskill` | 持续快速充能 | `MemberAbilityTotalizer.getTotalSkillGaugeCharging` |
| `?wfdev=stats` | 打印每个队员解析出的 hp/atk | `MemberImpl` 上的 4 个候选方法 |
| `?wfdev=trace:类.方法` | 追踪任意方法是否被调用 | 任意 prototype 方法 |

`stats` 最初只挂 `MemberImpl.getMaxHealthPoint`，实机毫无输出——那是一次没有依据的挂载点
猜测。现在同时挂 4 个候选（`getMaxHealthPoint` / `getCurrentHealthPoint` /
`getSkillPointRatio` / `isDead`），谁被调用谁报告，并打印实际武装成功的探针数量。

`trace` 是为了**不再靠猜**：想知道某个方法到底会不会被调用，不用改代码再发一版，
直接在 URL 里问：

```
?wfdev=trace:pinball.scene.battle.battle.squad.member.MemberImpl.getMaxHealthPoint
```

多个用 `;` 分隔。每个目标最多打印 20 次，附带该对象上的标量字段。

`fullskill` 可带比例（`fullskill:0.5`），`fastskill` 可带加成（`fastskill:2000`）。

`fullskill` 的原理是：成员初始化时执行 `skillPoint.setRatio(restore.getSkillPointRatio(index))`，
开场能量取自**续战数据**；新战斗没有记录所以返回 0，抬高它等于让游戏以为上次退出时槽是满的。
取 `max(原值, ratio)`，真实续战不会被调低。

两者都是 hook，**不改任何数据**，所以它们不是"被动技能"，只是测试辅助。

## 数值改动确实生效（A/B 实证）

`character_status` 的改动是否被游戏读取，靠推断说不清——战斗内数值叠加了队长技和被动，
绝对值对不上插值预期。用极端值做 A/B 才有结论。

把 129001 的 10 级和 80 级锚点临时设为 `9000/1`，进战斗读数：

```
member 0  hp=9214  atk=43     ← 129001
member 1  hp=1288  atk=178    ← 对照，与改动前一字不差
member 2  hp=1153  atk=200    ← 对照，与改动前一字不差
```

超出部分（9214 vs 9000、43 vs 1）来自加成。两个对照成员完全不变，排除了偶然。

**方法论**：验证一处数据是否被读取时，用**无法误读的极端值**加**未改动的对照**，
不要用"看起来差不多"的正常值去推断。
