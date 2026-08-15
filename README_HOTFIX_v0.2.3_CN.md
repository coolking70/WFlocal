# v0.2.3：完整 Trial Master 合并 Hotfix

## 为什么 v0.2.2 仍卡在 50%

v0.2.2 已成功让 `getPlayerSaveData(4)` 读取到挑战玩家，但 player 4 的队伍引用正式挑战角色（例如 `121001` brown_fighter）。启动阶段仍加载 `character_iosbundled.orderedmap`，这个教程小表只有角色 1/4/5/6，因此下一步再次触发 ClientError 8601。

## v0.2.3 的处理方式

不再逐个补缺失 key。对 Trial master 中所有同时存在：

- `foo.orderedmap`（完整 Trial 表）
- `foo_iosbundled.orderedmap`（教程启动小表）

的文件进行递归 union merge：完整表作为基础，iosbundled 记录在同 key 冲突时优先。这样既保留教程专用记录，又把挑战模式需要的角色、技能、Boss、Zone、文本等记录补入启动数据集。

本构建共发现 71 对表，其中 44 对实际增加了记录。

关键结果：

- `character_iosbundled`: 4 -> 22 个角色；
- `character_text_iosbundled`: 4 -> 22；
- `character_status_iosbundled`: 17 -> 107 个记录节点；
- `skill/action_skill_iosbundled`: 10 -> 179 个记录节点；
- `ability/leader_ability_iosbundled`: 2 -> 22；
- `battle/zone_iosbundled`: 13 -> 25；
- `generated/trimmed_image_iosbundled`: 51 -> 2139。

挑战队伍的 18 名角色现在全部存在于 character / character_text / character_status 的启动 Master 中。

## 测试

运行 `run_windows.bat` 或 `run_macos_linux.sh`，进入挑战模式。控制台应看到：

`[WFMod] build=0.2.3 mode=challenge master=merged-trial`

如果仍出错，只需要提供**第一条 ClientError 8601 的完整 internalMessage**；它将代表已经进入更深一层的依赖，而不是旧的 player/character master 问题。
