#!/bin/bash
# start_all.sh — Start all 3 apps with auto-restart on disconnect/crash.
# Run: ./start_all.sh
# Stop: Ctrl+C (kills all child processes)

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BOT_DON_HANG="/Users/duydinh0225/Documents/bot-don-hang"
FINAL_TELEGRAM="/Users/duydinh0225/Documents/final_telegram"
TUA_VENV="$SCRIPT_DIR/.venv/bin/python"
BOT_VENV="$BOT_DON_HANG/.venv/bin/python"

# Environment
export PYTHONPATH="$BOT_DON_HANG:$SCRIPT_DIR"
export PORT=3000

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m'

cleanup() {
    echo -e "\n${YELLOW}Shutting down all apps...${NC}"
    kill $PID_SERVER $PID_NODE $PID_BOT 2>/dev/null
    wait $PID_SERVER $PID_NODE $PID_BOT 2>/dev/null
    echo -e "${GREEN}All stopped.${NC}"
    exit 0
}
trap cleanup SIGINT SIGTERM

restart_app() {
    local name="$1"
    local pid_var="$2"
    shift 2
    local cmd=("$@")

    # Kill old process if still alive
    local old_pid="${!pid_var}"
    if [ -n "$old_pid" ] && kill -0 "$old_pid" 2>/dev/null; then
        kill "$old_pid" 2>/dev/null
        wait "$old_pid" 2>/dev/null
    fi

    echo -e "${CYAN}[$(date +%H:%M:%S)] Starting $name...${NC}"
    "${cmd[@]}" &
    local new_pid=$!
    eval "$pid_var=$new_pid"
    echo -e "${GREEN}[$(date +%H:%M:%S)] $name started (PID: $new_pid)${NC}"
}

# ─── Start all apps ──────────────────────────────────────────────────

PID_SERVER=""
PID_NODE=""
PID_BOT=""

# 1. Python server.py (port 8090)
restart_app "server.py:8090" PID_SERVER \
    "$TUA_VENV" "$BOT_DON_HANG/server.py"

# 2. Node.js final_telegram (port 3000)
restart_app "final_telegram:3000" PID_NODE \
    node "$FINAL_TELEGRAM/app.js"

# 3. Python bot (port 3002)
restart_app "bot.main:3002" PID_BOT \
    "$BOT_VENV" -m bot_don_hang.main

# ─── Monitor & auto-restart loop ─────────────────────────────────────

RETRY_DELAY=5
MAX_RAPID_RESTARTS=3
RAPID_WINDOW=60

declare -A RESTART_COUNT
declare -A RESTART_SINCE

monitor_and_restart() {
    local name="$1"
    local pid_var="$2"
    shift 2
    local cmd=("$@")

    local pid="${!pid_var}"
    if [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null; then
        # Process died
        local now=$(date +%s)
        local key="$name"
        local since="${RESTART_SINCE[$key]:-0}"
        local count="${RESTART_COUNT[$key]:-0}"

        # Reset rapid restart counter if outside window
        if [ $((now - since)) -gt $RAPID_WINDOW ]; then
            count=0
        fi

        if [ $count -ge $MAX_RAPID_RESTARTS ]; then
            echo -e "${RED}[$(date +%H:%M:%S)] $name crashed $count times in ${RAPID_WINDOW}s — pausing 30s before retry...${NC}"
            sleep 30
            count=0
        fi

        echo -e "${YELLOW}[$(date +%H:%M:%S)] $name died — restarting in ${RETRY_DELAY}s (attempt $((count+1)))...${NC}"
        sleep $RETRY_DELAY
        restart_app "$name" "$pid_var" "${cmd[@]}"

        RESTART_COUNT[$key]=$((count + 1))
        RESTART_SINCE[$key]=$(date +%s)
    fi
}

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
