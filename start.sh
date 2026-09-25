#!/usr/bin/env bash
# 一键启动:已在运行则提示,否则后台启动。端口从 .env 的 PORT 读取。
set -e
cd "$(dirname "$0")"
PID_FILE="app.pid"
LOG_FILE="app.log"
PORT="$(grep -E '^PORT=' .env 2>/dev/null | tail -1 | cut -d= -f2 | tr -d ' ')"
PORT="${PORT:-8000}"

if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "[start] 已在运行 (PID $(cat "$PID_FILE")),端口 $PORT。重启请先 ./stop.sh"
  exit 0
fi
rm -f "$PID_FILE"

# 端口是否被占用:curl 连得上(退出码0)=有服务在响应;连不上/超时=端口空闲
if curl -s -o /dev/null --max-time 3 "http://127.0.0.1:$PORT/"; then
  echo "[start] 端口 $PORT 已有服务在响应,先 ./stop.sh 或排查"
  exit 1
fi

nohup ./run.sh > "$LOG_FILE" 2>&1 &
echo "$!" > "$PID_FILE"
echo "[start] 已启动 PID $!,端口 $PORT"
sleep 3
tail -n 15 "$LOG_FILE"