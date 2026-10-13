@echo off
chcp 65001 >nul
title 校园二手物品交易平台 - 本地启动服务
echo =======================================================
echo          중고캠퍼스 校园二手物品交易平台 (V2)
echo =======================================================
echo.
echo [1/2] 正在启动后台 Web 服务 (端口 5001)...

set PATH=C:\Users\ROG\AppData\Local\Programs\Python\Python312;C:\Users\ROG\AppData\Local\Programs\Python\Python312\Scripts;%PATH%

start /B python app.py

echo [2/2] 正在打开浏览器访问 http://127.0.0.1:5001 ...
timeout /t 2 >nul
start http://127.0.0.1:5001

echo.
echo 服务已就绪！测试账号：demo / demo123, buyer / demo123
echo 若要停止服务，直接关闭本命令行窗口即可。
echo =======================================================
pause
