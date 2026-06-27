#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BOT_DON_HANG="/Users/duydinh0225/Documents/bot-don-hang"
FINAL_TELEGRAM="/Users/duydinh0225/Documents/final_telegram"
TUA_VENV="$SCRIPT_DIR/.venv/bin/python"
BOT_VENV="$BOT_DON_HANG/.venv/bin/python"

export PYTHONPATH="$BOT_DON_HANG:$SCRIPT_DIR"
export PORT=3000

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m'

RETRY_DELAY=5
MAX_RAPID_RESTARTS=3
RAPID_WINDOW=60

