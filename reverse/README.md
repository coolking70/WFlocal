# Reverse Atlas

`world-flipper.js` 是一个 29MB 的混淆 IIFE：局部变量全是 `_0xXXXXXX`，属性名写成
`\xNN` 转义，日文写成 `\uNNNN`。但 Haxe 留下了两个注册表——`$hxClasses` 和 `$hxEnums`
——它们的键是**真实类名**，而且每个类都记了 `__name__` / `__super__`。这就足够在不做
任何反编译的前提下恢复类与方法的全貌。

这个目录里的文件全部由工具生成，**不要手工维护**：

```bash
python3 tools/analyze_bundle.py index
```

耗时约 2 秒。bundle 全程只读。

## 内容

| 文件 | 数量 | 说明 |
| --- | ---: | --- |
| `classes.json` | 3282 | 类名、父类、prototype 方法、静态方法、偏移 |
| `enums.json` | 729 | enum 名与构造子 |
| `errors.json` | 285 | ClientError 码 → 消息 + 全部抛出点 |
| `scenes.json` | 878 | 类名含 `.scene.` 的类 |
| `masters.json` | 431 | 类名含 `.master.` 的类 |
| `remotes.json` | 51 | 名字里带 remote 的类 |
| `assets.json` | 1016 | bundle 里出现的资源路径 |

共 32569 个 prototype 方法。

## 偏移是"解码视图"里的位置

索引里的 `offset` 指的是**转义展开后**的文本位置，不是磁盘文件的字节位置。这样做是因为
解码后的视图才是人能读的（类名、日文消息都是明文）。要看某个偏移附近的源码：

```bash
python3 tools/analyze_bundle.py show 7772026
```

**补丁 anchor 仍然要用 `esc()` 构造**，和 `game-index.html` 里的做法一致——那是针对磁盘
原文的。这两套坐标不要混用。

## 常用查询

```bash
python3 tools/analyze_bundle.py find autoPlayUnlocked
python3 tools/analyze_bundle.py find GameSystemUnlockRepository
```

按错误码查（这几轮排障最常用的）：

```bash
python3 -c "
import json
e={x['code']:x for x in json.load(open('reverse/errors.json'))['errors']}
x=e[8601]; print(x['message']); print(len(x['sites']),'sites:',x['sites'][:5])
"
```

注意 `message` 有两种形态：字面量直接给文本；运行时拼接的给**表达式原文**，例如

```
8601 -> '指定されたキーは存在しません。key='+_0x269787['string'](_0x112883)+', '+_0x46ff18['extraInfo']
```

这是有意的——8601 有 117 个抛出点，消息是拼出来的，只存字面量的话这个码根本不会出现在索引里。
本项目前几轮追的 8601 / 2340 都属于这一类。

## 已知边界

- **只覆盖注册进 `$hxClasses` 的类。** 没注册的局部构造函数查不到。
- **`callgraph` 没有做，也不建议现在做。** 在混淆 bundle 上，调用图的节点全是 `_0x`
  局部名，构建成本高而可读性接近零。等到确有需求再说。
- **prototype 方法的提取有窗口限制**：从类注册点向后扫 200KB。绝大多数类的 prototype
  紧跟在注册之后，但极端情况可能漏。发现漏了就调大窗口。
- **静态索引 3282 个类，运行时注册表实测 3286 个**。差的 4 个是静态正则没匹配到的注册
  形式。运行时以 `window.WF_INTERNALS.classes` 为准，索引用于检索。
