#!/bin/bash
# restart_8090.command — Double-click to restart the Telethon 8090 app
# Also runnable from Terminal: ./restart_8090.command
# Location: ~/Documents/telegram-user-api/restart_8090.command

set -e

cd "$(dirname "$0")"

# Guard: code + live DB/media live on the samwinchester SSD (via symlinks
# ~/kiemkhach-code/telegram-user-api and ~/letrang-db). Refuse to start if the
# drive isn't mounted — otherwise the app can't open app.db / media.
if [ ! -d /Volumes/samwinchester/letrang ]; then
  echo "ERROR: samwinchester SSD not mounted (/Volumes/samwinchester/letrang missing)."
  echo "Mount the drive, then retry."
  exit 1
fi

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}   Telethon 8090 — Restart${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# ── Close other Terminal windows of this app ──
echo -e "\n${YELLOW}Closing other Terminal windows...${NC}"
osascript -e '
tell application "Terminal"
    repeat with w in (every window whose name contains "restart_8090" or name contains "server.py" or name contains "telegram-user-api")
        if not (id of w is id of front window) then
            close w
        end if
    end repeat
end tell' 2>/dev/null
echo -e "${GREEN}  ✓ Other windows closed${NC}"

# ── Kill existing ──
echo -e "\n${YELLOW}[1/4] Killing existing server.py...${NC}"
pkill -f "server.py" 2>/dev/null && echo -e "${GREEN}  ✓ Old process killed${NC}" || echo -e "${GREEN}  ✓ No existing process${NC}"
sleep 1

# ── Verify port is free ──
echo -e "\n${YELLOW}[2/4] Checking port 8090...${NC}"
if lsof -i :8090 -sTCP:LISTEN 2>/dev/null | grep -q LISTEN; then
    echo -e "${RED}  ✗ Port 8090 still in use — waiting...${NC}"
    sleep 3
    if lsof -i :8090 -sTCP:LISTEN 2>/dev/null | grep -q LISTEN; then
        echo -e "${RED}  ✗ Port 8090 STILL in use. Aborting.${NC}"
        echo -e "\nPress Enter to close..."
        read
        exit 1
    fi
fi
echo -e "${GREEN}  ✓ Port 8090 is free${NC}"

# ── Start server ──
echo -e "\n${YELLOW}[3/4] Starting server...${NC}"
nohup .venv/bin/python -u server.py &
PID=$!
echo -e "${GREEN}  ✓ Server started (PID: $PID)${NC}"

# ── Wait for it to be ready ──
echo -e "\n${CYAN}[4/4] Waiting for server to be ready...${NC}"
for i in {1..10}; do
    sleep 1
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:8090/ 2>/dev/null | grep -qE '^(200|404)'; then
        echo -e "${GREEN}  ✓ Server is responding on http://localhost:8090${NC}"
        break
    fi
    echo -n "."
done

echo -e "\n${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}   Done! Server running in background.${NC}"
echo -e "${GREEN}   Logs: tail -f logs/server.log${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "\nPress Enter to close this window..."
read
