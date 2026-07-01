# CLAUDE.md — telegram-user-api

Guide for AI agents working in this repo. Read this first. Keep it accurate: when
you change architecture, entry points, or the package layout, update this file in
the same change.

---

## 1. What this is

A **Python (Telethon + aiohttp)** service that logs into Telegram as a **user
account** (not a bot) and runs the order-management workflow for a wholesale candy
business ("Lê Trang Phát"). Everything — receiving orders, picking, delivery,
invoicing (KiotViet), collecting payment, printing — happens inside Telegram
channels/forum-topics and is driven by this process.

It is the **Python half** of a two-repo system. The other half is the Node.js repo
`final_telegram` (a sibling directory, out of this repo). The long-term goal is to
port everything to Python and retire the Node app.

**Scope rule for agents:** work only in this Python repo. Do **not** edit or "fix"
the sibling `final_telegram` (Node.js) repo. If a bug traces there, report it — do
not touch it.

**Language:** the business/users are Vietnamese. User-facing strings, command
names, and many docs are Vietnamese. Keep them Vietnamese. Talk to the user in
Vietnamese when they write Vietnamese.

---

## 2. Entry point & how to run

- **`server.py`** is the only entry point. It is a thin shim → real startup is
  **`server_app/bootstrap.py::main()`**. Read `bootstrap.py` to see everything the
  process starts, in order — it is the source of truth for wiring.
- **`server_app/config.py`** is the source of truth for env vars / config
  constants. Read it before assuming a setting exists.

Run:
```bash
.venv/bin/python server.py        # single process, serves on PORT (default 8090)
```
`start_all.sh` / `scripts/` also boot the sibling Node app + others for the full
system; for Python work you usually only need `server.py`.

---

## 3. Architecture — ONE process, ONE user client, three roles

`bootstrap.main()` creates a **single** Telethon `TelegramClient` (the user account)
and mounts three formerly-separate apps onto it. There is no longer a separate
`bot-don-hang` process — it was merged in. Do not assume multiple processes.

```
server.py → server_app.bootstrap.main()
  ├─ aiohttp web server (REST + WebSocket) ....... server_app/ (port 8090)
  ├─ command handlers on the user client ......... command_handlers/, order_commands_v3.py
  ├─ #don_hang channel indexer (live + backfill) . donhang_indexer_pkg/ → donhang_store/
  ├─ bot role (merged bot-don-hang) .............. server_app/bot_bootstrap.py + bot_core/, bot_flows/, bot_handlers/
  └─ Google Sheets bot (ported) .................. sheets_bot/   (no-op unless sheets creds set)
```

### Data stores it talks to
| Store | What | Path / config |
|---|---|---|
| **SQLite `app.db`** (shared) | Orders/customers/notes/quỹ — shared with the Node app | `SHARED_DB_PATH`, default `~/letrang-db/app.db` |
| **SQLite `donhang.db`** (local) | Index of the `#don_hang` channel | `DONHANG_DB`, default `donhang.db` |
| **Firebase RTDB** | Sync + print queue (`meta/to_print`, `html-to-png`) | service-account JSON (env / hardcoded path) |
| **KiotViet REST API** | External POS/accounting: invoices, payments, debt | see `integrations/` |
| **SQLite `bot_sessions.db`** | Bot-role session/state | local |

---

## 4. Repo layout — packages (what it does; what it connects to)

Real code lives in **packages** (dirs with `__init__.py`). Grouped by role:

**Web / server core**
- `server_app/` — aiohttp app: bootstrap, routes (orders, search, saved messages,
  websocket, pages), state, AI backend. Wires everything together.
- `utils/` — logging config and shared helpers. Imported everywhere.

**Order workflow (the heart)**
- `command_handlers/` — text commands typed in order/customer forum topics
  (`soan`, `giao`, `nop`, product/customer/note/quỹ/production commands…). Older layer.
- `order_commands_v3.py` (root module, not a shim) — live v3 order commands:
  KiotViet invoice, payment, print, debt, analysis. Registered by
  `server_app/command_bootstrap.py`.
- `channel_handlers/` — reacts to new posts in `#don_hang`: creates topic,
  parses, notifies, renders.
- `donhang_indexer_pkg/` — live + backfill indexing of `#don_hang` → `donhang_store`.

**Data stores (one package per SQLite domain)**
- `donhang_store/` — `#don_hang` index DB (schema, reads, writes, migrations, api).
- `order_store/`, `product_store/`, `payment_store/`, `bang_gia_store/`,
  `note_store/`, `production_store/` — domain tables in the shared `app.db`.
- `chat_log/` — logs new/edited/deleted Telegram messages to DB.
- `audit/` (+ `audit_log.py`) — audit-event DB and redaction.

**Bot role (merged bot-don-hang)**
- `bot_core/` — bot config, DB, keyboards, media, session store, firebase, html→png.
- `bot_flows/` — multi-step wizards (invoice create/edit, payment, nộp phiếu…).
- `bot_handlers/` — bot callbacks, menus, actions, sheets glue.

**Integrations / IO**
- `integrations/` — external systems (KiotViet, firebase_sync, …).
- `telegram/` — Telethon gateway (`TelegramGateway` = rate-limit-safe send/edit
  wrapper, edit-state, flood-wait handling). Self-contained.
- `tg_api/` — aiohttp HTTP endpoints wrapping Telegram edit/send-file ops, API-key
  auth. Lets other services edit/send as the user.
- `api_helpers/` — fetch/payment core helpers.
- `renderers/`, `printouts/`, `frontend/` — HTML/PNG rendering, print output,
  static/Next.js frontend served/pushed over WebSocket.
- `sheets_bot/` — Google Sheets bot (runs on the user client; no-op without creds).

**Tooling**
- `scripts/`, `tools/`, `tests/`, `docs/` — startup scripts, dev tools, tests, docs.

> If you add a package, add a one-line entry here.

---

## 5. Root-level `.py` files are SHIMS — do not put logic there

Most top-level `.py` files (e.g. `what_data.py`, `order_commands.py`,
`channel_handler.py`, `donhang_db.py`, `telegram_gateway.py`, `fetch.py`, …) are
**thin backward-compat shims** that just re-export from a package:

```python
# what_data.py
from command_handlers.what_data import register_what_data_handler
```

Rules:
- **Never add real logic to a root shim.** Edit the package module it points to.
- To find where a name really lives, follow the import in the shim.
- Real entry point is `server.py` → `server_app/bootstrap.py`. Everything else at
  root is a shim or a stray script.

**Exceptions — a few root `.py` still hold real logic** (not yet moved to a package):
`customer_notify.py` (payment notifications to customer topics), `mirror_channel.py`
(mirrors orders to a mirror channel), `nop_tien_reminder.py` (background timer:
nags when delivery done but payment not), and **`order_commands_v3.py`** — a real
~1900-line module holding the KiotViet invoice/print/payment/debt/analysis handlers
(`register_order_commands_v3`, `_auto_parse_fix`, `_process_payment_core`,
`_refresh_order_message`). It used to be an `exec()`'d blob of 22 `.txt` parts — now
a normal module. It is the **live** v3 implementation, registered by
`server_app/command_bootstrap.py`. `fetch.py` / `listener.py` are shim + `__main__`
runners.

---

## 6. Conventions

- **One feature = one file.** Split modules by responsibility, not by line count.
  Do not impose an arbitrary line cap; do not merge unrelated features to save files.
- **Every module should say what it does and what it connects to.** Start each
  module with a one-line docstring: what this file does + which package(s)/store(s)
  it talks to. Packages: put the summary in `__init__.py`.
- **Config via env.** Shared DB paths live in **`utils/paths.py`** (single source:
  `SHARED_DB_PATH`, `DONHANG_DB_PATH`) — import from there, never re-derive
  `os.path.expanduser(os.getenv("SHARED_DB_PATH", ...))` inline. Other env/config
  reads go through `server_app/config.py` (or a package's own `config.py`). Don't
  hardcode new secrets/paths — add an env var with a default.
- **Telegram sends/edits go through the gateway** (`TelegramGateway`) so flood-wait
  / rate limits are handled — don't call `client.edit_message` raw in hot paths.
- **Order mutations are read-modify-write on a JSON blob.** Orders live as one
  `json` column; a mutation is `get_order_by_thread_id → mutate dict → _save_order`.
  Wrap that sequence in `with transaction(conn):` (`order_store.schema`) so it's
  atomic — otherwise concurrent writers lose updates. `set_task_status` /
  `clear_task_status` already do; new mutation sites should too. See
  `docs/senior-review.md` for the phased plan to replace the blob with a typed model.
- **Run the tests with `./scripts/test.sh`** (wraps pytest; auto-installs dev deps
  from `requirements-dev.txt` on first run). 46 tests. Run before/after touching
  `order_store` — `tests/test_order_store.py` characterizes the order heart.
  Filter: `./scripts/test.sh -k task_status`.

---

## 7. Portability / cleanup debt (known)

These hurt "portable" and "organized"; fix opportunistically, ask before deleting
tracked files:

- **Hardcoded home paths** as defaults. `SHARED_DB_PATH` is now centralized in
  `utils/paths.py` (was duplicated across ~10 files — done). Still hardcoded:
  Firebase creds → `~/Documents/final_telegram/config/...` and `~/letrang-db/...`
  in `bot_core/firebase_rtdb.py` + `integrations/firebase_sync/core.py`. Move
  these to env / `utils/paths.py` too.
- **Tracked junk** (safe to remove, confirm first): `newfile.txt`, `sample.txt`,
  `test.txt`, `app_nohup.log`, `donhang-kh.db` (0 bytes), `bot_sessions.db-*`
  wal/shm. `*.db`, `*.session`, `.env`, and `*-firebase-adminsdk-*.json` are
  correctly gitignored — do not commit secrets or DBs.
- **Stale docs:** `docs/app-overview.md` still describes 3 separate processes and
  root-level handlers as live code. Reality: single process, packages + shims.
  Trust this file + `bootstrap.py` over older docs.

---

## 8. Fast orientation checklist for a new task

1. `server_app/bootstrap.py` — what starts, in what order.
2. `server_app/config.py` — env/config that exists.
3. Section 4 above — which package owns the thing you're touching.
4. If you landed on a root `.py`, check if it's a shim (section 5) and jump to the
   package.
5. Follow imports; edit the package, not the shim.
