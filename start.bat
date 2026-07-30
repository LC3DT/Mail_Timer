@echo off
chcp 65001 >nul
cd /d "%~dp0"

:: 检查是否已在运行
if exist email_scheduler.pid (
    set /p PID=<email_scheduler.pid
    tasklist /FI "PID eq !PID!" 2>NUL | findstr "!PID!" >nul
    if !errorlevel! equ 0 (
        echo [警告] 程序已在运行中 (PID: !PID!)
        echo 如需重启请先执行 stop.bat
        pause
        exit /b 1
    ) else (
        del email_scheduler.pid 2>nul
    )
)

:: 使用 pythonw.exe 后台运行（无命令行窗口）
echo 正在启动邮件定时发送程序...
start "" /B pythonw.exe email_scheduler.py

:: 等待 PID 文件生成
timeout /t 2 /nobreak >nul
if exist email_scheduler.pid (
    set /p PID=<email_scheduler.pid
    echo [成功] 程序已启动 (PID: !PID!)
    echo 关闭此窗口不影响程序运行。
) else (
    echo [失败] 程序启动失败，请检查 .env 或 tasks.json 配置。
    type email_scheduler.log 2>nul
    pause
)
