# WFDemo Stage Select v0.2.3 测试说明

1. 请解压到全新目录，不要覆盖旧版本。
2. Windows 运行 `run_windows.bat`；macOS/Linux 运行 `run_macos_linux.sh`。
3. 打开 `http://127.0.0.1:8081/`。
4. 选择“挑战 / 自制关卡”。
5. 控制台应首先出现：

   `[WFMod] build=0.2.3 mode=challenge master=merged-trial`

本版针对 v0.2.2 的第二个 50% 崩溃：player 4 已能读取，但其队伍角色 121001 等不存在于教程 iosbundled character master。v0.2.3 将 71 对完整/iosbundled Trial master 做递归合并，44 张表实际得到扩充。

重点验证：
- 是否越过 50%；
- 是否进入原生 3 个挑战关列表；
- 是否出现第 4 个 CUSTOM STAGE PoC；
- 原版三关与第 4 关是否可进入；
- AUTO 是否仍正常。

如果仍报错，请展开第一条 `[ClientError]:8601` 对象，把 `val.internalMessage` 完整内容发回。后续重复的 SipoError/事件错误通常是首个异常造成的连锁反应。
