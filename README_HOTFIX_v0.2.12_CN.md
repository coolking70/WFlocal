# v0.2.12：关闭本体的服务器上报

## 症状

游戏本身已可正常游玩，但每次场景切换控制台都会留下一条：

```
POST https://api.worldflipper.jp/api/index.php/reproduce/post net::ERR_CONNECTION_CLOSED
```

## 原因

`LogicSnapshot.applyLogicSnapshot()` 在每次场景切换时会走：

```
if (devConfig.normalReport) {
    ErrorReporter.reportToServer(makeDebugInfo('正常系自動送信', ...), reproduceData);
}
```

即本体的「正常系自动送信」——把逻辑快照上传到官方服务器。本地构建连不上那台服务器，
于是每次切换都留下一条失败请求。崩溃上报（`saveCrashReport` / `sendCrashReport`）走的是同一条上传通道。

## 处理方式

在挑战模式启动补丁里，把 DevConfig 构造函数里这三个默认值改成 false：

```
normalReport / saveCrashReport / sendCrashReport
```

这是本体自己的开关，不是外科手术。`Top.hx` 里在使用 dummy remote 时，本体也是把
**恰好这三个**一起关掉的（同一处还会切 `remote=EmptyRemote`、`payment=DummyPayment`，
那部分我们没有动，只取上报这一组）。

没有改成在 XHR 层拦截：那样请求虽然发不出去，但上传任务拿不到 load/error 回调，
上报队列会一直挂着；从源头关掉开关更干净。

本地诊断通道不受影响——v0.2.10 装的 ClientError 报告器仍然会把每个不同的
`code:message` 打一行到控制台。

## 测试

进入挑战模式，控制台应看到：

```
[WFMod] build=0.2.12 mode=challenge ... unlock=guarded tips=fallback report=off
[WFMod] v0.2.12 runtime patch applied: server report uploads disabled ...
```

之后正常游玩，控制台不应再出现任何 `api.worldflipper.jp` 的请求。
