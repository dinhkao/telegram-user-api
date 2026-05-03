# telegram-user-api

Python (Telethon + aiohttp) service that runs as a **Telegram user account**
(not a bot). It indexes a #don_hang channel into Postgres, exposes a small
HTTP API for search/inspection, broadcasts new "Saved Messages" via WebSocket,
and provides a `POST /api/tg/edit-message` helper so that other services can
edit Telegram messages **as the user** (bypassing bot edit limits).

It is one half of a two-process system. The other half is the Node.js app
[final_telegram](../final_telegram) which owns the order workflow, UI,
Firebase data, and is the main caller for Telegram bot operations.

---

## 1. Architecture overview

```
                ┌──────────────────────────────────────────────────────┐
                │                     Telegram                          │
                │  (channels, groups, Saved Messages, #don_hang topic) │
                └──────────────────────────────────────────────────────┘
                          ▲                              ▲
                          │ Bot API (HTTPS)              │ MTProto (user account)
                          │                              │
        ┌─────────────────┴────────────┐    ┌────────────┴───────────────────┐
        │ final_telegram (Node.js)     │    │ telegram-user-api (Python)     │
        │ port 3000                    │    │ port 8090 (default 8080 unset) │
        │                              │    │                                │
        │ - Express + node-telegram-   │    │ - Telethon user client         │
        │   bot-api (BOT1, BOT2)       │    │ - aiohttp web server           │
        │ - Firebase Admin             │    │ - Postgres (Supabase) for      │
        │ - Order DB (better-sqlite3,  │    │   #don_hang index              │
        │   Supabase Postgres)         │    │ - WebSocket /ws (Saved Msgs)   │
        │ - Builds order message HTML  │    │ - POST /api/tg/edit-message    │
        │   and edits via Bot API      │    │   (edit as user; not currently │
        │                              │    │   wired into final_telegram)   │
        └──────────────┬───────────────┘    └────────────────────────────────┘
                       │
                       │ HTTP (localhost:3000)
                       ▼
                  /api/update-order-message
                  (rebuilds & edits order main
                   message in channel)
```

### Order main-message update flow (current production path)

1. Something changes for an order (invoice, task status, payment, tag…).
2. The relevant `DonHang` instance in `final_telegram/class/dhClass.js`
   calls `scheduleUpdate()` / `priorityUpdate()` / `updateMainMessage()`.
3. Those methods POST the order JSON to
   `${PUBLIC_URL}/api/update-order-message` on the **same Node process**
   (PUBLIC_URL = `http://localhost:3000`).
4. The route handler in `final_telegram/src/routes/orders-message.js`
   re-renders the message HTML (`buildMessageContent` →
   `buildCompactChannelOrderMessageHtml` → discussion-mirror cleanup) and
   edits the channel message via the Telegram Bot API.
5. On any failure, `priorityUpdate()` falls back to a direct
   `bot1RateLimited.editMessageText`.

`telegram-user-api` is **not** in the hot path for this flow today. Its
`POST /api/tg/edit-message` exists for cases where we want the edit to
appear as performed by the user account (e.g. avoiding bot edit windows or
flood limits), but `final_telegram` does not currently call it.

---

## 2. Repos and processes

| Path                                        | Language / Runtime | Entry point              | Port |
| ------------------------------------------- | ------------------ | ------------------------ | ---- |
| `/Users/duydinh0225/Documents/telegram-user-api` | Python 3, Telethon, aiohttp | `server.py`              | 8090 (env `PORT`) |
| `/Users/duydinh0225/Documents/final_telegram`    | Node.js (ESM), Express, node-telegram-bot-api | `process-manager.js` → `app.js` | 3000 (env `PORT`) |

Both must be running for the order workflow to behave correctly. `final_telegram`
is the most important — without it, no bot messages, no order updates.

---

## 3. Setup

### 3.1 telegram-user-api (this repo)

```bash
cd /Users/duydinh0225/Documents/telegram-user-api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env       # then edit
```

Required env vars (see [.env.example](.env.example)):

- `API_ID`, `API_HASH` — from <https://my.telegram.org/apps>
- `PHONE` — international format, e.g. `+84…`
- `PORT` — HTTP port (default 8090)
- `TARGET_CHAT`, `GROUP_ID` — what to monitor / auto-reply
- `FIREWORKS_API_KEY`, `AI_BACKEND` — optional AI features
- `TG_EDIT_API_KEY` — optional shared secret for `/api/tg/edit-message`
- `SUPABASE_PSQL` (or whatever the indexer uses) — for `donhang_db`/`donhang_indexer`

First run will prompt for the Telegram login code (and 2FA password if set)
and create `user_session.session`.

### 3.2 final_telegram (Node side)

```bash
cd /Users/duydinh0225/Documents/final_telegram
npm install
# .env must include at minimum:
#   BOT1_TOKEN, BOT2_TOKEN
#   PUBLIC_URL=http://localhost:3000
#   FIREBASE_SERVICE_ACCOUNT={...}
#   SUPABASE_PSQL=postgresql://...
```

`PUBLIC_URL` **must** point at the locally running Node app (port 3000).
A stale Railway URL here will break order main-message updates.

---

## 4. Running

### 4.1 Start telegram-user-api

```bash
cd /Users/duydinh0225/Documents/telegram-user-api
./start_srv.sh                                    # foreground
# or:
source .venv/bin/activate && python server.py
```

Successful boot logs:

```
🌐 Web server: http://localhost:8090
```

### 4.2 Start final_telegram

```bash
cd /Users/duydinh0225/Documents/final_telegram
nohup node process-manager.js >/tmp/final-telegram.log 2>&1 &
disown
```

Successful boot logs:

```
🌟 Server is listening on port 3000
🌐 Access at: http://localhost:3000
```

### 4.3 Restart final_telegram

```bash
pkill -f "process-manager.js"
sleep 2
cd /Users/duydinh0225/Documents/final_telegram
nohup node process-manager.js >/tmp/final-telegram.log 2>&1 &
disown
```

Verify no order-update errors:

```bash
grep -aE "Priority update|updateMainMessage|update-order-message|404|❌" \
  /tmp/final-telegram.log | tail -20
```

---

## 5. HTTP endpoints (telegram-user-api)

| Method | Path                     | Purpose |
| ------ | ------------------------ | ------- |
| GET    | `/`                      | Static index page |
| GET    | `/ws`                    | WebSocket — live Saved Messages stream |
| GET    | `/api/search`            | Search Saved Messages (server-side + Vietnamese-normalized fallback) |
| GET    | `/api/donhang`           | Indexed #don_hang messages |
| GET    | `/api/donhang/stats`     | Index statistics |
| GET    | `/api/donhang/msg`       | Fetch a specific indexed message |
| GET    | `/donhang`               | Static donhang viewer page |
| GET    | `/static/*`              | Static assets |
| POST   | `/api/tg/edit-message`   | Edit a Telegram message **as the user account** (Telethon `client.edit_message`). Optional `X-API-Key` header if `TG_EDIT_API_KEY` is set. |

Body for `POST /api/tg/edit-message`:

```json
{
  "chat_id": -1002138495144,
  "message_id": 12345,
  "text": "<b>new content</b>",
  "parse_mode": "html",
  "link_preview": false
}
```

---

## 6. Common issues

- **Order main-message not updating** → check `PUBLIC_URL` in
  `final_telegram/.env` is `http://localhost:3000` and that the Node
  process is actually running on 3000. Look for
  `Application not found` 404s in `/tmp/final-telegram.log`; that means
  PUBLIC_URL still points at a dead Railway deployment.
- **Telethon prompts for login on every start** → ensure `user_session.session`
  is present and writable in the project root.
- **WebSocket clients see no messages** → the user account must be a
  member of `TARGET_CHAT` and `GROUP_ID`.

---

## 7. File map (this repo)

```
server.py             aiohttp app, Telethon client, WS broadcast, route registration
listener.py           live message handlers
fetch.py              ad-hoc Telegram fetchers
tg_edit.py            POST /api/tg/edit-message handler
donhang_db.py         Postgres schema + queries for the #don_hang index
donhang_indexer.py    backfill + live indexer for #don_hang
what_data.py          /api/donhang/* handlers
vn.py                 Vietnamese accent normalization (vn_normalize)
start_srv.sh          shell launcher
static/               donhang.html, index.html viewers
```
