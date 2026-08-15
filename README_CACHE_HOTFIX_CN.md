# v0.2.2 缓存 Hotfix

## 为什么 v0.2.1 仍然报 key=4 不存在

v0.2.1 ZIP 内的 `player_iosbundled.orderedmap` 已经实际包含 key=4。
如果仍出现 `key=4 ... player_iosbundled.orderedmap`，说明浏览器/Node `http-server` 返回了上一版缓存。

本版同时使用三层防护：
1. 启动 URL 加 `wfbuild=0.2.2`；
2. 所有同源 XMLHttpRequest 自动追加该 build 参数；
3. 自带服务器发送 `Cache-Control: no-store`。

建议直接运行 `run_windows.bat` 或 `run_macos_linux.sh`。
控制台应首先看到：
`[WFMod] build=0.2.2 mode=challenge`

如果坚持使用 npm http-server，请用：
`npx http-server WFTest -p 8081 -c-1`
并从本版 `index.html` 进入。
