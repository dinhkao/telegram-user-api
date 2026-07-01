# Senior review & refactor roadmap

Fresh-eyes review of this app and a **phased, non-breaking** plan to reach its
best version. The guiding rule: this is a live order/money system — **strangle,
don't rewrite**. Grow a spine under working behavior one phase at a time, deleting
a generation of cruft with each step. Every phase must keep behavior identical and
ship under green tests.

Status legend: ✅ done · 🚧 in progress · ⬜ not started.

---

## Findings (why this plan exists)

1. **Data model is a JSON blob, not a schema.** `orders(firebase_key, thread_id,
   …, json TEXT, updated_at, deleted_at)` — the whole order lives in one `json`
   column, mutated via `json_set` or full-blob rewrite (`order_store/serialization.py`).
   → not queryable, no integrity, and **read-modify-write races** (SELECT blob →
   mutate in Python → UPDATE whole blob) under autocommit connections.
2. **Integration bus = a shared SQLite file with a separate Node process**
   (`~/letrang-db/app.db`) + HTTP back to Node (`_call_final_telegram` → `:3000`)
   + Firebase RTDB as a print queue. Three coupling mechanisms for one system.
3. **Errors swallowed** — ~200 `except Exception: return None/False`. A failed
   payment/order write looks identical to "not found".
4. **No layering.** Telethon handlers reach straight into SQLite + Firebase +
   KiotViet in one function → the heart is untestable, so it was untested.
5. **Cruft as sediment.** Three command-handler generations; root shims; dead
   packages. Nothing deleted, only superseded.

---

## Phase 0 — make it legible ✅ (done)

- ✅ `CLAUDE.md` canonical map.
- ✅ Killed the `exec()`-blob: `order_commands_v3.py` is a real module (was 22
  `.txt` parts).
- ✅ Centralized shared DB paths in `utils/paths.py`.
- ✅ Deleted dead `command_handlers_v3/` facade + repo junk.
- ✅ One-line "what + connects to" docstrings on every package `__init__.py`.

## Phase 1 — put a spine on the data 🚧 (started)

Goal: stop silent data loss; give every mutation one safe place to stand.

- ✅ **Characterization tests** for `order_store` (`tests/test_order_store.py`) —
  lock current behavior of create/get/save/task-status/flags/invoice/soft-delete
  so later phases can't silently regress.
- ✅ **Atomic read-modify-write** — added `order_store.schema.transaction(conn)`
  (`BEGIN IMMEDIATE`, re-entrancy-safe, rolls back on exception; exported from
  `order_store` / `order_db`). Tested for commit, rollback, reentrancy, no leaked
  transaction. Migrated the **synchronous** RMW sites: `set_task_status`,
  `clear_task_status`, `set_order_flag`, `save_order_invoice` (store level) and
  `api_fix_handler`, `api_invoice_update_handler` (aiohttp — async work kept
  outside the lock).
- ✅ **Fixed latent bug**: `_update_order_json_field` with a bare string produced
  `json('Anh Tú')` (malformed JSON) and silently dropped the write — this was
  hitting `$.customer_name` and string customer IDs in `channel_handlers/parse.py`.
  Now `json.dumps` every value. Regression test added.
- ⬜ Remaining RMW sites are the **async money commands** in `order_commands_v3.py`
  (ck/tm/invoice/print) and `command_handlers/order_commands_v2_*`. These `await`
  network IO (KiotViet, Telegram) *between* the read and the save, so they must NOT
  be wrapped in a transaction as-is (that holds a write lock across IO). Correct fix
  = Phase 2: extract the synchronous mutation into a store helper, do the async work
  outside it. Do one command end-to-end as the template, then the rest.
- ⬜ Introduce a typed `Order` model (dataclass/Pydantic) as the ONLY thing new
  handler code touches; serialize to/from the JSON column underneath. One place
  knows an order's shape. Add round-trip tests. Do NOT rewire all handlers at
  once — new/changed code adopts it first.

## Phase 2 — layer it ✅ (core complete; mechanical tail remains)

**Core done:** the model/domain/store pattern is established and copied across the
key domains (task-status, payments, debt, profit), and every core piece of
previously-untested business logic is now locked under tests (85 total). All
*synchronous* order mutations are atomic.

**Remaining (mechanical, do incrementally with live tests — NOT blind):**
- Thin-handler migration of the async commands in `order_commands_v3` (invoice /
  VAT / print / fix — ~8 `_save_order` sites). Each `await`s KiotViet/Telegram
  between read and save, so the mutation must be extracted into a synchronous
  `domain` + transactional store call with the IO left in the handler, then
  live-tested. Low marginal risk-reduction (the shared `task_status` mutation is
  already atomic; single-command races are rare and WAL+busy_timeout serialize
  statements) — hence deferred, not rushed.
- Same for `command_handlers/order_commands_v2_*`.


Three layers, enforced by imports:
- `telegram/handlers` — parse input, format output, NO business logic.
- `domain` — pure functions on the typed `Order`, 100% unit-tested, no IO.
- `stores` + `integrations` — all IO (SQLite, Firebase, KiotViet) behind
  interfaces with fakes.

- ✅ **Reference template** on the task-status command (`soan`/`giao`/`nop`/`nhan`,
  live-verified): `order_store/model.py` (`Order` — lossless typed façade over the
  blob) + `order_store/domain.py` (pure `mark_task`/`clear_task`/`all_steps_done`)
  + `order_store/tasks.py` (transaction + IO only). Behavior identical (guarded by
  `tests/test_order_store.py`); pure rules unit-tested in `tests/test_order_domain.py`
  with zero IO. This is the pattern to copy.
- ✅ **Payments (`ck`/`tm`)** templatized: the order-blob mutation already flows
  through the refactored atomic `set_task_status` (via `_auto_complete_tasks_core`);
  the payment row is a separate table (`add_payment`). Extracted the pure decision
  logic (`payment_store/domain.py`: `method_params`, `resolve_payment_target`,
  `build_payment_record`) out of `_process_payment_core` and unit-tested it
  (`tests/test_payment_domain.py`) — no KiotViet/DB needed. Orchestration
  unchanged.
- ⬜ Migrate the remaining commands (invoice/print/fix and `order_commands_v2_*`)
  to the same shape: pure rule in a `domain` module + transactional store call +
  IO in the handler outside the lock.
- ✅ **Parsers characterized** — `tests/test_parsers.py` locks the core Vietnamese
  order parsing (`_parse_qc`, `_parse_no_qc`, `parse_comma_text`,
  `parse_invoice_free_text`) that was previously untested. Pure (no DB): uses the
  `_all_products` injection seam / `kh_id=None`. Documents the rules (t=thùng ×50
  default, KDXDB special 5, DM180 lốc→12/b, trailing `tao hd` stripped).
- ✅ **Money calcs characterized**: extracted pure `compute_debt` to
  `payment_store/domain.py` (single source for `calculate_debt` + `get_all_debts`,
  was duplicated) and characterized `calculate_order_profit`
  (`tests/test_payment_domain.py`, `tests/test_profit.py`). Revenue/cost/profit +
  VAT/PVC/discount fees now locked.
- ⬜ Grow `Order` typed accessors as fields get touched; keep it lossless until
  Phase 3 promotes fields to columns.

## Phase 3 — promote hot fields out of the blob ✅ (mostly pre-existing)

**Finding (2026-07-01): the prod `orders` table is already substantially
denormalized/indexed** — this phase was largely done before the review:
- generated column `nop_nhan_done` + partial composite index
  `(nop_nhan_done, order_created) WHERE deleted_at IS NULL`
- indexes on `thread_id`, `message_id`, `updated_at`, `json_extract('$.created')`
- a full-text `orders_fts` table and a denormalized `tasks` table

So point lookups and the common status/date filters are already indexed. The one
NOT covered is **debt/`remaining`**: payments live inside the JSON blob
(`order["payments"]`, no payments table), so a `remaining` column would need to
sum a JSON array — not a plain generated column. Maintaining it requires either a
trigger or a change to the **write path**, which the Node app shares → that work
belongs to Phase 4, not here. No safe, high-value Phase-3 change remains in the
Python repo alone.

## Phase 4 — cut the Node cord ⬜ (blocked: out-of-scope repo + live data)

Replace shared-SQLite + HTTP-to-`:3000` with this process owning the data and
exposing one API. Move the hardcoded Firebase cred paths
(`bot_core/firebase_rtdb.py`, `integrations/firebase_sync/core.py`) to env. Retire
`final_telegram`. This was the stated long-term goal; layering makes it reachable.

**Cannot be done from this repo/session:** it requires editing the Node
`final_telegram` repo (out of scope — Python-only rule) and re-owning a live
production data path. Needs its own project with staged cutover + backups. The
Phase 1–2 layering done here is the prerequisite that makes it *possible* later.

---

## Greenfield target (aim, not a jump)

Only relevant as the north star Phases 1–4 converge on:
- Python + Telethon (async fits); typed end-to-end.
- **Postgres**, real tables (`orders`/`order_items`/`payments`/`customers`), FKs;
  JSONB only for genuinely unstructured extras.
- Hexagonal: pure domain core ← application services ← adapters (Telegram,
  KiotViet, printer, DB). One process owns state.
- KiotViet/printing behind interfaces with fakes → full order flow tested with
  zero external calls.
- Structured logging; no bare excepts — errors handled or surfaced, not
  `None`-sentineled.

## Why not rewrite from scratch

The domain logic (KiotViet quirks, Vietnamese parsing, print pipeline, tax edge
cases) is hard-won and undocumented. A big-bang rewrite would relearn it by
reintroducing every bug, on a system that moves real money. The strangler path
above delivers the same end state with a working app at every commit.
