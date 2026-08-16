# `tools/orderedmap.py`：master 表读写工具

自制关卡的前置工具。运行时没有变化，因此启动器版本仍是 v0.3.1。

## 格式

在全部 286 张表上验证通过：

```
file   := u32 index_len, zlib(index), record_bytes
index  := u32 count, (u32 key_end, u32 record_end) * count, key_bytes
record := zlib(csv_row) | 嵌套 orderedmap | 不透明字节
```

`key_end` / `record_end` 是**累计结束偏移**，第 i 条覆盖 `[end(i-1), end(i))`。

> 这里有个坑值得记下来：这两个 u32 很容易被误读成 `(key, offset)` 对。
> 我最初就是这么读的，于是把 `main_quest` 的顶层 key 读成了整数 `3`——
> 实际那是字符串 `"111"` 的长度。误读之下嵌套表根本解不开，还因此得出过
> "第 4 关不存在"的错误结论。key 是变长 UTF-8 字符串，不是整数。

值有三种：

| kind | 含义 |
| --- | --- |
| `row` | 单个 zlib 流，内容是一行 CSV 式 UTF-8 文本 |
| `map` | 嵌套 orderedmap，结构与顶层完全相同，可以递归任意层 |
| `blob` | 其余情况，原样保留 |

判别方式不靠猜 header：`row` 的 zlib 流必须**恰好覆盖整条记录**（`unused_data` 为空），
否则就尝试按嵌套表解析，再不行才当 blob。

## 无损性

数据里所有 zlib 流在 **level 9** 下重新压缩都能逐字节复现原文，所以 decode → encode
是真无损，不需要把原始压缩块存进 JSON。

这一点是全量证明的，不是抽样：

```
$ python3 tools/orderedmap.py roundtrip $(find WFTest/assets -name "*.orderedmap")
286/286 files round-trip byte-identical
```

改动这个文件后请重跑这条命令。

## 用法

```bash
python3 tools/orderedmap.py inspect <file>...            # 结构与样例行
python3 tools/orderedmap.py dump <file> [-o out.json]    # 解码成 JSON
python3 tools/orderedmap.py build <in.json> <out>        # JSON 编回 .orderedmap
python3 tools/orderedmap.py diff <a> <b>                 # 按 key 比较，递归展开
python3 tools/orderedmap.py roundtrip <file>...          # 无损校验
```

`diff` 会把嵌套结构拍平成 `111/1/4` 这样的路径，所以能直接看出我们对官方数据做了什么：

```
$ python3 tools/orderedmap.py diff <原档的 main_quest> WFTest/.../quest/main_quest.orderedmap
  only in a  0
  only in b  1
  changed    0

--- only in b ---
  111/1/4
```

这正是第 4 关。整棵树相对原档的数据改动只有这一行。

## 示例：第 4 关长什么样

```
$ python3 tools/orderedmap.py inspect WFTest/assets/trial/production/master/quest/main_quest.orderedmap
  1 entries (1 map)
    '111' ->                                    # chapter
      1 entries (1 map)
        '1' ->                                  # stage node
          4 entries (4 row)                     # quest
            '1' -> 111001001,VS ガーディアンゴーレム,...
            '2' -> 111001002,VS クラーケン,...
            '3' -> 111001003,VS 妖狐,...
            '4' -> 111001004,CUSTOM STAGE PoC - Guardian Mirror,...
```

`chapter / stage_node / quest` 三层嵌套，`trialStageNodeId = 111001` 对应前两层。
TrialQuestSelect 是原生枚举这一层的（交接文档 §27），所以往这里加行就会多出一张卡。
