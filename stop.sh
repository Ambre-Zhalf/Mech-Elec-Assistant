#!/usr/bin/env bash
# 一键停止:优雅关闭 -> 未退再强杀 -> 清理 PID 文件。
set -e
cd "$(dirname "$0")"
PID_FILE="app.pid"
PID=""
[ -f "$PID_FILE" ] && PID="$(cat "$PID_FILE")"

if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
  echo "[stop] 正在停止 PID $PID ..."
  kill -TERM "$PID" 2>/dev/null || true
  sleep 3
  if kill -0 "$PID" 2>/dev/null; then
    echo "[stop] 未退出,强杀 ..."
    kill -9 "$PID" 2>/dev/null || true
  fi
else
  echo "[stop] 未发现运行中的服务"
fi
rm -f "$PID_FILE"

pkill -9 -f "python app.py" 2>/dev/null || true

PORT="$(grep -E '^PORT=' .env 2>/dev/null | tail -1 | cut -d= -f2 | tr -d ' ')"
PORT="${PORT:-8000}"
echo "[stop] 已停止(端口 $PORT 应不再响应)"