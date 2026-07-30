#!/bin/bash
# 邮件定时发送程序 — Linux 状态查看脚本
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$SCRIPT_DIR/email_scheduler.pid"
LOG_FILE="$SCRIPT_DIR/email_scheduler.log"

if [ ! -f "$PID_FILE" ]; then
    echo "状态：未运行"
    exit 0
fi

PID=$(cat "$PID_FILE")

if ! kill -0 "$PID" 2>/dev/null; then
    echo "状态：已停止 (PID $PID 进程不存在)"
    rm -f "$PID_FILE"
    exit 0
fi

echo "状态：运行中 (PID: $PID)"
echo "启动时间: $(ps -p "$PID" -o lstart= 2>/dev/null || echo '未知')"
echo ""
echo "最近日志："
if [ -f "$LOG_FILE" ]; then
    tail -20 "$LOG_FILE"
else
    echo "（日志文件不存在，如使用 systemd 请用 journalctl -u mail-scheduler 查看）"
fi
