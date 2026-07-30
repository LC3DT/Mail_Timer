@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist email_scheduler.pid (
    echo 状态：未运行
    exit /b 0
)

set /p PID=<email_scheduler.pid
tasklist /FI "PID eq %PID%" 2>NUL | findstr "%PID%" >nul
if %errorlevel% equ 0 (
    echo 状态：运行中 (PID: %PID%)
    echo.
    echo 最近日志：
    if exist email_scheduler.log (
        tail -20 email_scheduler.log 2>nul || powershell -Command "Get-Content email_scheduler.log -Tail 20"
    ) else (
        echo （日志文件不存在，终端输出不可见——后台模式正常现象）
    )
) else (
    echo 状态：已停止 (PID %PID% 进程不存在)
    del email_scheduler.pid 2>nul
)
