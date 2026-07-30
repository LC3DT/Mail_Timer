#!/bin/bash
# 邮件定时发送程序 — Linux 停止脚本
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$SCRIPT_DIR/email_scheduler.pid"

if [ ! -f "$PID_FILE" ]; then
    echo "[提示] 未找到运行中的程序（PID 文件不存在）。"
    exit 0
fi

PID=$(cat "$PID_FILE")

if ! kill -0 "$PID" 2>/dev/null; then
    echo "[提示] PID $PID 进程已不存在，清理残留文件。"
    rm -f "$PID_FILE"
    exit 0
fi

echo "正在停止邮件定时发送程序 (PID: $PID)..."
kill "$PID"

# 等待进程退出，最多等 10 秒
for i in $(seq 1 10); do
    if ! kill -0 "$PID" 2>/dev/null; then
        echo "[成功] 程序已停止。"
        rm -f "$PID_FILE"
        exit 0
    fi
    sleep 1
done

# 超时则强制终止
echo "[警告] 进程未响应，强制终止..."
kill -9 "$PID" 2>/dev/null
rm -f "$PID_FILE"
echo "[成功] 程序已强制终止。"
