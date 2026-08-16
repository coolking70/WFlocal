# R3 第一步：原创角色的最小闭环

目标不是做出一个原创角色，而是**先把一个新角色 ID 送进战斗**——在任何原创美术和技能数据
之前。这一步会立刻暴露数据链上还缺什么，失败成本极低。

## 做法

克隆官方角色 `121001`（ソーニャ / brown_fighter）到 WFMod ID `129001`，
**保留 string_id 不变**，于是所有资源路径仍指向已发布的美术，一张新图都不用做。

```bash
python3 tools/clone_character.py --from 121001 --to 129001 --name-prefix "WFMOD "
python3 tools/assign_character.py --player 4 --party 1 --slot main1 --character 129001 --level 20
```

两个都可回滚：

```bash
python3 tools/assign_character.py --player 4 --party 1 --slot main1 --restore
python3 tools/clone_character.py --from 121001 --to 129001 --revert
```

## 一个角色 ID 牵动 12 张表

不是猜的，是扫出来的：

```
character/character                     角色行本身
character/character_text                名字与介绍
character/character_status              数值曲线（嵌套 4 个等级档）
character/character_speech              语音
character/character_gacha_sound         抽卡音效
character/full_shot_image_attribute     立绘属性
generated/character_image               图像引用
generated/mana_board                    魔法盘布局
mana_board/mana_node                    盘上节点
mana_board/upskill                      盘上技能强化
ability/leader_ability                  队长技（以角色 ID 为 key）
skill_preview/skill_preview_character   技能预览
```

加上玩家侧两张：

```
player/player_character   <玩家>/<角色ID> -> 等级
player/player_party       <玩家>/<队伍>   -> main1..3, unison1..3
```

这些表大多是**嵌套**的，顶层 key 就是角色 ID，所以克隆顶层 entry 会带走整棵子树
（`character_status` 的 4 个等级档、`mana_board` 的 26 个节点都是这么来的）。

## ID 命名

用 `129001` 而不是 `9xxxxx`。

官方 ID 的编码是 `(6-稀有度)(属性+1)(四位序号)`：`121001` = 稀有度 5、属性 1、序号 1001；
`221002` = 稀有度 4、属性 1。前两位很可能被资源约定或其他系统依赖，贸然换成 `9xxxxx`
会同时改变稀有度和属性的编码。

所以 WFMod 的命名空间取**序号段 9000+**，前缀沿用官方编码。既是独立命名空间
（不会和官方 ID 撞），又不破坏编码含义。

> 这与"自制内容走独立命名"的决定一致；如果后续确认前两位并无依赖，再迁移到纯 `9xxxxx` 也不迟。

## 克隆时改了什么

只改了三处，其余逐字节照抄：

| 位置 | 改动 | 原因 |
| --- | --- | --- |
| `character.leader_ability` 第 9 列 | `121001` → `129001` | 指向克隆出来的队长技行 |
| `character.identity_character_id` 第 15 列 | `121001` → `129001` | 指向自己 |
| `character_text` 名字列 | 加前缀 `WFMOD ` | **在游戏里一眼能认出来** |

名字前缀是这一步的验证手段：如果队伍里显示 `WFMOD ソーニャ`，说明克隆真的生效了，
而不是回落到了原角色。

## 现在的状态

```
挑战关卡 1 的队伍（player 4 / party 1）：
  main1   129001   ← WFMOD ソーニャ
  main2   221003
  main3   221002
  unison  321002 / 221006 / 321004
```

挑战关卡按关号选队伍（关卡 1 用队伍 1），所以第一关的队长就是这个克隆角色。

## 需要验证

`./tools/verify_all.sh` 全过，286 张表仍全部无损 round-trip，bundle 仍是原档 SHA。
浏览器侧需要确认：

- 挑战模式关卡 1 能进；
- **队伍里显示 `WFMOD ソーニャ`**；
- 战斗中该角色正常出现、技能可放、AUTO 正常；
- 战斗能正常结算；
- 控制台无 ClientError。

任何一项失败都是有价值的信息——它会指出数据链上还缺哪张表。

## 下一步

跑通之后按这个顺序逐项替换，一次只动一个变量：

1. `character_text` 名字与介绍 → 真正的原创设定；
2. `character_status` 数值 → 原创数值；
3. `action_skill` 行 → 指向新的 `program_path`；
4. `.action.dsl.json` → 原创技能行为（可用那 12 个官方没用过的命令）；
5. 美术：像素、立绘、头像、技能图标。
