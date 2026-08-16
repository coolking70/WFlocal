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
