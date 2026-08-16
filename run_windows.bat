@echo off
REM Run the static checks before opening a browser: a bad edit should be caught
REM here, not by hunting a ClientError halfway through a quest load.
python tools\verify_tree.py || goto :failed
node tools\verify_patches.mjs || goto :failed
echo.
python run_server_nocache.py --port 8081
pause
exit /b 0

:failed
echo.
echo 静态检查未通过，未启动服务。
echo 修好上面的问题后重试，或直接运行 python run_server_nocache.py --port 8081 跳过检查。
pause
exit /b 1
