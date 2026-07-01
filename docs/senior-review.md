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
  (`BEGIN IMMEDIATE`, re-entrancy-safe, rolls back on exception) and wrapped the
  highest-traffic chokepoint mutations `set_task_status` / `clear_task_status`
  (the soan/giao/nop/nhan flow). Tested for commit, rollback, reentrancy, no
  leaked transaction.
- ⬜ Wrap the remaining ~23 RMW call sites (every `get_order_by_thread_id` →
  mutate → `_save_order` pair — grep `_save_order`). Do a few per PR, each under
  the characterization tests. Candidates: `order_store/orders.py`,
  `order_commands_v3.py`, `command_handlers/order_commands_v2_*`,
  `server_app/order_api_*`.
- ⬜ **Fix latent bug** documented by `test_update_json_field_bare_string_is_broken`:
  `_update_order_json_field(conn, tid, path, "somestring")` produces `json('somestring')`
  = malformed JSON and silently returns False. Make it JSON-encode scalar strings
  too (`json.dumps(value)` for any non-pre-encoded value). Then flip that test.
- ⬜ Introduce a typed `Order` model (dataclass/Pydantic) as the ONLY thing new
  handler code touches; serialize to/from the JSON column underneath. One place
  knows an order's shape. Add round-trip tests. Do NOT rewire all handlers at
  once — new/changed code adopts it first.

## Phase 2 — layer it ⬜

Three layers, enforced by imports:
- `telegram/handlers` — parse input, format output, NO business logic.
- `domain` — pure functions on the typed `Order`, 100% unit-tested, no IO.
- `stores` + `integrations` — all IO (SQLite, Firebase, KiotViet) behind
  interfaces with fakes.

Handlers become thin; the heart becomes testable without a live Telegram client.
Migrate one command end-to-end as the reference implementation, then the rest.

## Phase 3 — promote hot fields out of the blob ⬜

Move the columns you actually query (status, customer_id, amount_due, timestamps)
into real typed columns + indices (there are already two GENERATED virtual columns
— `nop_nhan_done`, `order_created` — proving the need). JSON stays for the long
tail. "Unpaid > 30 days" becomes a `WHERE`, not a full-table Python scan.

## Phase 4 — cut the Node cord ⬜

Replace shared-SQLite + HTTP-to-`:3000` with this process owning the data and
exposing one API. Move the hardcoded Firebase cred paths
(`bot_core/firebase_rtdb.py`, `integrations/firebase_sync/core.py`) to env. Retire
`final_telegram`. This was the stated long-term goal; layering makes it reachable.

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
