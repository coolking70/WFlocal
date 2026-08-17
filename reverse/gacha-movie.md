# 抽卡落球动画

回答："抽卡这块二次开发能做到什么地步。"独立入口已跑通（`wfmode=gacha`）。

## 链路

```
SceneKind.TutorialLightBallMovie(progressKind)     ← 只要 1 个参数
  └─ TutorialLightBallMovieScene.preparation()
       new BallMovie(BallMovieKind.SingleMovie('gacha/tutorial_light'))
            └─ assets/production/gacha/tutorial_light.gacha.json    ← 行为全在这里
                 └─ FixedFallingField + gacha_physics.*（45 个类，纯本地）
```

`BallMovieKind` 只有两种：

| | 参数 | 需要什么 |
| --- | --- | --- |
| `SingleMovie` | `configPath` | 只要配置文件。**不需要抽卡 master 数据，播放不发远程** |
| `Gacha` | `gachaId, drawKind, resultCharacterIds, drawIndex, draw` | 构造时就 `getGachaRepository().getGacha(gachaId)`，而 `gacha` 表是空的 |

随机数是 `pinball.common.random.MersenneTwister`，按种子初始化——**钉住种子能逐帧复现同一次落球**。

## 种子是数据，不是硬编码

```js
// FallingField 构造函数
if (Object.prototype.hasOwnProperty.call(config, 'seed')) seed = config.seed;
else                                                     seed = Date.getTime();
```

官方配置里有 `"seed": 12345`，删掉这个键就变成按时钟播种。

```bash
python3 tools/gacha_movie.py --seed random    # 每次不同
python3 tools/gacha_movie.py --seed 12345     # 钉住，用于判断物理改动
```

## 一次几颗球：代码支持，缺的是数据

```js
BallMovieGachaSource.getGachaConfig(i) {
  config = getGachaConfig(GachaMovieIdTools.getGachaConfigAssetPath(this.draw[i].movie_id));
  config = copy(config);
  config.seed = this.draw[i].seed;        // 每颗球的种子来自 draw
}
getAllGachaConfig() { return this.draw.map(…) }        // 一颗球一个 config
getResultCharacterId() { return Some(this.resultCharacterIds[this.drawIndex]) }
```

**球数就是 `draw` 数组的长度**，没有硬编码上限。而且入场演出的素材已经带了十连序列：

```
entry_movie_back / entry_movie_front → ['once', 'ten_times_first', 'ten_times_other']
```

所以**十连缺的是 `gacha` master 那一行，不是美术**。顺带一个推论：真实抽卡里每颗球的种子由 `draw[i].seed` 给出，即**落点是服务端决定的**，客户端只是回放。

## 官方配置是教程道具，三处"关掉了"的开关

这三处都会让改动**看起来没生效**，而原因各不相同：

| 配置 | 官方值 | 后果 |
| --- | --- | --- |
| `threshold.ballStar4` | **1** | `probability` 是 `[0,1)` 的均匀分布，`probability > 1` 永不成立 → 稀有度恒为 0 |
| `amulet.totalCount` / `barAmulet.totalCount` | **0** | 场上没有护符 |
| `threshold.amulets` | **[]** | 护符稀有度要拿下标索引它 |

`amulet.totalCount = 0` 会**同时废掉三个演出**，因为它们都挂在护符上：

- **变色**：`amuletContactedHandler` 在球撞上 `rarity > 0` 的护符时隐藏护符、播接触特效、闪背景，并调用 `ballDisplayElement.updateRarity()`。**球的外观只有这一处会重读** ——所以空场时强制 `ball.rarity` 改的是一个再没人读的数字。
- **擦过减速**：`precalculateFieldResult` 逐个护符预算 `ballNearestDistance <= camera.slowDistance` 并记下帧号，播放时在那些帧减速（`BallMovieState.FallingSlow`）。
- **★5 升级**：`rarityUpStar5Dispatcher` → `rarityUpStar5Handler`，把前后两层冲击波移到那个护符的位置播放。

测试用值（**不是设计值**）：

```bash
python3 tools/gacha_movie.py --set threshold.ballStar4=0.7 \
    --set amulet.totalCount=6 --set barAmulet.totalCount=2 \
    --set 'threshold.amulets=[0,0,0,0,0,0]'
```

## 三种球的外观都在

`ball.timeline.json` 有 `rarity3` / `rarity4` / `rarity5`，`BallDisplayElement.updateRarity()`：

```js
playhead.gotoAndPlay(rarity > 1 ? 'rarity5' : rarity > 0 ? 'rarity4' : 'rarity3');
```

`rarity + 3` 就是星级（bundle 自己在 `verifyResultBallRarity` 里这么算）。

但**有些时间线只带了它用过的那一个序列**：`entry_movie_op_once` 只有 `rarity3`。
序列名找不到是**硬崩不是回退**（`rarity4は存在しないシーケンス名です`），
所以提高阈值后会黑屏。

```bash
python3 tools/gacha_movie.py --placeholder-rarities   # 把缺的别名到 rarity3
```

序列只是一段命名的帧区间，别名不需要新帧——每个稀有度播同一段动画，**是占位，看起来也就是占位**。

## 强制稀有度（测试开关）

```
?wfdev=ballrarity:1        球 → ★4（0/1/2 = ★3/★4/★5）
?wfdev=amuletrarity:1      所有护符 → 高稀有度，必定触发变色
```

hook 挂在 `FixedFallingField.initBallRarity` / `initAmuletRarity`。落球场会被模拟**两次**
（一次预算结果、一次播放），一个 hook 覆盖两次。

**在这条路径上强制是安全的，走 `Gacha` 路径就不是**：`verifyResultBallRarity` 会把模拟出的
球稀有度和结果角色的稀有度对比，不一致抛 3032——但它只在数据源报告了结果角色时才跑，
而 `SingleMovieSource.getResultCharacterId()` 返回 `None`。

## 独立入口的两处改动

1. `boot-router` 补丁：`wfmode=gacha` → `TutorialLightBallMovie(Shortened)`；
2. `gacha-loop` 补丁：`gotoNextScene` 原本要向教程仓库问"下一步"，而从启动路由进来
   **没有教程步骤状态**，`nextStep()` 返回 undefined、`getStepValues` 在它上面读
   `_hx_index` 直接崩。gacha 模式改成**重播自己**——既是修复，也正是测试台要的：
   一次播完就是一次新抽。

顺带确认：`tutorialUpdateStep` 这个远程调用**离线下不会失败**（崩溃发生在它之后）。

## 方法论

这条线上"改了没反应"出现了两次，两次的原因都不是开关没生效：

1. 稀有度恒定——**比较永不成立**（阈值正好是取值上界）；
2. 强制稀有度无效——**没有任何东西再去读那个值**（护符数为 0，唯一的读取点不会被触发）。

第二次尤其值得记：我先验证了 hook 确实挂上（对真 bundle，applied 非 failed），
证明"开关生效"，却因此没去查"生效之后有没有人用它"。**验证了因，不等于验证了果。**
而那两个 `0` 就在我自己两轮前打印的 `--show` 输出里。
