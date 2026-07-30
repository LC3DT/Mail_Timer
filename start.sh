#!/bin/bash
# 邮件定时发送程序 — Linux 后台启动脚本
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PID_FILE="$SCRIPT_DIR/email_scheduler.pid"
LOG_FILE="$SCRIPT_DIR/email_scheduler.log"

# 检查是否已在运行
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "[警告] 程序已在运行中 (PID: $PID)"
        echo "如需重启请先执行: ./stop.sh"
        exit 1
    else
        rm -f "$PID_FILE"
    fi
fi

# 确认 .env 或 tasks.json 存在
if [ ! -f "$SCRIPT_DIR/.env" ] && [ ! -f "$SCRIPT_DIR/tasks.json" ]; then
    echo "[错误] 未找到 .env 或 tasks.json 配置文件。"
    echo "请先配置: cp .env.example .env  或  cp tasks.json.example tasks.json"
    exit 1
fi

# 后台启动（nohup 保证关终端不中断）
echo "正在启动邮件定时发送程序..."
nohup python3 email_scheduler.py >> "$LOG_FILE" 2>&1 &
PID=$!
echo $PID > "$PID_FILE"

sleep 1
if kill -0 "$PID" 2>/dev/null; then
    echo "[成功] 程序已启动 (PID: $PID)"
    echo "日志文件: $LOG_FILE"
    echo "关闭终端不影响运行。查看状态: ./status.sh  停止: ./stop.sh"
else
    echo "[失败] 程序启动失败，请查看日志:"
    tail -20 "$LOG_FILE"
    rm -f "$PID_FILE"
    exit 1
fi
