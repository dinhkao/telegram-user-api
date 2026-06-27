#!/bin/bash
# start_srv.sh — Start telegram-user-api server on port 8090
# 
# IMPORTANT: Run this from a REAL Terminal app, NOT from CodeWhale.
# CodeWhale's sandbox blocks writes to ~/Library, ~/Documents/final_telegram,
# and /opt/homebrew — which breaks both the shared SQLite DB and Playwright Chromium.
#
# Usage:
#   cd ~/Documents/telegram-user-api
#   ./start_srv.sh

set -e
cd "$(dirname "$0")"
source .env
export PORT=8090
exec .venv/bin/python -u server.py
