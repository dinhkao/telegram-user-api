# Restart telegram-user-api

## Quick restart

```bash
cd /Users/duydinh0225/Documents/telegram-user-api

# Kill existing server
pkill -f "server.py"

# Wait a moment for port 8090 to free up
sleep 1

# Start
source .env 2>/dev/null
exec .venv/bin/python server.py
```

Or as a one-liner:

```bash
pkill -f "server.py" && sleep 1 && cd /Users/duydinh0225/Documents/telegram-user-api && source .env 2>/dev/null && exec .venv/bin/python server.py
```

## What runs on which port

| App | Port | Script |
|-----|------|--------|
| **telegram-user-api** (this app) | 8090 | `server.py` |
| final_telegram (Node.js) | 3000 | `~/Documents/final_telegram/app.js` |
| bot-don-hang (Python bot) | 3002 | `bot_don_hang.main` |

## Verify it's running

```bash
# Check port 8090
lsof -i :8090 -P -n

# Check logs in real-time
tail -f server.log
```

## Handlers registered on startup

- `what_data` — chat `-1002124542200`
- `gtr` — chat `-1002124542200`
- `order_commands` (v1) — chat `-1002124542200` (soan, giao, ban, nop, nhan, clear)
- `order_commands_v2` — chat `-1002124542200`
- `order_commands_v3` — chat `-1002124542200` (comma, tao hd, fix/fixapp, print, payments)
- `newkh` — chat `-1002437761799`
- `khachhang_commands` — chat `-1002437761799`
- `product_commands` — chat `-1002124542200`
- `chat_logger` — chat `-1002124542200`
- `channel_handler` — monitors `CHANNEL_DON_HANG_MOI` for new orders
- `firebase_sync` — Firebase RTDB
- `html_to_png` — Playwright browser for rendering HTML to PNG

## Common issues

- **Port 8090 already in use** — an old `server.py` process is still alive. Kill it: `pkill -f "server.py"`
- **Telegram session expired** — re-login may be needed. Check `bot_session.session` exists.
