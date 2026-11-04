#!/usr/bin/env bash
cd "$(dirname "$0")/.."
[ -f logs/api.pid ] && kill "$(cat logs/api.pid)" 2>/dev/null && sleep 1
setsid nohup .venv/bin/uvicorn src.api:app --host "${API_HOST:-127.0.0.1}" --port "${API_PORT:-8700}" > logs/api.log 2>&1 &
echo $! > logs/api.pid
