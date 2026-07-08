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

## 3. Architecture — ONE process, TWO Telethon clients, three roles

`bootstrap.main()` runs everything in a **single process** and creates a Telethon
`TelegramClient` for the **user account** that hosts the web server, command
handlers, and #don_hang indexer. There is no longer a separate `bot-don-hang`
process — it was merged in — but it still uses its **own second client**: the merged
bot role (`bot_bootstrap.start_bot`) starts a **distinct `TelegramClient("bot_session")`
with `BOT_TOKEN`** (a real bot account). So: one process, **two clients**. The bot
can't post as the user or attach inline keyboards to user-account messages, so its
order-topic sends go through the user client's REST (`/api/tg/send-file`) and
production inline buttons go via the bot client (`get_bot_client`). Do not assume the
bot role shares the user client.

```
server.py → server_app.bootstrap.main()
  ├─ aiohttp web server (REST + realtime /ws) .... server_app/ (port 8090)
  ├─ command handlers on the user client ......... command_handlers/, order_commands_v3.py
  ├─ #don_hang channel indexer (live + backfill) . donhang_indexer_pkg/ → donhang_store/
  ├─ bot role (merged bot-don-hang) .............. server_app/bot_bootstrap.py + bot_core/, bot_flows/, bot_handlers/
  └─ Google Sheets bot (ported) .................. sheets_bot/   (DISABLED by default; SHEETS_BOT_ENABLED=true to enable)
```

### Data stores it talks to
| Store | What | Path / config |
|---|---|---|
| **SQLite `app.db`** (shared) | Orders/customers/notes/quỹ. Was shared with the (now-retired) Node app; Python is the sole writer | `SHARED_DB_PATH`, default `~/letrang-db/app.db`. Connections via `utils/db.py` |
| **SQLite `donhang.db`** (local) | Index of the `#don_hang` channel | `DONHANG_DB`, default `donhang.db` |
| **Firebase RTDB** | Sync + print queue (`meta/to_print`, `html-to-png`) | service-account JSON (env / hardcoded path) |
| **KiotViet REST API** | External POS/accounting: invoices, payments, debt | see `integrations/` |
| **SQLite `bot_sessions.db`** | Bot-role session/state | local |
| **Order image files** (disk) | Photos attached to an order (full + thumbnail), one dir per thread_id. Metadata row in `order_images` table (app.db) | `ORDER_MEDIA_DIR`, default `~/letrang-db/media`. Via `order_images_store/` + `server_app/image_routes.py` |

---

## 4. Repo layout — packages (what it does; what it connects to)

Real code lives in **packages** (dirs with `__init__.py`). Grouped by role:

**Web / server core**
- `server_app/` — aiohttp app: bootstrap, routes (orders, customers, comments,
  create-order, pages), state, `/ws` realtime channel. Wires everything together.
  `server_app/web_auth/` — per-user login + HMAC-token middleware for the orders
  web app (enforcement off by default; `WEB_AUTH_ENABLED=true` to gate `/api/*`).
  Plan: `docs/web-app-plan.md`.
  - `server_app/realtime.py` — **realtime push** to webapp over `/ws`. Order
    mutations from BOTH sources (web via `order_api_common.refresh_order_bg`,
    Telegram via `order_commands_v3._refresh_order_message`) plus new-order
    (`channel_handlers/register.py`), comment-add, and image add/delete
    (`server_app/image_routes.py`, `order_photo_sync.py`) emit `order_changed`
    (carries a ready-to-splice list row) / `orders_changed`. Emit via `emit_*` (fire-and-
    forget, never blocks the refresh path); sends concurrently with a timeout and
    closes dead sockets. `/ws` is gated by token when `WEB_AUTH_ENABLED` (carries
    PII). Client: `webapp/src/realtime.ts` (reconnect + resync-on-reconnect).
    **Realtime coverage is app-wide** — besides order/production events there are
    `customer_changed` (khách sửa/công nợ), `inventory_changed` + `box_changed` (kho/thùng),
    `price_lists_changed` (bảng giá), and the report-editing pair `report_lock` /
    `report_draft` (see Production). Every mutation site emits (customer edit, price save,
    box update/disable/allocate/release, box comments/images, web-only order tasks). Client
    detail widgets Comments/Images/History use `eventMatchesBase(base, e)` to reload only
    when *their* entity changed. If you add a mutation, add its `emit_*`.
  - The old **saved-messages** feed, `/api/search`, `ai_backend.py` (group AI +
    auto-reply-"yes") and the static `/` page were removed; `/` now 302s to `/app/`.
- `utils/` — logging config and shared helpers. Imported everywhere.

**Order workflow (the heart)**
- `command_handlers/` — text commands typed in order/customer forum topics
  (`soan`, `giao`, `nop`, product/customer/note/quỹ/production commands…). Older layer.
- `order_commands_v3.py` (root module, not a shim) — live v3 order commands:
  KiotViet invoice, payment, print, debt, analysis. Registered by
  `server_app/command_bootstrap.py`.
- `channel_handlers/` — reacts to new posts in `#don_hang`: creates topic,
  parses, notifies, renders. **Core = `channel_handlers/create.py::process_new_order(client, msg)`**
  (creates forum topic + order row + fires `auto_parse` = customer/invoice parse +
  channel render + **picking-sheet print**). `register.py` is now just the thin
  Telethon `NewMessage(#don_hang)` listener → calls `process_new_order`. It is
  **idempotent by `message_id`**, and the **webapp create-order calls it directly**
  (see below) because Telethon does NOT emit `NewMessage` for the client's own sends.
  Picking sheet (`renderers/picking_sheet.py`) prints for **every** new order now
  (the old `if invoice:` gate was removed 2026-07-04).
- **Webapp create-order (`server_app/order_api_create.py`, `POST /api/order/create`)** —
  posts the order text into `CHANNEL_DON_HANG_MOI` as the user, then calls
  `channel_handlers.create.process_new_order(client, sent)` directly → real Telegram
  topic + order (positive thread_id, flow_version 2), returns thread_id so the web
  navigates straight to it. **No more DB-only web orders** (the old negative-thread_id
  `flow_version:"web"` path is gone). Client: `webapp/src/pages/CreateOrder.tsx`.
- `donhang_indexer_pkg/` — live + backfill indexing of `#don_hang` → `donhang_store`.
- **Feed khách (`server_app/customer_feed.py`)** — GET `/api/customers/{key}/feed`:
  đơn + thanh toán 1 dòng thời gian (rail nợ, dây SVG nối payment↔đơn). Nợ sau mỗi
  sự kiện: số KiotViet gốc, hoặc **SỐ TÍNH LẠI có kiểm chứng** (nội suy neo mốc KV,
  chỉ hiện khi đoạn CÂN ±1đ — est hiện `≈`; xem memory debt-recalc-permitted-feed).
  Mode `?days=1`/`?day=` cho trang lịch khách (`#/khach/:key/lich`).
- **VIỆC / task list (`task_store/` + `server_app/task_routes.py`)** — bảng
  **`web_tasks`** (bảng `tasks` là sync Firebase legacy 18k row, CẤM đụng). kind:
  `free` (việc tự tạo, link đơn tuỳ chọn) | `order_step`/`order_custom` = **MIRROR
  dual-write từ blob đơn** (blob vẫn là nguồn sự thật; hook ở `order_store/tasks.py`
  + `custom_tasks.py`; done từ dashboard ghi ngược qua `api_task_handler_impl`;
  backfill 1 lần/process, đơn từ 2026-06-01). API `/api/tasks` (+`?days/?day` lịch,
  `?counts=1` badge, `/assignees`); media trao đổi/ảnh scope `task`
  (`entity_media_routes`, thêm cả scope này vào production/box/report_bg). UI:
  `#/viec` (TasksBoard — chips lọc + search không dấu vnfold + lazy scroll + lịch)
  + `#/viec/:id` (TaskDetail) + `TaskBell` badge app-bar (số việc của tôi).
- **Lịch giao (`orders_delivery_handler`)** — `?days=1` (đếm pending/done + NHÃN
  text từng đơn theo ngày giao, mọi tháng) + `?day=` (đơn 1 ngày) + `?month=` cũ.
  Filter **Chưa giao** của dashboard chỉ tính đơn TỚI HẠN (`_ngay_giao_due`: chưa
  hẹn hoặc ngày giao ≤ hôm nay VN) — filter, chip đếm, matcher realtime client
  cùng rule.
- **Orders list load (`server_app/orders_api.py`)** — `GET /api/orders` paginates
  20/page over the `orders` blob table; `_build_order_row` is the single source of
  the list-row shape (reused by realtime). Kept fast by SQLite VIRTUAL generated
  columns `has_customer` / `is_done` + partial indexes `idx_orders_stats` (chip
  counts) and `idx_orders_list` (default `created` sort — no temp-btree), added by
  `orders_db.ensure_orders_stats_columns` (PG already has these). Search uses a
  trigram FTS5 table (`orders_fts`); it + the indexes are **prewarmed in a
  background thread at startup** (`orders_db.prewarm_orders_indexes`) so the first
  search doesn't pay the ~460ms cold build. If you change the row shape or these
  filters, keep the generated-column definitions and `_build_order_row` in sync.
- **Order images (photos) — `server_app/image_routes.py` + `server_app/order_photo_sync.py`.**
  `/api/order/{thread_id}/images` GET/POST(multipart)/DELETE + `.../{id}/file`
  (FileResponse, immutable cache, path-traversal guard). Client resizes+re-encodes
  to WebP and sends a full (~1600px) + thumbnail (~400px) so the server does no
  image work (Pillow only as a thumb fallback). **2-way sync with the Telegram
  topic:** a web upload is forwarded into the order's topic (`ORDER_GROUP_ID`,
  `reply_to=thread_id`, photo preview); a photo posted in the topic is pulled back
  into the gallery (inbound `NewMessage` handler registered in
  `command_bootstrap.py`). **Xoá ảnh = XOÁ MỀM** (2026-07-08): cột
  `deleted_at/deleted_by`, dòng + file GIỮ NGUYÊN — webapp vẫn hiện ảnh kèm dấu X
  đỏ phủ chéo (`.img-x-mark`, mọi nơi: grid/strip/PhotoViewer); xoá HĐ KiotViet
  tự xoá mềm ảnh `kind='hoa_don'` của đơn. Kinds: soan_hang / nop_tien (nhận
  tiền) / **nop_tien_task (nộp tiền — wizard nộp gắn mặc định)** / hoa_don / khac. **Bot-forwarded photos** (session photo → topic via
  `POST /api/tg/send-file`) are imported directly in `send_file_handler` because
  Telethon fires no `NewMessage` for the client's own sends —
  `order_photo_sync.import_sent_image`. Loop-prevention: self-sent message-ids
  (set+deque FIFO) + a `UNIQUE(thread_id, tg_message_id)` index. Add/delete emit
  realtime `order_changed`, an `order.image_added` audit event (→ shows in **Lịch sử
  thao tác** with a thumbnail), and an **FCM push** (`server_app/fcm.py`, topic
  `orders`) — same as new comments (`comment_routes`). Tapping a push **deep-links**
  to `#/order/<id>?focus=<type>:<id>` → OrderDetail scrolls to + highlights the item
  (APK reads FCM `data` extras in `MainActivity`).
- **Dashboard card thumbnail** — `orders_api._attach_thumbs` batch-fetches each
  order's latest image id per list page (and on realtime rows); the card shows it on
  the left. Updates live via the `order_changed` row-splice.

**Data stores (one package per SQLite domain)**
- `donhang_store/` — `#don_hang` index DB (schema, reads, writes, migrations, api).
- `order_store/`, `product_store/`, `payment_store/`, `bang_gia_store/`,
  `note_store/`, `production_store/` — domain tables in the shared `app.db`.
- `user_store/` — `web_users` table in `app.db`: login accounts for the orders web
  app (PIN hash in `pin.py`, CLI: `tools/add_web_user.py`).
- `comment_store/` — `web_comments` table in `app.db`: web-app comments on orders
  (separate from `order_chat_messages` = read-only Telegram log).
- `inventory_store/` — kho thùng (`app.db`). Bảng:
  - `inventory_boxes` (`schema.py`+`queries.py`): 1 row = 1 thùng vật lý. Mã thùng =
    **SỐ GỌI 3 chữ số `001`–`999` TOÀN KHO, xoay vòng** (`domain.next_call_numbers`:
    tiếp từ số cấp gần nhất, nhảy qua số của thùng còn hàng/vô hiệu, hết 999 quay về
    001 — ngoài kho chỉ hô "thùng 347"). Số TÁI DÙNG khi thùng hết hàng → `box_code`
    KHÔNG unique; danh tính bất biến = `id` (lịch sử/link đều theo id). Mã cũ kiểu
    `K2L-001`/base36 vẫn parse (`code_call_number`) + chiếm số tới khi xuất hết.
    Pool tồn gom theo `product_code`. Cột:
    `quantity`, `mfg_date`, `note`, `disabled`+`disabled_reason`, `source_thread_id`
    (phiếu SX nguồn), **`unit_id`** → `inventory_units` (đơn vị chứa: Thùng/Kiện/Hũ…),
    **`place_id`** → `inventory_places` (vị trí kho Kho A/B…). (`status`/`order_thread_id`
    legacy.) `list_boxes`/`get_box` join thêm `place_name`, `unit_name`, `product_unit`
    (đơn vị đếm của SP từ `products.unit` — cây/gói…).
  - `inventory_units` (đơn vị chứa) + `inventory_places` (vị trí kho): bảng user-định-nghĩa,
    CRUD `list/add/rename/delete_*`. API `/api/units`, `/api/places` (rename/delete admin).
  - `box_allocations` (`allocations.py`): 1 row = 1 **phần** thùng đã lấy. `remaining =
    quantity − Σ allocations`; tồn = Σ remaining. Cột **`kind`**: `'order'` (xuất cho đơn)
    | `'production'` (tiêu hao nguyên liệu khi SX — xem `recipe_store`). Xuất
    `allocate_picks(picks, thread_id, kind=)`; thu hồi = `delete_allocation`;
    `list_order_allocations(kind=)` lọc.
  - `domain.py` (pure, unit-tested) = sinh mã base36 + gộp nhóm size. Thùng **vô hiệu**
    → loại khỏi tồn/phân bổ. Admin **xoá thùng** (`box_delete_handler`, cấm nếu đã xuất) +
    gỡ entry khỏi phiếu SX (`production_store.remove_number_by_note`).
  - API `server_app/inventory_routes.py` (`_ensure` = create+migrate mọi bảng): `/api/inventory`
    (summary), `/api/inventory/boxes` (MỌI thùng), `/api/inventory/{code}` (chi tiết SP),
    `/api/inventory/box/{id}` GET/POST/DELETE, nhập `POST /api/production/{id}/boxes`
    (nhận `product_code`/`unit_id`/`place_id`/`consume` = thùng NL tiêu hao),
    xuất `POST /api/order/{id}/allocate|release`.
  - UI (**ô thùng dùng chung `detail/BoxLabelGrid.tsx`** = nhãn tem: mã SP · số +/gốc ·
    đơn vị+mã thùng · **nền "bình chứa" fill ngang theo remaining** · badge vị trí; bản nhỏ
    `BoxMiniGrid` cho card phiếu SX): tab **📦 Kho** = `pages/KhoBoxes.tsx` (`#/kho`, MỌI
    thùng phẳng + lọc mã/vị trí) · `pages/PlacesList.tsx` (`#/vi-tri`) → `PlaceDetail.tsx`
    (`#/vi-tri/:id`) · `pages/InventoryList.tsx` = **"Sản phẩm"** (`#/san-pham`, danh mục) →
    `InventoryDetail.tsx` (`#/kho/:code`, thùng + KiotViet link + `RecipeEditor`) →
    `pages/BoxDetail.tsx` (`#/thung/:id`). Nhập: `detail/ProductionBoxes.tsx` (chọn SP/đơn
    vị/vị trí/nguyên liệu). Xuất: `detail/OrderStock.tsx` + `StockPickerModal.tsx` (popup
    chọn thùng — **cap không cho vượt số cần**, seed lựa chọn cũ).
- `order_images_store/` — `order_images` table in `app.db`: metadata for photos
  attached to an order (filename, thumb, size, dims, uploader, `tg_message_id`).
  Image bytes live on disk under `ORDER_MEDIA_DIR/<thread_id>/`, not in the DB.
- `recipe_store/` — `product_recipes` table (`app.db`): công thức/BOM sản xuất, 1 SP
  cần các nguyên liệu (product khác) theo tỉ lệ (`ratio` = số cây NL / 1 cây thành
  phẩm). Tỉ lệ định nghĩa ở trang chi tiết SP (`detail/RecipeEditor.tsx`). Khi nhập
  thùng ở phiếu SX, người dùng CHỌN thùng nguyên liệu → trừ kho qua
  `inventory_store.allocate_picks(kind='production')` (cột `kind` phân biệt xuất-đơn ↔
  tiêu-hao-SX; `remaining` = quantity − Σ mọi allocation nên tồn NL giảm đúng).
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
- `renderers/`, `printouts/` — HTML/PNG rendering; print jobs queued via **Firebase
  RTDB** (`meta/to_print`, `html-to-png`), not WebSocket. (`/ws` is now the webapp
  realtime channel only — see `server_app/realtime.py`. The old Next.js `frontend/`
  was removed — use `webapp/`.)
- `sheets_bot/` — Google Sheets bot (runs on the user client). DISABLED by default
  (gated by `SHEETS_BOT_ENABLED` in `server_app/bootstrap.py`); no-op without creds.

**Production (sản xuất / phiếu SX)**
- `production_store/` — `production_slips` table (1 row per forum topic, keyed
  `thread_id`; standalone, **no order link**). The worker báo cáo (bảng theo thợ) is a
  **JSON blob in the `bang` column** of that row (whole-blob overwrite via `set_bang`).
  `domain.py` = pure `;`-format báo cáo parser (`parse_report`/`compute_report`/
  `looks_like_report`, unit-tested) shared by the Telegram handler AND the webapp so they
  never drift. `command_handlers/production_commands.py` = the group bot.
  - **`production_store/report_rows.py` — relational mirror `production_report_rows`**
    (1 row per thợ per phiếu: worker_name, product_code, report_date + normalized
    `report_ymd`, so_gach/so_tru/so_cay_le/so_mam/tong_calc, note; indexed). Dual-written:
    `set_bang` also does delete+insert here so it's queryable for the dashboard (the `bang`
    blob stays the source for current UI reads). Has `dashboard()` + `worker_detail()`
    aggregation queries + `backfill_report_rows()`.
- `server_app/production_routes.py` — webapp API `/api/production*` (list/detail/
  catalog/create/set-product/set-target/add-number/report parse+save/delete). Create
  opens a forum topic in `PRODUCTION_GROUP_ID`. Emits realtime `production_changed`/
  `productions_changed` (separate id-space from orders). **Report editing has a
  single-editor lock** (in-memory TTL 45s, heartbeat 20s): `/report/lock|unlock|draft`
  + events `report_lock` (who holds) / `report_draft` (live keystrokes to viewers). Save
  is server-guarded (409 if another holds). These transient endpoints are **excluded from
  audit** (`server_app/audit.py` `_NO_AUDIT`) so history isn't spammed. `production_sheets.py`
  = best-effort Google Sheet push on report save (gated; no-op without creds).
  `server_app/production_dashboard_routes.py` — `/api/production/report-dashboard` +
  `/api/production/worker/{name}` (registered BEFORE `{thread_id}`).
  Webapp UI: `webapp/src/pages/ProductionList.tsx` + `ProductionDetail.tsx` +
  `detail/ProductionReport.tsx` (báo cáo **view-only, always shown** + ✏️ Sửa button), nav
  tab 🏭 SX (`#/san_xuat`). **Sửa báo cáo = trang riêng `pages/ProductionReportEdit.tsx`**
  (`#/san_xuat/:id/bao-cao`): editable spreadsheet-grid table (type Tên/Gạch/Trừ/Lẻ/Ghi
  chú, auto-computes Mâm+Tổng from `slip.sp_mam`; builds `;`-text → existing save endpoint),
  with the lock overlay + live draft view. **Dashboard `pages/ProductionDashboard.tsx`**
  (`#/sx-bang`, in ☰ Thêm) → tap a thợ → `pages/ProductionWorkerDetail.tsx` (`#/sx-tho/:name`,
  per-day phiếu/SP breakdown). Chọn mã SP dùng **`detail/ProductPicker.tsx`**.
  - **Công thức/BOM** (`recipe_store`): SP có thể cần nguyên liệu (product khác) theo tỉ lệ,
    đánh dấu **bắt buộc / không bắt buộc**. Định nghĩa ở chi tiết SP (`detail/RecipeEditor.tsx`).
    Khi nhập thùng → phải chọn thùng NL (bắt buộc) → trừ kho (`allocate_picks kind='production'`).

**Web app for phones (orders management, 5-6 internal users)**
- `webapp/` — Vite + Preact + TS mobile UI (Vietnamese). Hash router `main.tsx`, nav
  bottom **📋 Đơn · 👤 Khách · ➕ Tạo · 🏭 SX · 📦 Kho** + ⚙️ cài đặt ở top bar
  (đăng xuất; kèm `TaskBell` badge việc-của-tôi + chuông thông báo). Dashboard Đơn:
  view-slider 4 ô (chi tiết/gọn/siêu gọn/**📅 lịch giao**). Menu ☰ Thêm có **Việc**. Trang: orders list/detail, tasks, payments, comments, create order,
  **sửa hoá đơn = trang riêng `pages/OrderInvoiceEdit.tsx` (`#/order/:id/hoa-don`,
  mở thẳng edit; KHOÁ nếu đã có HĐ KiotViet; order detail chỉ hiện tóm tắt + nút)**,
  customers/debt (bảng giá riêng `personal_price_list`), **photos (camera in-page HTTPS +
  gallery, 2-way Telegram sync)**, **phiếu sản xuất (🏭 SX)** + sửa báo cáo thợ + dashboard SX,
  **kho (📦 Kho: thùng/vị trí/sản phẩm — xem `inventory_store`)**, lịch giao (`#/lich`),
  lịch sử thao tác (`#/lich-su`).
  - **Admin xoá**: đơn (`order_api_delete.py`, cấm nếu còn HĐ KiotViet/phân bổ kho), thùng, SP,
    vị trí, HĐ KiotViet. **Đơn vị SP** (`products.unit`) sửa ở chi tiết SP; hiện đúng khắp nơi.
  - **UI dùng chung (đừng tự chế lại)**: `ui/SelectPopup` (chọn tĩnh) + `ui/PickerPopup`
    (autocomplete) = mọi dropdown/select là **popup neo đỉnh** (bàn phím không che); mọi
    popup gọi `ui/usePopupBack` (nút BACK đóng popup trước) + `useScrollLock`. Ô thùng =
    `detail/BoxLabelGrid`. Toast/confirm = `ui/feedback`. Cuộn = `scroll.ts`.
    **`ui/SearchBar`** = search bar chuẩn mọi trang list (+ `FilterActiveBar` panel
    "Đang lọc"). **`detail/ScrollCalendar`** = lịch cuộn liền mạch kiểu macOS dùng
    chung (lịch giao `#/lich` [text đơn trong ô, đỏ chưa giao/xanh đã giao], lịch
    khách `#/khach/:key/lich`, lịch việc): vô hạn 2 chiều kể cả tháng trống, tháng
    active nổi bật khi lướt, nút Hôm nay, chấm/dòng đúng số lượng; prepend có bù
    scroll + `overflow-anchor:none` (không thì Chrome bù đôi → nhảy tháng).
    Dải ảnh `ImageStrip` tràn màn tự CUỘN VÒNG (rAF scrollLeft — chạm là dừng, yên
    3s chạy tiếp); popup camera `CameraBox` có nút Chọn ảnh từ máy. Nhớ vị trí cuộn **trung tâm** (`useScrollMemory`
  trong `main.tsx`: back→khôi phục, forward→top; trang lazy-load cache list ở module scope
  để về đúng vị trí tức thì, khỏi refetch). **Camera cần HTTPS** (WebView phải load URL
  `https://…/app` qua tailscale serve :443 — nếu load `http://…:8090` thì nút Mở camera ẩn;
  push-update.sh default URL = HTTPS). Offline cache+queue. Build
  `cd webapp && npm run build` →
  served at `/app` (`server_app/webapp_routes.py`). Image UI: `webapp/src/detail/
  Images.tsx` (+ `imageProcess.ts` client-side WebP resize/thumbnail).
- **APK for phones** — built by the EXTERNAL generic builder at
  `~/Documents/ultimate-webview-android` (a thin WebView loading the server URL over
  Tailscale), NOT the in-repo `android/`. To push an update run
  `./push-update.sh` there: it bumps the versionCode above the deployed one and
  deploys `app.apk` + `version.json` into `~/letrang-db/apk` (= `WEBAPP_APK_DIR`),
  served at `/app/update/`; installed apps auto-prompt on next resume. Webapp-only
  changes don't need an APK push (WebView loads the webapp remotely — a reload gets
  them); rebuild the APK only for native changes (permissions, camera) or to force a
  fresh reopen. The in-repo `android/` is legacy (bundled dist, "not installable").
  Full plan/status: `docs/web-app-plan.md`.

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

- **One file = one thing, ≤400 lines.** Each file does one job and does it well.
  Split modules by responsibility. Hard cap **400 lines per file** — if a file grows
  past it, split it along responsibility lines. Do not merge unrelated features to
  save files.
- **Every module should say what it does and what it connects to.** Start each
  module with a one-line docstring: what this file does + which package(s)/store(s)
  it talks to. Packages: put the summary in `__init__.py`.
- **Config via env.** Shared filesystem paths live in **`utils/paths.py`** (single
  source: `SHARED_DB_PATH`, `DONHANG_DB_PATH`, `ORDER_MEDIA_DIR`) — import from there, never re-derive
  `os.path.expanduser(os.getenv("SHARED_DB_PATH", ...))` inline. Other env/config
  reads go through `server_app/config.py` (or a package's own `config.py`). Don't
  hardcode new secrets/paths — add an env var with a default.
- **DB connections go through `utils/db.py`** — `get_connection(path, *, readonly,
  autocommit, busy_timeout)` + `transaction(conn)`. Every `app.db` access uses this
  one gateway (no scattered `sqlite3.connect`). Default engine is **SQLite**. There
  is a **dormant PostgreSQL path** behind `DB_ENGINE=postgres` (`utils/pg.py` psycopg
  wrapper, `utils/sql_translate.py`, `migrations/pg/`, `tools/migrate_*`) — the app
  was migrated to PG then reverted to SQLite (single process/machine → SQLite fits;
  see `docs/postgres-migration.md`). Leave it dormant unless re-enabling PG.
- **Telegram sends/edits go through the gateway** (`TelegramGateway`) so flood-wait
  / rate limits are handled — don't call `client.edit_message` raw in hot paths.
- **Order mutations are read-modify-write on a JSON blob.** Orders live as one
  `json` column; a mutation is `get_order_by_thread_id → mutate dict → _save_order`.
  Wrap that sequence in `with transaction(conn):` (`order_store.schema`) so it's
  atomic — otherwise concurrent writers lose updates. `set_task_status` /
  `clear_task_status` already do; new mutation sites should too. See
  `docs/senior-review.md` for the phased plan to replace the blob with a typed model.
  ⚠ **Known offenders that skip `transaction()`** (fix if you touch them): several
  `order_commands_v3.py` handlers (`on_comma_invoice`, `vat`/`pvc`, `fix`, `bo no`,
  `detect invoice`), `mirror_channel.sync_order_to_mirror`, and the bot flow
  `bot_flows/invoice_create._save_order_field` (raw SQL, no transaction) — all do
  bare RMW on the blob and can clobber concurrent writes.
- **Layering pattern (copy this).** New/changed order logic goes in 3 layers:
  **store** (`order_store/tasks.py`, `payment_store/…`) = transaction + IO only →
  **domain** (`order_store/domain.py`, `payment_store/domain.py`) = pure rules, no
  IO, unit-tested → **model** (`order_store/model.py` `Order`) = lossless typed
  façade over the blob. Reference impls: `set_task_status`, the payment decision
  logic, `compute_debt`. Put pure logic in a `domain` module and unit-test it.
- **Run the tests with `./scripts/test.sh`** (wraps pytest; auto-installs dev deps
  from `requirements-dev.txt` on first run). 85 tests. Run before/after touching
  `order_store`/`payment_store` — the heart, parsers, and money math are
  characterized (`tests/test_order_store.py`, `test_order_domain.py`,
  `test_parsers.py`, `test_payment_domain.py`, `test_profit.py`).
  Filter: `./scripts/test.sh -k task_status`.
- **Auto-commit after every change.** When you finish a change, commit it
  yourself — do not ask the user first. Small, focused commits (Conventional
  Commits style, Vietnamese subject OK). Never commit secrets/DBs (see gitignore).
  Committing ≠ pushing: push only when asked.

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
- **Secrets:** KiotViet `client_id`/`client_secret` were hardcoded in
  `integrations/kiotviet/core.py`; now read from `.env` (`KIOTVIET_CLIENT_ID/SECRET`).
  ⚠ The old secret is in git history — **rotate it** (see `REVIEW_REPORT.md`).
- **Security debt (Tailscale-mitigated):** `WEB_AUTH_ENABLED` defaults false (all
  `/api/*` unauthenticated), and `tg_api` auth (`tg_api/common.py`) fails OPEN when
  `TG_EDIT_API_KEY` is unset. Safe only because deployment is Tailscale/LAN-only.
  Remediation steps in `REVIEW_REPORT.md` (repo root — full autonomous review 2026-07-03).
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
