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
- **Gallery camera Cloudinary (`server_app/cloudinary_routes.py` + `cloudinary_warm.py`)** —
  trang `#/camera` (`webapp/src/pages/CameraGallery.tsx`, poll 10s + module-cache +
  content-visibility; **layout 2 CỘT SONG SONG**: hàng = 1 thời điểm, channel 11 trái ⟷
  channel 14 phải, ghép cặp lệch ≤5s, ô 16:9, lọc 1 kênh → grid 3 cột; **lazy load
  khi cuộn** — nút "Xem ảnh cũ hơn" là sentinel IO) ← `/api/cloudinary/camera-images`
  (**chỉ văn phòng** — `is_office_request`, menu Thêm ẩn với staff): proxy Search API read-only
  (key chỉ ở server, multi-account env `CLOUDINARY_*`), cache trang đầu RAM
  stale-while-revalidate (60s fresh/10ph stale, dedup in-flight) + refresher 15s
  (idle-gate: không ai poll 5ph → 0 request), ETag/304. `cloudinary_warm.py` = session
  aiohttp dùng chung + **CDN-warm derived asset ảnh MỚI** (GET thumb/preview với Accept
  giống browser — f_auto derive theo Accept; warmed set FIFO 500, seed lúc boot).
  Endpoint nằm trong `_NO_AUDIT` (poll 10s không ghi audit_events).
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
  **idempotent by `message_id`** — the `_existing_thread` re-check + topic-create +
  `_create_order` insert run under a per-`(channel_id, message_id)` `asyncio.Lock`
  (`_create_locks`), so 2 concurrent calls for the same message can't create a double
  topic/đơn. The **webapp create-order calls it directly**
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
  Logic chuỗi nợ thuần = **`server_app/feed_debt.py`** (unit-tested,
  tests/test_debt_chain.py): điền + **demote mốc đúng-số-nhưng-SAI-CHỖ** (HĐ KV
  tạo trễ sau phiếu thu → khDebt chụp sai thời điểm — bỏ ít mốc nhất cho chuỗi
  cân lại, có leo thang + guard ts_guessed/nợ-âm). Mode `?days=1`/`?day=` cho
  trang lịch khách (`#/khach/:key/lich`).
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
- **PRODUCT ID = danh tính bất biến (2026-07-09).** `products.id` INTEGER PK; `code`
  chỉ là NHÃN UNIQUE **đổi tự do** (admin, ô "Mã SP" ở `#/kho/:code`; cấm mã toàn
  chữ số). Mọi liên kết nội bộ theo id: `inventory_boxes.product_id`,
  `product_recipes.product_id/ingredient_id`, `production_slips.product_id`,
  `production_report_rows.product_id`, bảng giá key = `str(id)`
  (`price_list_store/keys.py`), item đơn/trả hàng có `sp_id` (backfilled 99,9%,
  choke = `freeze_invoice_cost_prices`). Mã cũ ghi `product_code_history` → alias:
  parser nhận mã cũ, URL cũ redirect, search mở rộng, đơn-theo-SP không đứt
  (`product_store/resolve.py`). HIỂN THỊ mã/tên luôn resolve bản hiện hành, fallback
  snapshot khi SP xoá (`order_store/display.py`, cache 30s); GIÁ/giá vốn là snapshot
  vĩnh viễn — không resolve lại. **KiotViet giao tiếp bằng `productId`** (`kv_id`
  trong invoiceDetails — spike xác nhận), đổi mã local không ảnh hưởng; rename đẩy
  code mới sang KiotViet best-effort (`update_product_code_kv`). Đổi mã =
  `product_store.rename_product` (UPDATE 1 ô + history + refresh cột mã snapshot +
  emit realtime + audit `product.renamed`). Migration/backfill chạy ở boot:
  `server_app/db_migrate.py` (idempotent, marker kv_store). SP_INFO (mâm/lượng SX)
  port vào cột `prod_mam`/`prod_luong` (fallback config, `production_store/defaults.py`).
  Plan: `docs/plan-product-id.md`.
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
    (phiếu SX nguồn), `source_purchase_id`/`source_return_id` (thùng tạo từ phiếu NHẬP
    HÀNG / hàng TRẢ về — link "Nguồn" ở BoxDetail + guard cấm xoá lẻ khi phiếu đã
    xử lý hàng), **`unit_id`** → `inventory_units` (đơn vị chứa: Thùng/Kiện/Hũ…),
    **`place_id`** → `inventory_places` (vị trí kho Kho A/B…). (`status`/`order_thread_id`
    legacy.) `list_boxes`/`get_box` join thêm `place_name`, `unit_name`, `product_unit`
    (đơn vị đếm của SP từ `products.unit` — cây/gói…).
  - `inventory_units` (đơn vị chứa) + `inventory_places` (vị trí kho): bảng user-định-nghĩa,
    CRUD `list/add/rename/delete_*`. API `/api/units`, `/api/places` (sửa tên/ghi chú qua
    POST `{name?, note?}`; delete admin). Vị trí có **ảnh/trao đổi/lịch sử** (entity media
    scope `place`); list trả `thumb_image_id` (ảnh mới nhất, `entity_media_store.latest_image_ids`)
    → thumbnail card ở dashboard `#/vi-tri`.
  - `box_allocations` (`allocations.py`): 1 row = 1 **phần** thùng đã lấy. `remaining =
    quantity − Σ allocations`; tồn = Σ remaining. Cột **`kind`**: `'order'` (xuất cho đơn)
    | `'production'` (tiêu hao nguyên liệu khi SX — xem `recipe_store`)
    | `'transfer_out'`/`'transfer_in'` (**chuyển hàng giữa 2 thùng cùng SP** — bút toán
    kép ±q cùng transaction qua `transfer_between_boxes`, dòng `transfer_in` quantity ÂM
    nên mọi công thức remaining tự đúng; `quantity` gốc 2 thùng KHÔNG đổi, tồn tổng bảo
    toàn; API `POST /api/inventory/box/{id}/transfer`, UI ở chi tiết thùng). Xuất
    `allocate_picks(picks, thread_id, kind=)`; thu hồi = `delete_allocation`;
    `list_order_allocations(kind=)` lọc. **Xoá thùng thành phẩm phiếu ĐÓNG GÓI** hoàn NL
    theo ratio × số cây (`release_production_amount`, LIFO, trả chi tiết thùng NL nhận);
    xoá cả phiếu hoàn nốt residue (`release_production_consumption`).
  - `domain.py` (pure, unit-tested) = sinh mã base36 + gộp nhóm size. Thùng **vô hiệu**
    → loại khỏi tồn/phân bổ. Admin **xoá thùng** (`box_delete_handler`, cấm nếu đã xuất) +
    gỡ entry khỏi phiếu SX (`production_store.remove_number_by_note`).
  - **PHIẾU ĐIỀU CHỈNH tồn thùng (`inventory_store/adjustments.py` + `server_app/adjustment_routes.py`,
    2026-07-16)**: bảng `inventory_adjustments`, mỗi phiếu = 1 allocation `kind='adjustment'`
    quantity = −delta — KHÔNG sửa quantity gốc, remaining tự đúng mọi công thức. Tạo =
    văn phòng (`POST /api/inventory/box/{id}/adjust` {new_remaining, reason bắt buộc} —
    delta tính trong transaction); gỡ = admin (hoàn nguyên, guard tồn âm). Event
    `adjustment.created/deleted` (scope='box'). UI `detail/BoxAdjust.tsx` ở chi tiết thùng.
    **Kiểm kho ÁP DỤNG vào kho** (`inventory_store/stocktake_apply.py`, POST
    `/api/stocktakes/{id}/apply`, văn phòng): phiếu ĐÃ CHỐT, 1 lần (applied_at CAS),
    tạo phiếu điều chỉnh theo DELTA (đếm − sổ lúc chụp — không đè biến động hợp lệ
    sau đếm), all-or-nothing + chặn tồn âm; cột applied_at/by/result. Event
    `stocktake.applied`. Tests: tests/test_adjustments.py.
  - **Kiểm kho theo vị trí (`inventory_store/stocktakes.py` + `server_app/stocktake_routes.py`
    + `stocktake_lock.py`)**: `inventory_stocktakes`/`inventory_stocktake_items` — 1 phiếu/vị
    trí, chụp `expected_quantity` (= remaining) CỐ ĐỊNH lúc tạo; mỗi vị trí tối đa 1 nháp
    (unique partial index `WHERE status='draft'`). Khoá 1-người (`stocktake_lock.py`, TTL 60s,
    heartbeat 20s, multi-tab). **Vô hiệu hoá khi kho biến động:** `_place_live_state` (CÙNG
    tập/công thức với lúc chụp) so với snapshot → `_payload` gắn `stale{changed,added,removed,
    adjusted,summary}` cho phiếu **draft**; `complete` bị chặn (409 `stale`); webapp nghe
    realtime `inventory_changed` → `reloadStale()` báo người đang kiểm. Gỡ: `resync_stocktake`
    (đồng bộ số sổ sách theo tồn hiện tại, GIỮ số đã đếm, thêm/bớt dòng) — cần giữ khoá; hoặc
    `void_stocktake` (`status='voided'`, văn phòng, giải phóng vị trí). Audit `stocktake.
    created/completed/resynced/voided`. UI `pages/StocktakeDetail.tsx` (`#/kiem-kho/:id`).
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
  phẩm). Tỉ lệ định nghĩa ở trang chi tiết SP (`detail/RecipeEditor.tsx`). Nhu cầu NL
  theo **LOẠI PHIẾU** (bỏ cờ bắt buộc/optional per-NL 2026-07-09): phiếu **sản xuất**
  = KHÔNG cần NL; phiếu **đóng gói** = BẮT BUỘC có công thức + chọn đủ thùng NL cho
  MỌI nguyên liệu → trừ kho qua
  `inventory_store.allocate_picks(kind='production')` (cột `kind` phân biệt xuất-đơn ↔
  tiêu-hao-SX; `remaining` = quantity − Σ mọi allocation nên tồn NL giảm đúng).
  **Cách sản xuất = 2 CỜ ĐỘC LẬP trên `products` (2026-07-16)**: `can_produce_directly`
  (INTEGER DEFAULT 1 = 🏭 SX trực tiếp, phiếu `kind='san_xuat'`) và `can_package`
  (INTEGER DEFAULT 0 = 📦 đóng gói từ NL, phiếu `kind='dong_goi'`). 1 SP có thể bật CẢ
  hai / KHÔNG cái nào (= nguyên liệu / hàng mua từ NCC). Phiếu san_xuat chỉ nhập SP
  can_produce_directly; phiếu dong_goi chỉ nhập SP can_package + bắt buộc công thức
  (gate ở `inventory_routes` + picker `ProductionBoxes.tsx`). UI 2 chip toggle độc lập
  ở `InventoryDetail.tsx` khối "Cách sản xuất". Backfill 1 lần marker
  `migrate/can_package_v1` (SP chỉ-đóng-gói-cũ + SP có công thức → can_package=1).
- `settings_store/` — cài đặt hệ thống (blob `kv_store['app_settings']`, app.db):
  toggle rule vận hành, sửa từ trang Cài đặt webapp (admin, `server_app/settings_routes.py`).
  Hiện có `soan_hang_require_stock` (mặc định BẬT): task **soạn hàng** chỉ đánh dấu
  xong khi đơn **đã chốt xuất kho** (`$.stock_confirmed`, POST `/api/order/{id}/stock-confirm`
  — xuất đủ mới chốt, chốt xong khoá allocate/release trừ admin,
  `server_app/order_stock_lock.py`) **và có ảnh `soan_hang`**; tiếp chuỗi:
  giao hàng cần soạn xong, in HĐ giao cần giao xong. Rule ở
  `order_store/guards.py`, chặn cả web API, lệnh Telegram lẫn `print_service`.
- `return_store/` — phiếu TRẢ HÀNG (`return_slips`, app.db). KiotViet public API
  KHÔNG có POST /returns → cơ chế: **HĐ KiotViet GIÁ ÂM** (sl dương × giá âm — KV
  nhận, trừ thẳng nợ; sl âm bị chặn, phụ thu âm bị ép 0). **Flow giống ĐƠN**: tạo
  phiếu = NHÁP (chưa đụng KV/nợ, sửa được) → `POST /api/returns/{id}/invoice`
  (văn phòng) tạo HĐ âm + trừ nợ + khoá sửa; xoá = admin (xoá HĐ KV, hoàn nợ);
  resync nợ qua `debt_sync` return_id. **Đã xử lý hàng (`goods_handled_at`) → chặn
  sửa items VÀ chặn xoá phiếu** (thùng đã tạo/tồn đã đổi, không hoàn tác được). Ảnh/trao đổi/lịch sử = entity media scope
  `return`. Realtime `return_changed`. UI: dashboard `#/tra-hang` (ReturnsList,
  menu Thêm) + chi tiết `#/tra-hang/:id` (ReturnDetail) + nút '↩ Trả hàng'
  (`detail/ReturnModal.tsx`) ở chi tiết khách; feed khách kind='return'
  (nháp delta 0, có HĐ delta âm).
  - **Xử lý HÀNG trả về** (`server_app/return_goods.py::apply_goods_dispositions`, POST
    `/api/returns/{id}/handle-goods`, văn phòng): sau khi tạo phiếu trả, prompt "Xử lý
    ngay?" → `detail/ReturnGoodsModal.tsx` mỗi dòng chọn **nhập vào thùng có sẵn**
    (`update_box` +quantity) | **tạo thùng mới** (`add_boxes`) | **xuất hủy** (box-less,
    gom 1 phiếu) | bỏ qua. Cột `goods_handled_at/by/goods_result` (JSON) chặn xử-lý-2-lần
    + hiện tóm tắt. Audit `return.goods_handled`. Auto-mở modal qua sessionStorage `rg_open`.
- `disposal_store/` — phiếu XUẤT HỦY hàng hóa (`disposal_slips`, app.db, 100% local).
  Hai loại: **THEO THÙNG** (`create_disposal`) hủy hàng hư/hết hạn, trừ tồn qua
  `box_allocations kind='disposal'` (order_thread_id = id phiếu; remaining tự đúng), xoá
  (admin) → TỒN HOÀN LẠI; **BOX-LESS** (`create_manual_disposal`, `source_return_id`)
  cho hàng khách trả bị hủy — chỉ GHI NHẬN, KHÔNG trừ tồn, `_row_to_slip` gắn `box_less`,
  xoá chỉ xoá mềm. BẮT BUỘC lý do, items = snapshot. **Tạo phiếu theo thùng ở
  `#/thung/:id` BẮT BUỘC CHỤP ẢNH** (photo-first: CameraBox collect → tạo phiếu →
  upload `/api/media/disposal/{id}`; HTTP-no-camera fallback không ảnh). API
  `disposal_routes.py` (`/api/disposals*`); realtime `disposal_changed`; media scope
  `disposal`. UI: `#/xuat-huy` (DisposalsList) → `#/xuat-huy/:id` (DisposalDetail).
  Tests: `tests/test_disposal_store.py`, `tests/test_return_goods.py`.
- `supplier_store/` + `purchase_store/` — NHẬP HÀNG + NHÀ CUNG CẤP (app.db,
  **100% local, không KiotViet**). `suppliers` (tên/SĐT/địa chỉ/ghi chú, xoá mềm,
  chặn xoá khi còn phiếu) + `purchase_slips` (items JSON [{sp, sp_id?, sl, price}]
  — **hàng hoá dùng chung bảng sản phẩm**: mã resolve qua `product_store` gắn
  `sp_id`, hiển thị bản hiện hành như đơn; giá ≥ 0, snapshot). Flow như đơn: tạo/sửa
  = văn phòng, xoá = admin (xoá mềm). **`update_purchase_items` chặn hạ tổng dưới số
  đã trả VÀ chặn đổi NCC khi `paid > 0`** (gỡ các lần trả trước mới đổi được). API `server_app/supplier_routes.py` +
  `purchase_routes.py` (`/api/suppliers*`, `/api/purchases*`); realtime
  `purchase_changed`/`supplier_changed`; ảnh/trao đổi/lịch sử = entity media scope
  `supplier`/`purchase`. UI: dashboard `#/nhap-hang` (PurchasesList + PurchaseModal,
  chọn NCC gõ tên lạ → tạo mới ngay) → `#/nhap-hang/:id` (PurchaseDetail);
  `#/ncc` (SuppliersList, thống kê số phiếu/tổng tiền) → `#/ncc/:id` (SupplierDetail,
  sửa info + phiếu nhập của NCC). Tests: `tests/test_purchase_store.py`.
  **Trả tiền NCC từ KÉT (2026-07-14)**: cột JSON `payments` trên `purchase_slips`
  (`purchase_store/payments.py` — RMW nguyên tử, chặn trả quá phần còn nợ TRONG
  transaction; id payment = epoch ms SỐ để audit-path chuẩn hoá {id}). POST
  `/api/purchases/{id}/pay` (đăng nhập, két CỦA MÌNH — admin két bất kỳ; chặn quá
  số dư két, serialize qua `cashbox_routes._transfer_lock`) + `/payments/{pid}/delete`
  (admin). Derive vào hệ két: két người trả → EXTERNAL (NCC), reason `purchase_pay`
  (`cashbox_store/service.py`, stamp có chữ ký SUM(LENGTH(payments))). Sự kiện
  `purchase.paid`/`purchase.payment_deleted` (event_format + _PAIRS). UI: khối
  "Thanh toán NCC" ở PurchaseDetail (trả nhiều lần, admin gỡ), chip ✓ đã trả/nợ ở
  PurchasesList, link phiếu nhập trong timeline két.
  **Nhập KHO hàng mua về (2026-07-16, flow GIỐNG XUẤT KHO ĐƠN)**: phiếu MỞ → ghi
  nhập TỪNG ĐỢT, đủ rồi CHỐT. Cột `goods_handled_at/by/goods_result` trên
  `purchase_slips` = trạng thái CHỐT; trạng thái ĐANG NHẬP derive LIVE từ kho
  (`purchase_goods._draft_receipt`: thùng `source_purchase_id` + allocation
  `purchase_in`) — không bảng state riêng. Orchestration thuần
  `server_app/purchase_goods.py` (tests/test_purchase_goods.py), row đọc
  `purchase_goods_view.py` (attach `boxes` + `draft_receipt{new,existing,totals}`
  vào detail), routes `purchase_goods_routes.py` (đăng ký app_factory):
  - POST `/receive-goods` (văn phòng, nhiều lần): mỗi dòng `restock_new` (tạo N
    thùng GIỐNG NHAU như phiếu SX — `{count, quantity/thùng, unit_id, place_id}`,
    thùng gắn `source_purchase_id` → link "Nguồn") | `restock_existing`
    (allocation ÂM `kind='purchase_in'` — remaining tăng, quantity gốc giữ) |
    `skip`. Validate TRƯỚC khi ghi: mã có trên phiếu, đúng SP thùng, thùng
    sống/còn hàng, không vượt trần cộng dồn theo SP (trần = phiếu − đã nhập).
  - Gỡ từng dòng khi ĐANG MỞ: xoá thùng mới qua DELETE box (office được với thùng
    `source_purchase_id` phiếu mở — `box_delete_handler`; thùng khác admin-only,
    `_box_delete_lock` chặn phiếu chốt/thùng đã dùng); gỡ dòng cộng qua POST
    `/unreceive {allocation_id}` (guard phần cộng chưa tiêu).
  - POST `/confirm-goods` (văn phòng): CHỐT — CAS `goods_handled_at` + snapshot
    `goods_result` từ trạng thái đang nhập → phiếu KHOÁ sửa items + chặn xoá.
    CHỈ chốt khi đã nhập ĐỦ mọi mã theo phiếu (như chốt xuất kho đơn; server chặn
    cả confirm lẫn handle-goods, UI mờ nút kèm lý do) — hàng về thiếu/vỡ thì sửa
    SL trên phiếu về số thực nhận rồi chốt.
  - POST `/handle-goods` = receive + confirm 1 transaction (endpoint cũ, tương thích).
  - **HỦY CHỐT** (admin) POST `/undo-goods`: all-or-nothing — giữ thùng mới, gỡ
    allocation purchase_in, clear goods_* → phiếu QUAY VỀ trạng thái đang nhập;
    CHẶN nếu hàng đã dùng (thùng mới có allocation, remaining thùng có sẵn < số cộng).
  - Guard nhất quán khi kho còn dấu vết nhập: `soft_delete_purchase` chặn xoá
    phiếu; `update_purchase_items` chặn hạ hàng dưới phần đã nhập
    (`_retained_box_totals` = thùng + purchase_in) + re-check khoá TRONG transaction.
  Events: `purchase.goods_line_added/line_removed/received/undone` (event_format).
  UI `PurchaseDetail`: khối "Đang nhập kho (chưa chốt)" — tiến độ theo mã
  (đã nhập/trên phiếu/thiếu) + Ô THÙNG 1 ô/1 dòng nhập (BoxTileGrid
  mode="allocated", ✕ đỏ góc ô = xoá thùng mới / gỡ phần cộng — giống thu hồi ở
  OrderStock), nút "Nhập thêm" + "✓ Chốt nhập kho"; sau chốt = khối "Đã nhập
  kho" + Hủy chốt.
  `PurchaseGoodsModal` = popup GHI 1 đợt (prefill + cap theo phần còn lại; đơn vị
  nhập Thùng ×30 → count×per; prompt sau tạo phiếu, cờ session `pg_open`); items
  gắn `base_unit` (đơn vị gốc SP) để bảng hàng nhập luôn hiện đơn vị; chip 📦 kho.
  **Đơn vị nhập trên dòng phiếu (2026-07-16)**: item nhận thêm `unit`/`unit_factor`
  (snapshot từ `product_units` — SL + giá tính theo đơn vị đã chọn, 1 unit =
  factor đơn vị gốc; `_parse_items` validate, đơn vị xấu chỉ rơi phần unit).
  UI `detail/PurchaseUnitPicker.tsx` (chỉ hiện khi SP có quy đổi; chọn ở
  PurchaseModal/PurchaseEdit, cache đơn vị `purchaseProduct.unitChoicesFor`);
  modal nhập kho prefill SL = sl × factor (quy về đơn vị gốc).
  SP có 2 cờ `can_sell`/`can_purchase` (products, mặc định 1, sửa ở chi tiết SP
  `#/kho/:code` khối "Mua bán", admin): tắt → SP biến khỏi GỢI Ý picker tương ứng
  (bán = InvoiceEditor, nhập = PurchaseModal/PurchaseDetail — lọc client-side từ
  `/api/products?search=`; mã gõ tự do vẫn nhận).
  **QUY ĐỔI ĐƠN VỊ (2026-07-16)**: bảng `product_units` (`product_store/units.py`,
  khoá products.id) — 1 SP nhiều đơn vị phụ, `factor` = 1 đơn vị phụ = ? đơn vị gốc
  (`products.unit`); quy đổi 2 đơn vị bất kỳ = tỉ số factor (`convert`, unit-tested).
  API `/api/products/{code}/units*` (`server_app/product_unit_routes.py` — GET đăng
  nhập, thêm/sửa văn phòng, xoá admin; audit `product.unit_*`, realtime
  inventory_changed). UI khối "Quy đổi đơn vị" chi tiết SP (`detail/ProductUnits.tsx`).
- `cashbox_store/` — hệ KÉT TIỀN "ai đang giữ tiền" (2026-07-14). Trạng thái két
  **DERIVE THUẦN từ blob đơn** (chỉ đơn từ `SINCE=2026-07-14` theo NGÀY VN — env
  `CASHBOX_SINCE`; mốc SQL đổi sang UTC `_since_utc`, đơn cũ hơn chưa qua flow
  két nên loại như tính năng kho), KHÔNG ledger table —
  mỗi đồng của đơn nằm ở đúng 1 két mọi thời điểm, movement là cặp src→dst cân
  bằng ⇒ bảo toàn tiền theo cấu trúc (un-done task/xoá payment/sửa HĐ → recompute
  tự đúng). Máy trạng thái (`domain.py`, unit-tested `tests/test_cashbox_domain.py`):
  tiền ở KHÁCH → `giao_hang` done → két người giao (COD phần chưa thu) →
  `nop_tien` done: `tra_tien_mat`→két văn phòng | `co/khong_ky_toa`→két khách nợ
  | không note/skip→**két chưa rõ** (không đoán) | `chieu_lay_tien` (done=false)
  → vẫn giữ; payment → rút min(amount, phần còn lại) từ két hiện tại → két người
  tạo (method Transfer → **két ngân hàng**). Danh tính hợp nhất tg-id↔username
  (`identity.py`: fold dấu USER_NAMES khớp web_users; env `CASHBOX_TG_MAP` ép tay).
  Bảng duy nhất: `cashbox_transfers` (chuyển tay giữa két, văn phòng; xoá mềm admin;
  chặn rút quá số dư). Cache RAM theo stamp orders.updated_at (`service.py`). API
  `server_app/cashbox_routes.py` (`/api/cashbox*`, GET nằm trong `_NO_AUDIT`; staff
  chỉ thấy két mình); realtime `cashbox_changed` + client nghe order_changed. UI:
  `#/ket` (CashboxList + chuyển tiền) → `#/ket/:key` (CashboxDetail — timeline rail
  số dư kiểu OrderTimeline + đơn đang nằm két, badge ⏰ quá hạn nộp 17:00). Tiền RA
  khỏi hệ két = trả NCC từ két (xem purchase_store). **HƯỚNG DẪN sử dụng trong app
  (`webapp/src/guides/` + `pages/Guides.tsx`): 25 bài phủ mọi khía cạnh, nội dung
  HTML TĨNH trong `data_*.ts` (gom ở `guides/registry.ts`, render qua
  `dangerouslySetInnerHTML`). Mỗi bài = `{key,icon,title,desc,cat,routes[],sections[]}`;
  `routes` = hash-prefix trang mà bài liên quan. Danh sách `#/huong-dan` đẩy bài KHỚP
  trang đang xem lên đầu ("Trang bạn đang xem") — **nút `?` nổi (HelpFab) truyền
  `?from=<route>`**, `guidesForRoute` (types.ts) khớp prefix (tránh nuốt tiền tố như
  `#/tho`↔`#/thung`). 1 route generic `#/huong-dan/:key` → `GuideDetail`. **Thêm tính
  năng mới = thêm 1 guide vào `data_*.ts` tương ứng (tự vào app, khỏi sửa route)**;
  giữ `cat` khớp `GUIDE_CATS`. **Phân quyền XEM bài**: cờ `office`/`admin` trên guide
  (`visibleGuides`) → ẩn với staff ở danh sách + khối "Trang bạn đang xem" + chặn mở URL
  trực tiếp, kèm badge "Chỉ văn phòng/admin". CHỈ đặt cờ khi TRANG chặn hẳn staff (không
  phải chỉ ẩn nút): hiện `thu-tien`, `tien-cong` (#/tien-cong+#/luong-sp+#/bao-cao),
  `camera`. Trang mixed (ket/nhập hàng/trả hàng/hoá đơn…) KHÔNG gắn cờ — chỉ ghi chú
  action office/admin trong nội dung.**
- `usage_store/` — bảng `usage_stats` (app.db): đếm GỘP thao tác webapp theo
  (ngày, user, kind view/tap, trang chuẩn hoá, nhãn nút) — KHÔNG log thô từng cú bấm
  (tránh phình kiểu audit_events). Client tự bắt mọi click nút/link + hashchange
  (`webapp/src/usage.ts`, listener toàn cục — nhãn: title/aria/text với số→#, link
  điều hướng = "→ route"), gom buffer gửi batch 20s (`POST /api/usage/batch`, nằm
  trong `_NO_AUDIT`, offline→queue). Admin xem `#/usage` (UsageStats, menu Thêm) ←
  `GET /api/usage/stats?days=&user=` (`server_app/usage_routes.py`).
- `audit/` (+ `audit_log.py`) — audit-event DB and redaction.
- **Lịch sử thao tác — 3 mặt hiển thị, 1 bảng tra nhãn (2026-07-14).** Mọi dòng
  lịch sử có `parts: [{t, href?}]` = đoạn chữ + LINK tới thực thể được nhắc
  (thùng/SP/khách/đơn/phiếu…); `detail` = text ghép (fallback). Module:
  `server_app/history_format.py` (part/href_for/Resolver tra tên best-effort),
  **`event_format.py` = bảng tra DUY NHẤT mọi domain event → (nhãn VN, parts)**,
  `activity_format.py` (feed toàn cục: phủ MỌI scope + khử trùng request↔event
  ±15s + `_EXTRA_LABELS` cho endpoint scope=None + gộp autosave). Mặt đọc:
  `order_history.py` (đơn), `entity_history.py` (mọi thực thể — scope allowlist
  trong handler), `activity.py` (#/lich-su, peek batched/scope). **Thêm tính năng
  mới = thêm event vào `event_format.event_entry` (+nhãn `_EXTRA_LABELS` nếu
  endpoint scope=None) — không thì rơi vào nhãn generic/vô hình.** Client render
  parts: `webapp/src/detail/History.tsx` + `pages/ActivityLog.tsx`.
- **Timeline biến động ĐƠN (`server_app/order_timeline.py`)** — GET
  `/api/order/{id}/timeline` → `#/order/:id/timeline` (`pages/OrderTimeline.tsx`,
  nút ở chi tiết đơn): đời của đơn (tạo → HĐ KV → xuất kho → soạn/giao/nộp/nhận →
  từng lần thu) + rail TIỀN CÒN PHẢI THU (chấm trượt như timeline thùng). Nguồn:
  blob (5 mốc + payments = chuẩn) + audit rows; khử trùng, gộp burst.

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
    (1 row per thợ per phiếu: **worker_id → production_workers.id (danh tính bất
    biến; worker_name = snapshot)**, product_id/product_code, report_date + normalized
    `report_ymd`, so_gach/so_tru/so_cay_le/so_mam/tong_calc, note; indexed). Đổi tên
    thợ (worker_store.update_worker) CASCADE cùng transaction: mirror rows + blob
    `bang` mọi phiếu → dashboard/chi tiết thợ không tách lịch sử. Dual-written:
    `set_bang` also does delete+insert here so it's queryable for the dashboard (the `bang`
    blob stays the source for current UI reads). Has `dashboard()` + `worker_detail()`
    aggregation queries + `backfill_report_rows()`.
- `server_app/production_routes.py` — webapp API `/api/production*` (list/detail/
  catalog/create/set-product/set-target/add-number/report parse+save/delete). Create
  opens a forum topic in `PRODUCTION_GROUP_ID`. **Khoá 24h** (`server_app/production_lock.py`
  `is_locked`): phiếu >24h (hoặc `lock_override='locked'`) → cấm mọi mutation trừ admin.
  Áp CẢ web (`locked_error`) LẪN lệnh nhóm Telegram (`command_handlers/production_commands.py`
  chặn đổi SP/SX/DEL/done/nhập số/lưu báo cáo khi khoá + không phải admin Telegram;
  lệnh chỉ-đọc + tạo phiếu mới không bị chặn). **`set_sp` KHÔNG re-chốt `luong_1sp` khi
  phiếu đã có dòng báo cáo** (tránh đổi tiền công đã tính). Emits realtime `production_changed`/
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
  - **Công thức/BOM** (`recipe_store`): SP có thể cần nguyên liệu (product khác) theo tỉ lệ.
    Định nghĩa ở chi tiết SP (`detail/RecipeEditor.tsx`). Nhu cầu theo LOẠI PHIẾU: sản xuất
    = không cần NL; đóng gói = bắt buộc công thức +
    chọn đủ thùng NL mọi nguyên liệu → trừ kho (`allocate_picks kind='production'`).
  - **Phiếu BÁO CÁO SX** (`production_store/report_slips.py` + `server_app/report_slip_routes.py`,
    office-only — tiền lương): văn phòng tạo phiếu chọn khoảng ngày (`production_report_slips`);
    nội dung TÍNH LIVE mỗi lần xem (tổng SP + tiền theo THỢ, tiền TỪNG PHIẾU SX, tổng cộng —
    cây × đơn giá CHỐT theo phiếu + phụ cấp 1 lần/(phiếu, thợ)); tuỳ chọn CHỌN THỢ
    (`worker_ids` JSON id bất biến, NULL = mọi thợ — chip chọn + preset Lương tuần =
    thợ bật `weekly_salary`). UI `#/bao-cao` (`pages/ReportSlips.tsx`
    list+tạo, preset Tuần này/trước) → `#/bao-cao/:id` (`ReportSlipDetail.tsx`); xoá = admin.
    Realtime `report_slips_changed`. ⚠ GROUP BY trên cột alias (`code`) bị SQLite resolve về
    `pr.code` — luôn GROUP BY biểu thức COALESCE đầy đủ (đã sửa ở cả `compute_wages`).
  - **Bảng LƯƠNG SP** (`production_store/wages.py`): bảng `production_wages` (app.db, seed 1
    lần từ dict cứng cũ `_SEED`), `wage_per_cay` đọc qua cache module (invalidate khi ghi).
    Sửa từ webapp `#/luong-sp` (`pages/WageTable.tsx`, office) qua `server_app/wage_routes.py`
    GET/POST `/api/wages` (luong ≤ 0 = gỡ mã → về missing_wage); lưu xong emit
    `productions_changed` → tiền công/báo cáo tính lại ngay.
  - **Lương CHỐT THEO PHIẾU** (`production_slips.luong_1sp`): đơn giá /1SP CỐ ĐỊNH từng phiếu
    SX — gán/đổi SP (`queries.set_sp`) chốt từ bảng lương hiện tại (gán lại đúng SP cũ GIỮ giá
    đã sửa tay); NULL = chưa chốt → bảng lương live; backfill boot (`schema.migrate`, khớp cả
    sp_name không có product_id). Đổi bảng lương KHÔNG ảnh hưởng phiếu đã chốt. Văn phòng sửa
    riêng từng phiếu: POST `/api/production/{tid}/wage` (`set_slip_wage_handler`), UI ô "Đơn
    giá phiếu này" trong khối tiền công (`detail/ProductionWages.tsx`). MỌI chỗ tính tiền
    (compute_wages, compute_range_report, worker_detail, _phieu_wages) ưu tiên luong_1sp.
  - **Lương THEO GIỜ (2026-07-14)**: phiếu SẢN XUẤT có cột **"Giờ"** trong bảng báo cáo
    thợ (= cột 12 "số giờ TL" layout sheet — `domain.parse_report` đọc, blob `bang` +
    mirror `production_report_rows.so_gio`). Dòng có giờ → tiền = giờ ×
    `production_workers.hourly_rate` (đặt ở `#/sx-tho/:name`, office-only qua POST
    `/api/workers/{id}`) THAY cây × đơn giá. Cả 4 chỗ tính tiền xử lý; thợ có giờ chưa
    đặt đơn giá → cảnh báo `missing_hour_rate`/`giờ: <tên>`, dòng hiện 0đ + ⚠.

**Web app for phones (orders management, 5-6 internal users)**
- `webapp/` — Vite + Preact + TS mobile UI (Vietnamese). Hash router `main.tsx`, nav
  bottom **📋 Đơn · 👤 Khách · ➕ Tạo · 🏭 SX · 📦 Kho** + ⚙️ cài đặt ở top bar
  (đăng xuất; kèm `TaskBell` badge việc-của-tôi + chuông thông báo). Dashboard Đơn:
  view-slider 4 ô (chi tiết/gọn/siêu gọn/**📅 lịch giao**). Menu ☰ Thêm có **Việc**. Trang: orders list/detail, tasks, payments, comments, create order,
  **sửa hoá đơn = trang riêng `pages/OrderInvoiceEdit.tsx` (`#/order/:id/hoa-don`,
  2 TAB như trang tạo đơn, cùng mount: ⚡ Nhanh = sửa TEXT + preview parse, lưu qua
  `/api/order/fix` [text sửa → nhận diện lại khách, cảnh báo nếu đổi; text nguyên →
  preview theo khách hiện tại, Lưu khoá]; 📋 Nâng cao = ① Khách hàng [nợ KV + bảng
  giá + Đổi khách qua `/api/order/assign-customer`] → ② InvoiceEditor lấy giá theo
  khách bước 1 — đổi khách là editor xoá cache giá bảng, tra lại; KHOÁ nếu đã có HĐ
  KiotViet; popup bảng giá dùng chung `detail/PriceListModal.tsx`; chế độ gõ chia
  đôi màn dùng chung `ui/useTypingSplit.ts` với CreateOrder)**,
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
  `add_payment`/`delete_payment_record` (`api_helpers/payment_core.py`) now RMW inside
  `transaction()` via `_save_order` (no more bare-commit `_save`); when there's a long
  await (KiotViet/Telegram) in the middle, RE-READ the blob fresh inside a short
  `transaction()` after the await and patch only the changed field — see
  `_process_payment_core` (`order_commands_v3.py`), `on_comma_invoice`/`detect invoice`,
  and `mirror_channel.sync_order_to_mirror` for the pattern. The previously-listed
  bare-RMW offenders (v3 `on_comma_invoice`/`vat`/`pvc`/`fix`/`bo no`/`detect invoice`,
  `mirror_channel`, `bot_flows/invoice_create._save_order_field`) are all wrapped now.
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
