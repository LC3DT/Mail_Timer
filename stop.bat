@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist email_scheduler.pid (
    echo [提示] 未找到运行中的程序（PID 文件不存在）。
    exit /b 0
)

set /p PID=<email_scheduler.pid
tasklist /FI "PID eq %PID%" 2>NUL | findstr "%PID%" >nul
if %errorlevel% neq 0 (
    echo [提示] PID %PID% 进程已不存在，清理残留文件。
    del email_scheduler.pid 2>nul
    exit /b 0
)

echo 正在停止邮件定时发送程序 (PID: %PID%)...
taskkill /PID %PID% /F >nul 2>&1
if %errorlevel% equ 0 (
    del email_scheduler.pid 2>nul
    echo [成功] 程序已停止。
) else (
    echo [失败] 无法停止程序，请手动结束进程 PID: %PID%。
)
