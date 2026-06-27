#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/scripts/start_all_config.sh"
source "$SCRIPT_DIR/scripts/start_all_runtime.sh"

trap cleanup SIGINT SIGTERM

# 1. Python server.py (port 8090)
restart_app "server.py:8090" PID_SERVER \
    "$TUA_VENV" "$BOT_DON_HANG/server.py"

# 2. Node.js final_telegram (port 3000)
restart_app "final_telegram:3000" PID_NODE \
    node "$FINAL_TELEGRAM/app.js"

# 3. Python bot (port 3002)
restart_app "bot.main:3002" PID_BOT \
    "$BOT_VENV" -m bot_don_hang.main

echo -e "${GREEN}=== All apps running. Monitoring... (Ctrl+C to stop) ===${NC}"

while true; do
    sleep 5

    monitor_and_restart "server.py:8090" PID_SERVER \
        "$TUA_VENV" "$BOT_DON_HANG/server.py"

    monitor_and_restart "final_telegram:3000" PID_NODE \
        node "$FINAL_TELEGRAM/app.js"

    monitor_and_restart "bot.main:3002" PID_BOT \
        "$BOT_VENV" -m bot_don_hang.main
done
