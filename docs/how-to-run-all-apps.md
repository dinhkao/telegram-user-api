# How to run all 3 apps correctly

Three apps form the order management system. Start order matters — ports and dependencies.

---

## Architecture

```
telegram-user-api (Python, port 8090)
  └─ Telegram user session (Telethon)
  └─ Handlers: what_data, gtr, donhang indexer
  └─ WebSocket push to static frontend

final_telegram (Node, port 3000)
  └─ Telegram bots (bot1, bot2)
  └─ Order management logic (dhClass.js, khClass.js)
  └─ SQLite database (data/app.db) — shared with other apps
  └─ HTTP API for tg_edit, tg_send, order/nhan-tien

bot-don-hang (Node, port 3002)
  └─ Product code keyboard / order interaction bot
  └─ Polls Telegram independently (different bot token)
  └─ HTTP API for /api/product-codes
```

---

## Port layout

| App | Port | Purpose |
|---|---|---|
| final_telegram | 3000 | Main bot + HTTP API |
| telegram-user-api | 8090 | Telethon listener + WebSocket |
| bot-don-hang | 3002 | Product codes API |

**Conflict note:** `PORT=8090` is set in the shell environment (`.zshrc` or parent process). This leaks into final_telegram's `app.js` unless explicitly overridden. final_telegram's `process-manager.js` now unsets `PORT` before spawning `app.js`, so `app.js` defaults to 3000.

---

## Startup order

### 1. final_telegram (must start first — owns the shared DB)

```bash
cd ~/Documents/final_telegram
nohup node process-manager.js > /tmp/final_telegram.log 2>&1 &
```

Wait for: `Server is listening on port 3000`

### 2. telegram-user-api

```bash
cd ~/Documents/telegram-user-api
nohup .venv/bin/python server.py > server.log 2>&1 &
```

Wait for: `Web server: http://localhost:8090`

### 3. bot-don-hang

```bash
cd ~/Documents/bot-don-hang
nohup node src/index.js > server.log 2>&1 &
```

Wait for: `Polling started. Waiting for /start <order_id>...`

---

## Verify all apps

```bash
# Port check
lsof -i :3000 -i :8090 -i :3002 | grep LISTEN

# Health checks
curl -s http://localhost:3000/
curl -s http://localhost:8090/
curl -s http://localhost:3002/health

# Process check
ps aux | grep -E "process-manager|server\.py|bot-don-hang.*index" | grep -v grep
```

Expected output:
```
node    ... process-manager.js
node    ... app.js                     # spawned by process-manager
Python  ... server.py                  # telegram-user-api
node    ... src/index.js               # bot-don-hang
```

---

## Common issues

### Port 8090 conflict

If final_telegram's `app.js` grabs port 8090 instead of 3000:
- Check: the shell has `PORT=8090` set. final_telegram's process-manager unsets it, but if you run `app.js` directly it will inherit the shell value.
- Fix: kill `app.js`, start telegram-user-api first, then restart final_telegram. Or run via process-manager only.

### bot-don-hang `[http] Port in use`

The bot tries to start but HTTP server fails. Port 3002 may be occupied by a stale instance.
- Fix: `lsof -ti :3002 | xargs kill -9` then restart.

### Polling 409 conflict

Caused by stale long-poll connections at Telegram's end after a crash.
- Fix: wait 30 seconds for the connection to time out, or run:
  ```bash
  curl "https://api.telegram.org/bot<TOKEN>/getUpdates?timeout=0"
  ```
  This drains any pending updates and releases the connection lock.

### Stale polling lock

If bot-don-hang says "Another instance owns polling lock" but no other instance is running:
```bash
cd ~/Documents/bot-don-hang
node -e "
  const sqlite = require('./src/db/firebase-shim');
  sqlite.database().ref('_runtime/telegram_polling_lock').remove().then(() => process.exit(0));
"
```

### SQLite `app.db` locked

All 3 apps access `~/Documents/final_telegram/data/app.db`. WAL mode prevents most conflicts, but if writes are heavy:
- Check: `lsof | grep app.db` to see which processes have it open
- Kill and restart in order: final_telegram → telegram-user-api → bot-don-hang

---

## Stop all apps

```bash
pkill -f "process-manager\.js"
pkill -f "python.*server\.py"
pkill -f "bot-don-hang.*src/index"
pkill -f "app\.js"    # final_telegram child process
```
