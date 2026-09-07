#!/usr/bin/env bash
# Linux/macOS 一键启动。按优先级选择 Python:
#   1) 环境变量 PYTHON(显式指定,最稳)
#   2) 已激活的 conda 环境(CONDA_PREFIX,适配 AutoDL)
#   3) 项目内 .venv(普通 venv 部署)
#   4) 系统 python3
# 默认监听 127.0.0.1:8000;要对外访问,启动前设 HOST=0.0.0.0(或写进 .env)
set -e
cd "$(dirname "$0")"

PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  if [ -n "$CONDA_PREFIX" ] && [ -x "$CONDA_PREFIX/bin/python" ]; then
    PY="$CONDA_PREFIX/bin/python"
  elif [ -x ".venv/bin/python" ]; then
    PY=".venv/bin/python"
  else
    PY="python3"
  fi
fi

# 启动前轻量校验核心依赖,缺了就给出明确指引
if ! "$PY" -c "import fastapi, uvicorn" >/dev/null 2>&1; then
  echo "[run.sh] 当前 Python 缺少依赖，可能没激活 conda 环境或没装包。请先执行："
  echo "  conda activate myagent"
  echo "  pip install -r requirements.txt"
  echo "  ./run.sh"
  echo "（或直接指定解释器: PYTHON=/root/miniconda3/envs/myagent/bin/python ./run.sh）"
  exit 1
fi

exec "$PY" app.py
