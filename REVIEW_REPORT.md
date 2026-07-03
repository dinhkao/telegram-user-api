# REVIEW_REPORT.md — Autonomous codebase review (2026-07-03)

Full autonomous review of the `telegram-user-api` codebase (Python aiohttp + Telethon
backend, Vite/Preact/TS webapp). Scanned source only (excluded `node_modules`, build
output, `.venv`, `.git`, `*.session`). Six parallel review agents covered: image
feature, server core/auth, order/payment/money domain, webapp, a security sweep, and
integrations/bot.

## Baseline (before & after)

| Check | Before | After |
|---|---|---|
| pytest (`./scripts/test.sh`) | 85 passed | 85 passed |
| webapp `tsc --noEmit` | clean | clean |
| webapp `vite build` | ok | ok |
| app import smoke (`create_app()`) | ok | ok |

No regressions introduced.

---

## ✅ Fixed (applied, verified)

Priority order: security → crash → logic/race → leak → quality.

### Security
1. **KiotViet client secret hardcoded in source** — `integrations/kiotviet/core.py`.
   Client id + secret were committed as env defaults. Moved both to `.env` (gitignored);
   source now reads env with empty default + warns if unset. **⚠ MANUAL: the old secret
   is in git history and MUST be rotated in KiotViet** (see manual items).
2. **Exception detail leaked to callers** — `tg_api/send_file_handler.py:88`. The catch-all
   returned `type(e).__name__: e` to the client; now returns a generic `"send failed"`
   (full detail still logged server-side).

### Crash bugs
3. **`get_order_history` leaked its DB connection on the query-error path** —
   `server_app/order_history.py`. `except: return []` skipped `conn.close()` (fd leak that
   accumulates). Restructured into `try/finally: conn.close()`.
4. **Debt report 500'd on one bad order** — `api_helpers/payment_core.py:get_all_debts`.
   `compute_debt()` ran outside the `try` guarding `json.loads`, so a single malformed
   order crashed the whole report. Moved inside the try; bad rows are skipped.
5. **`tag_parts` crashed on float money values** — `renderers/order_parts.py`. `str(abs(n))[:-3]`
   → `int("")` ValueError when a value was a float `< 10` (e.g. `5.0`), and mis-stripped
   thousands for any float. Coerce `int(n or 0)` before slicing.
6. **`invoice-update` 500'd after a successful save** — `server_app/order_api_mutations.py:95`.
   `len(invoice)` crashed when the (optional) `invoice` body field was `None`. → `len(invoice or [])`.
7. **Order-list white screen** — `webapp/src/pages/OrdersList.tsx`. `setOrders(data.orders)`
   with no guard → `undefined` state → `.map` throws if a response/cache lacks `orders`.
   → `data.orders || []`.

### Logic / race
8. **Payment-id collision after delete** — `api_helpers/payment_core.py:add_payment`.
   Id used `len(payments)` which is reused after a delete; a same-second collision let
   `delete_payment_record` remove two records. → uuid-suffixed id.
9. **Duplicate image import (check-then-insert race)** — `order_images_store/images.py`.
   Added `UNIQUE(thread_id, tg_message_id)` index + `INSERT OR IGNORE` returning the
   existing row on conflict (NULLs stay distinct, so multiple pre-forward web uploads are fine).
10. **`delete_order` not atomic** — `order_store/orders.py`. Bare `conn.commit()` read-modify-write
    could clobber a concurrent writer; wrapped in `with transaction(conn)` per the repo invariant.
11. **`InvoiceEditor` wiped unsaved edits on background reload** — `webapp/src/detail/InvoiceEditor.tsx`.
    The `[invoice]` effect re-seeded rows on every realtime `reload()` (new array identity),
    discarding mid-edit changes. Now re-seeds only when the invoice *content* actually changed.
12. **`offline.ts` flushQueue clobbered concurrently-queued POSTs** — a POST queued during the
    flush was overwritten on writeback. Now merges items appended during the flush.
13. **Realtime stale-socket → duplicate connection** — `webapp/src/realtime.ts`. `onclose`
    unconditionally nulled the current `ws`; a late close of an old socket spawned a second
    connection. Guarded to only null if it's the current socket. Also reset `everConnected`
    in `stopRealtime` (logout→login no longer fires a spurious `resync`).

### Leaks (timers / listeners / fs)
14. **`CustomerPicker`** debounce timeout never cleared → setState after unmount. Added cleanup.
15. **`OrdersList.flashOrder`** 5s timers never cancelled. Tracked + cleared on unmount.
16. **`OrderDetail`**: `saveText` 1.5s timer and the deep-link focus flash timeout were not
    cleared on unmount. Both tracked + cleared.
17. **`image_routes._safe_path` did a filesystem `makedirs` on the read/serve path** — every
    thumbnail GET (and any arbitrary thread-id in a URL) created an empty dir. Split
    path-safety (pure) from dir creation (write path only).
18. **`order_photo_sync` self-sent cache evicted arbitrary (not FIFO) members** — could drop
    ids still inside the 2s dedup window. Switched to set + deque FIFO eviction.

### Quality
19. **Unstable React keys** — `History.tsx` and `Comments.tsx` used array index while lists are
    reordered/prepended (wrong node/anchor reuse, stale thumbnail). Keyed by stable fields.

---

## 🔍 Identified — NOT auto-fixed (manual review / decision needed)

These are real but were left for you because fixing them changes security posture or
behavior on the LIVE system, or needs a judgement call. Least-invasive fix noted.

### Security posture (require config + coordination — Tailscale-mitigated today)
- **ROTATE the KiotViet secret.** It's in git history; moving it to `.env` stops *future*
  source exposure but the leaked value is still recoverable from history. Rotate in KiotViet,
  put the new value in `.env`.
- **`tg_api/common.py` fails OPEN when `TG_EDIT_API_KEY` is unset** — `/api/tg/send-file` &
  `/api/tg/edit` (run as the user's Telegram account) accept unauthenticated requests. Fix:
  set `TG_EDIT_API_KEY` **and** `USER_API_KEY` (bot side) to the same random value in `.env`,
  then change `check_auth` to fail closed (`return bool(_API_KEY) and header == _API_KEY`).
  Not auto-applied to avoid breaking the bot's photo-forward if the keys aren't set atomically.
- **`WEB_AUTH_ENABLED` defaults false** — all `/api/*` (orders, customer PII, debt, mutations)
  are unauthenticated by default; safe only because deployment is Tailscale/LAN-only. Enable it
  (users must log in / carry tokens) before any exposure beyond Tailscale.
- **`order_api_invoice.py:63` invoice-delete admin gate falls back to `body["user_id"]`** — with
  WEB_AUTH off, an attacker can pass `{"user_id":"duy"}` to satisfy the admin check. Real fix is
  deriving the actor only from the verified token — but that disables web-delete while WEB_AUTH is
  off, so it's coupled to enabling WEB_AUTH.
- **`web_auth` loopback exemption by source IP** — if a reverse proxy is ever placed in front,
  all requests look like loopback and bypass auth. Gate the bot on a shared header/secret instead.
- **Login has no rate-limit/lockout** (only a 0.5s delay) on short numeric PINs. Add per-IP/account
  throttling. (PIN hashing itself is sound: pbkdf2-sha256 + constant-time compare.)

### Logic / data-integrity (safe to fix, deferred for scope)
- **`order_store/customers.py`**: `add_customer` derives `firebase_key` from the lowercased name
  → two customers with the same name collide and `ON CONFLICT DO UPDATE` overwrites the first
  (data loss). And `touch_customer_last_order` does a full-blob SELECT→UPDATE while
  `update_customer_debt` uses atomic `json_set` on the same row → a concurrent touch can wipe a
  just-set debt. Fix: unique-suffix the key; use `json_set` for `last_order_at`.
- **`product_store/profit.py:30`**: `total_profit` drops `fee_total` entirely when `total_cost==0`,
  so orders with no known item costs report profit 0 even when VAT/ship/discount fees apply.
- **Parsers** (`order_store/comma_parser.py:72`, `order_store/free_text.py:35`): decimal prices
  (`12.5`) raise and get demoted into the note; the `tb` branch yields float quantities unlike the
  int-producing `t`/`b` branches. Add tests + parse accordingly (these are characterized by
  `tests/test_parsers.py` — extend it).
- **`production_store/queries.py:63` & `bang_gia_store/queries.py:41`**: read-modify-write
  (get→upsert / set_price) without a transaction → lost update under concurrency. Wrap in one txn.
- **`bang_gia_store` set_price** stores price unvalidated (may be a str) → later `int(price)` can crash.
- **`OrdersList` realtime splice** keeps a row that no longer matches the active filter chip until
  the next full refetch (e.g. an order that became "done" lingers under "Chưa xong").
- **`CreateOrder.tsx`**: advanced flow creates the order then updates the invoice; if the 2nd call
  throws, an orphan order exists with no navigation to it. Navigate to `#/order/<id>` even on failure.
- **`InvoiceTable` `total` prop** is accepted but unused → the dashboard card's server total and the
  table's recomputed total can disagree for the same order.

### Integrations / bot (from the integrations reviewer)
- **KiotViet HTTP calls are synchronous (`urllib`) inside async handlers** — they block the event
  loop during each POS request. Wrap in `run_in_executor`/`asyncio.to_thread`.
- **Playwright html→png**: cross-thread usage + temp-PNG files not always cleaned up on error paths.

### Confirmed NOT vulnerable (checked)
Path traversal (both file handlers normpath+prefix-check; filenames are uuid + whitelisted ext),
SQL injection (all queries parameterized incl. dynamic `IN (...)`), CORS (strict allowlist),
PIN/token crypto (pbkdf2 + `compare_digest`, 32-byte random secret chmod 600), no pickle/eval/exec/
os.system on untrusted input, no user-controlled outbound URLs (no SSRF), no secrets in logs,
webapp object-URLs revoked, no unhandled promise rejections.

---

## How to apply the deferred security hardening (quick)
```bash
# 1) rotate KiotViet secret in the KiotViet portal, then:
#    edit ~/letrang-db-adjacent .env → KIOTVIET_CLIENT_SECRET=<new>
# 2) tg_api auth (one process, one .env → keys match):
python -c "import secrets;print('TG_EDIT_API_KEY=%s'%secrets.token_hex(24))" >> .env
#    copy the same value to USER_API_KEY=<same>, then set check_auth to fail closed.
# 3) enable web auth once all clients carry tokens:  WEB_AUTH_ENABLED=true
```
