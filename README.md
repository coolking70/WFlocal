# WFlocal — World Flipper 体验版的本地修改工程

一个离线可跑的 World Flipper Web 体验版，加上一层可撤销的修改工具链。

**原则**：`WFTest/world-flipper.js` 是官方原档（sha256 `db5f3806…a814315`），**永不修改**。
所有对代码的改动是 `WFTest/game-index.html` 里的**声明式补丁表**（运行时打在内存副本上），
所有对数据的改动都有工具和 `--revert`。

```bash
./run_macos_linux.sh          # 跑全部静态检查，然后起服务并打开测试页
./tools/verify_all.sh         # 只跑检查（约 10 秒）
```

启动后打开的是 `game-index.html?wfmode=challenge&wfdev=fullskill`。
右下角 **WFMod Hub** 按钮可以看数值、看技能 DSL、改参数。

---

## 一、已经用实验确定的事

下面每一条都有实机证据，出处在括号里。**没有列进来的就是还没确定的**，
不要当成已知（这个项目吃过好几次"看起来合理的推断"的亏）。

| 结论 | 依据 |
| --- | --- |
| 参数时间单位是**帧，60fps** | `ShowEffect.lifetime` 347→120，实测约 2 秒 |
| 长度单位是**逻辑像素**（540×960） | `u=2000` 把特效推出画面；源码 `stepPos` 无缩放 |
| 角度单位是**弧度** | `NWay 6 @0.5236` 产生 ±15/45/75° 的判定朝向 |
| terrain 单位 **×6 = 世界坐标** | 房间中心 (136,526) → trace 报 (816,3156) |
| `CreateNormalAttack.damage` 是**与攻击力无关的固定伤害** | 4→999999 一击秒杀，倍率作对照未动 |
| `character_status` 的改动**确实被读取** | 极端值 A/B，两名对照成员一字不差 |
| `NWay` 分**朝向**不分位置 | 六块判定 x/y 相同、仅 r 不同；源码偏移写死为 0 |
| **判定区永不渲染** | 它是物理形状，不进显示列表 |
| DSL 负数 id 是**绑定好的固定点** | `-1` 场地中心 / `-2` 左上 / `-17` 角色 / `-18` 弹珠 |
| 开场满能量**做不成被动** | `AbilityTriggerConditionKind` 没有"战斗开始"触发器 |
| master 行的 schema 在**构造函数**里，不是字段顺序 | 199 个字段跨多列 |
| 波次 = zone 表嵌套键 = terrain 图层 | `tutorial_5` 两间房的结构 |
| 同屏小怪上限 **10** | `ZoneValues` 只解析 `zako01..zako10` |

详细记录：
[`reverse/character-skill-chain.md`](reverse/character-skill-chain.md)（角色→技能→DSL、单位、开发开关）、
[`reverse/custom-stage.md`](reverse/custom-stage.md)（关卡结构、坐标系、四个踩过的坑）、
[`reverse/dsl-capability-matrix.md`](reverse/dsl-capability-matrix.md)（34 条命令，22 已用）、
[`reverse/README.md`](reverse/README.md)（bundle 索引怎么生成、边界在哪）。

## 二、仍未确定的

- **等级曲线**：`character_status` 只有 4 个锚点（1/10/80/100），插值公式未反推。
  这是 Hub 不显示"20 级 HP"的原因——数据支撑不了的数字不显示。
- `CreateShield` 的占位素材契约：注册资源后仍在 `flatomo.timeline.Playhead` 抛 INTERNAL ERROR。
- `movingSpeed`、`Line(s, o)` 的单位（标为 inferred，界面不做换算）。
- `SPAWN3` / `SPAWN6` 里那个数字的含义（所以加出生点时照抄原对象类型）。

## 三、当前这份 mod 里有什么

| | 内容 | 撤销方式 |
| --- | --- | --- |
| 角色 | `129001` WFMOD 001 試作体，队伍 4/1 的队长 | `set_character.py` / `assign_character.py` |
| 技能 | `wfmod_001`，分叉自 `brown_fighter`：场地中心六向 30° 展开的长条判定，8 帧一跳 | `fork_skill.py --revert` |
| 关卡 | 挑战第 4 关「WFMOD 練習場」——小怪房间（10 只网格分布）→ boss 房间 | `dummy_stage.py --revert` |
| 界面 | WFMod Hub：队伍数值 / DSL 视图 / 参数编辑 | 不改游戏，`?wfhub` 才展开 |
| 补丁 | 8 个（challenge 模式），见 `game-index.html` 的 `PATCHES` | 表里删掉即可 |

挑战关卡 1~3 保持原样，它们是验证其他改动时的基准。

## 四、工具

**读**

```bash
python3 tools/analyze_bundle.py find <name>       # 类 / 方法 / 错误码检索
python3 tools/master_schema.py --show <Class>     # master 表的列布局
python3 tools/master_schema.py --decode <f> --as <Class>
python3 tools/orderedmap.py inspect|dump <f>     # master 表结构 / 转 JSON
python3 tools/tune_skill.py --dsl <f> --show     # 技能 DSL 按参数名展开
```

**改**（每个都可逆）

```bash
python3 tools/clone_character.py                 # 复制一个角色
python3 tools/set_character.py                   # 改身份 / 数值
python3 tools/fork_skill.py                      # 让角色拥有独立的技能与 DSL
python3 tools/tune_skill.py --command X --set p=v # 改 DSL 参数
python3 tools/dummy_stage.py --build|--revert    # 训练场
```

**生成**

```bash
python3 tools/analyze_bundle.py index            # reverse/*.json
node tools/dump_runtime_enums.mjs                # enum 参数名
python3 tools/build_dsl_reference.py             # Hub 用的参考（含中文说明）
python3 tools/stamp_assets.py                    # 三个 wfmod 脚本的 cache-buster
```

## 五、护栏：`./tools/verify_all.sh` 覆盖什么

| 检查 | 拦住的是 |
| --- | --- |
| 树 vs 原档清单 | 误改原档、意外多出的文件 |
| 补丁表 | anchor 不唯一、打完不能解析、hooks 挂在 load 事件上 |
| cache-buster | 三个脚本任一过期（浏览器跑旧代码，看起来像功能坏了） |
| `ADDED_ASSETS` | 路径不是根相对、**分叉件与模型不在同一个资源根**（游戏会静默加载原版） |
| orderedmap 往返 | 286/286 逐字节一致 |
| 两个解析器 | 浏览器版与 Python 版对 286 张表结果一致 |
| DSL 参考时效 | Hub 显示昨天的数据 |
| Hub 渲染 | join 错误（渲染出"自信的错误界面"） |
| 编辑路径 | 写入有损、拒绝失效、**HTTP 路线没人调用过** |

**不覆盖**：任何需要游戏真正跑起来的事。启动、进关卡、AUTO、战斗结算、
技能表现——**这些只能在浏览器里由人验**，本仓库不假装验过。

## 六、方法论（都是这次踩出来的，代价具体）

1. **现象不明显时先回源码确认参数怎么被消费**，再设计判据；不要靠加大数值反复试。
2. **让两种结果签名不同**（滞留/不滞留），而不是幅度不同（偏了多少）。
   幅度判据要求观察者先能认出观察对象，而这个前提常常不成立——
   那时得到的是**无法解读的结果，不是否定结论**。
3. **"修好了一个真实缺陷" ≠ "找到了原因"**。现象没随修复改变时，原因还在别处。
   这一条花掉了木桩关卡四轮里的两轮。
4. **验证数据是否被读取，用无法误读的极端值 + 未改动的对照。**
5. **测试要覆盖调用者实际走的路径**，不是被测函数最方便的入口。
   编辑功能第一版写入器是好的、HTTP 路线从没被调用过，而所有检查都通过了。
6. **一个改动"看不出变化"有两种可能**：没生效，或者生效了但在这个配置下本来就不该有可见差别。
   只有把内部状态读出来才分得清——`?wfdev=trace` 就是为此存在的。
