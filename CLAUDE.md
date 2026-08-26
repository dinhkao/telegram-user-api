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
- **GIÁ MẶC ĐỊNH KHI PARSE HOÁ ĐƠN = GIÁ MUA LẦN GẦN NHẤT (2026-08-10,
  `order_store/last_prices.py`)** — thứ tự ưu tiên: **giá gõ tay trong text** >
  **giá khách đó đã mua lần gần nhất** > **bảng giá** (riêng đè chung) > 0.
  `last_order_prices(conn, kh_id)` quét 30 đơn gần nhất của khách (chưa xoá, sắp theo
  `order_created`) — lọc qua **cột generated `cust_key`** (= coalesce khach_hang_id/khID)
  + `idx_orders_cust_created`, xem `orders_db.ensure_orders_stats_columns`; viết thẳng
  biểu thức `json_extract` là QUÉT TRỌN BẢNG (khách chưa mua bao giờ ~70ms CHẶN event
  loop, mỗi 60s 1 lần lúc đang gõ). DB chưa có cột → tự rơi về biểu thức gốc, cùng kết
  quả. Lấy giá > 0 của lần XUẤT HIỆN
  ĐẦU (đơn mới nhất thắng); khớp SP theo `sp_id` rồi tới mã + alias mã cũ → key là MÃ
  HIỆN HÀNH. Cache RAM 60s/khách (parse chạy mỗi lần gõ ở trang tạo đơn), `_save_order`
  bỏ cache của khách đó. Dùng bởi CẢ 2 parser (`free_text.parse_invoice_free_text`,
  `comma_parser.parse_comma_text`) ⇒ mọi đường tạo/sửa hoá đơn bằng text (tạo đơn tab
  ⚡ Nhanh + preview, auto_parse, `fix`, lệnh `,` Telegram) đều theo luật này. Tab
  📋 Nâng cao cùng luật: `/api/customer/price` trả thêm `last_price`, `InvoiceEditor`
  tự điền nó (chú thích/nút đặt-lại vẫn theo bảng giá, nhãn "✓ lần trước").
  ⚠ Giá đơn là snapshot vĩnh viễn → sửa lại text của CHÍNH đơn đó sẽ lấy lại giá của
  chính nó (đơn gần nhất của khách chính là nó) — muốn về giá bảng thì gõ giá tay.
  Tests: `tests/test_last_prices.py`.
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
- **NỢ QUÁ HẠN (`server_app/debt_alert.py` + `debt_alert_daily.py`, 2026-07-28)** —
  khách ĐÃ GIAO HÀNG mà chưa trả tiền quá N ngày. Luật: đơn còn nợ theo đúng lọc
  trang thu tiền (`order_api_collect._owing_remaining`, bỏ đơn `bypass_debt`) +
  **phải giao xong** (mốc = `task_status.giao_hang.at`, đơn cũ lùi về `created`),
  ngày đếm theo giờ VN; gom theo khách: `days` = đơn quá hạn lâu nhất,
  `order_count`/`total` = CHỈ các đơn đã quá ngưỡng. **Chỉ đơn tạo TỪ
  `DEBT_ALERT_SINCE`** (mặc định 2026-07-01, ngày VN — như `CASHBOX_SINCE` của
  két; đơn thiếu `created` coi như cũ → bỏ). GET `/api/debt-alerts?days=N`
  (văn phòng) → `#/no-qua-han` (`pages/DebtAlerts.tsx`, chip 1/3/7/15 ngày).
  `debt_alert_daily.debt_alert_loop` (spawn ở bootstrap, nhịp 10ph) mỗi ngày từ
  `DEBT_ALERT_HOUR` (mặc định 8h VN) đẩy **1 thông báo/khách** qua
  `server_app.notify.push_bg` (chuông trong app + FCM), type `debt` → NotifCenter
  mở `#/order/<tid>/thanh-toan`; quá `DEBT_ALERT_MAX_PUSH` (8) gộp phần dư 1 dòng.
  Chống nhắc trùng/khi restart: ngày đã gửi lưu `kv_store['debt_alert_state']` —
  đúng 1 lượt/ngày. Tests: `tests/test_debt_alert.py`.
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
  `orders_db.ensure_orders_stats_columns` (PG already has these). Cùng chỗ đó còn
  `cust_key` + `idx_orders_cust_created` = đơn CỦA 1 KHÁCH mới-nhất-trước (cho
  `order_store/last_prices.py` — xem mục giá mua lần gần nhất). Search uses a
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
  thao tác** with a thumbnail), and an **FCM push** (`server_app/fcm.py` — gửi THEO
  TOKEN từng máy, bảng `fcm_tokens` trong `notif_store/fcm_tokens.py`, APK đăng ký
  qua `POST /api/fcm/register` [cầu JS `AndroidApp.fcmToken()`, client
  `webapp/src/fcmRegister.ts`]; lọc bỏ role `chat_luong` + user khoá; topic `orders`
  chỉ còn là FALLBACK cho máy APK cũ — tắt bằng `FCM_TOPIC_FALLBACK=false` khi mọi
  máy đã cập nhật) — same as new comments (`comment_routes`). Tapping a push **deep-links**
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
  **`prod_mam` = số CÂY trên 1 mâm** (báo cáo SX: `tổng = cây/mâm × số mâm + lẻ`,
  `production_store/domain.compute_report`) — ⚠ chú thích ở `bot_core/config.py::SP_INFO`
  ghi "số mâm trong 1 chảo" là SAI so với cách code dùng. Sửa 2 số này ở **chi tiết SP
  `#/kho/:code`** (2 ô "Số cây / 1 mâm" + "Lượng 1 mẻ", `POST /api/products/{code}`
  {prod_mam, prod_luong} — **CHỈ văn phòng** vì ra tiền công; rỗng/0 = xoá về NULL;
  ô là `type=text inputMode=decimal` để gõ "3,5" kiểu Việt được).
  Đổi số CHỈ áp cho phiếu SX gán mã SAU ĐÓ — `set_sp` đã snapshot `production_slips.sp_mam`.
  Tests: `tests/test_product_prod_nums.py`.
  Plan: `docs/plan-product-id.md`.
- **VAI ĐƠN VỊ (2026-07-17, plan: `docs/plan-don-vi-hang-hoa.md`).** SP có 1 đơn vị
  GỐC (`products.unit` — mọi số trong DB) + đơn vị phụ quy đổi (`product_units`).
  3 cột vai trên `products` (`bulk_unit_id`/`display_unit_id`/`stocktake_unit_id`:
  NULL = không · 0 = đơn vị gốc · >0 = product_units.id; resolve
  `product_store/units.py::unit_role/role_by_code`; UI = 3 dòng chip trong khối Quy
  đổi đơn vị `ProductUnits.tsx`, office; xoá đơn vị đang giữ vai bị CHẶN):
  - **📦 NGUYÊN KIỆN**: nhập bằng đơn vị này → 1 kiện = 1 dòng thùng quantity=factor,
    nhãn chứa = tên đơn vị (`unit_label`), khỏi chọn inventory_units. Rule chung
    `bulk_label_for_qty` (1 dòng ≤ 1 kiện) áp CẢ 3 đường tạo thùng: nhập NCC
    (`purchase_goods` — server tự resolve vai), phiếu SX (`inventory_routes`, thay
    nhánh self-container cũ — factor 1 giữ nguyên hành vi; recipe API trả
    `bulk_unit`), hàng trả (`return_goods` TỰ TÁCH 75→2×30+15). **`self_container`
    giờ DERIVE từ vai 📦** (hết suy từ tên đơn vị thùng/kiện; backfill 1 lần marker
    `migrate/unit_roles_v1`); gate rã kiện `return-material` theo đó.
  - **👁 HIỂN THỊ**: BoxTile quy đổi SỐ trên ô thùng (chia hết → nguyên, lẻ → 1 chữ
    số + nhãn đơn vị nhỏ, tooltip kép "90 cây = 3 Thùng"); fill + MỌI Ô NHẬP giữ gốc.
  - **📋 KIỂM KHO**: phiếu kiểm snapshot (tên, factor)/dòng lúc tạo/resync
    (`stocktakes._stamp_count_units`), nhập kép [N kiện]+[M lẻ] → `actual_quantity`
    quy về gốc + lưu số thô `counted_bulk/loose` cho audit; apply/hao hụt NL đọc gốc
    như cũ. Tests: `tests/test_unit_roles.py` + case bulk trong
    test_purchase_goods/test_return_goods/test_stocktakes.
- `user_store/` — `web_users` table in `app.db`: login accounts for the orders web
  app (PIN hash in `pin.py`, CLI: `tools/add_web_user.py`).
- `comment_store/` — `web_comments` table in `app.db`: web-app comments on orders
  (separate from `order_chat_messages` = read-only Telegram log).
- **`salary_store/` — LƯƠNG THÁNG (`app.db`, 2026-07-18, office-only).** Bảng lương
  từng tháng cho mọi NV. `production_workers.wage_type` phân loại NV: `'product'`
  (lương SP tự tính từ sản xuất theo tháng qua `report_slips.compute_range_report` —
  **ĐÃ GỒM phụ cấp ghi trong PHIẾU SX** `production_allowances`; row trả riêng
  `pc_phieu` = phần phụ cấp phiếu đã gộp đó để UI tách dòng [ô Lương có dấu ⁺ +
  popup tab Lương], KHÁC cột `phu_cap` = phụ cấp THÁNG `salary_allowances` — đừng
  cộng 2 lần. ⚠ phụ cấp phiếu của thợ `'time'` KHÔNG vào bảng lương: compute chỉ
  truyền `worker_ids` là thợ SP)
  | `'time'` (lương THỜI GIAN từ CHẤM CÔNG 2026-07-19: mốc tháng ÷ 26 × ngày công +
  tăng ca ×1,2 — công/TC quy từ
  máy chấm qua `attendance_store.month_worker_stats`/`domain.work_stats`, ngày đủ 2 ca
  = 1 công, đã gộp giờ sửa tay; sửa mốc = ô "Mốc" bảng lương, office)
  | **`'time_flat'` = TG\* (2026-07-30)**: CỐ ĐỊNH theo ngày công — giờ tăng ca GỘP LUÔN
  vào ngày công (`cong = (work_min + ot_min)/480`) rồi trả bằng đơn giá công, `luong_tc`
  = 0 (`ot_gio` vẫn trả để biết đã gộp bao nhiêu; UI: ô Công có dấu `+TC`, ô L.TC "—").
  ⚠ Thêm giá trị wage_type mới phải sửa **cả whitelist `worker_store.update_worker`**
  (giá trị lạ bị ép về 'product' — âm thầm) LẪN validate `server_app/worker_routes.py`;
  client gom nhãn/luật ở **`webapp/src/detail/wageType.ts`** (`isTimeWage`/`otInCong`/
  `wageChip`/`wageLabel`/`nextWageType` — chip Loại bấm đổi VÒNG SP→TG→TG*).
  **MỐC lương lưu THEO TỪNG THÁNG (2026-07-30, `salary_store/moc.py` + cột
  `salary_month.monthly_salary`, tests/test_salary_moc.py)**: mốc hiệu lực của tháng M =
  bản đặt gần nhất có tháng ≤ M (đặt tháng nào áp TỪ THÁNG ĐÓ TRỞ ĐI, tháng sau tự kế
  thừa), chưa đặt bao giờ → `production_workers.monthly_salary` (mốc mặc định hồ sơ,
  dữ liệu cũ). Sửa mốc KHÔNG tính lại tháng trước (trước đây 1 số chung → sửa là đổi
  cả quá khứ đã trả tiền). Ghi qua `/api/payroll/adjust {monthly_salary}` (0 = bỏ mốc
  riêng tháng này); row trả thêm `moc_ym`/`moc_own` để UI nói rõ nguồn (dấu ↩ = kế
  thừa). Ô Mốc bấm mở tab "moc" của `PayrollCellPopup`: sửa mốc + **TRAO ĐỔI gắn theo
  THỢ** (`entity_media` scope `worker_moc`, entity_id = worker_id → CÙNG luồng ở mọi
  tháng; scope nằm trong `_OFFICE_ONLY_SCOPES` nên staff 403 cả xem lẫn ghi, và
  `Comments allowPin={false}` để số lương không ghim lên bảng tin chung).
  **4 ô Mốc / P.cấp / Ứng / BHXH đều có khung trao đổi XUYÊN THÁNG** — scope
  `worker_moc` · `worker_pc` · `worker_ung` · `worker_bhxh`, entity_id = worker_id
  (KHÔNG kèm tháng), tất cả office-only.
  Bảng `salary_month`
  (thưởng + ghi chú + `weekly` = nhận-lương-tuần THEO THÁNG — mỗi (tháng, thợ) độc
  lập, KHÁC `production_workers.weekly_salary`) + `salary_advances` (ỨNG lương NHIỀU
  lần/tháng) + `salary_allowances` (PHỤ CẤP NHIỀU KHOẢN/tháng — amount + nhãn, cộng
  dồn; giống ứng). `compute_month_payroll(ym)`: thực lãnh = lương + phụ cấp (Σ khoản)
  + thưởng − ứng − **BHXH**. ⚠ **TỔNG cột Lãnh CHỈ cộng thợ DƯƠNG** (2026-08-05):
  tổng = tiền THỰC phải chi; thợ âm (ứng/BHXH vượt lương) tháng này nhận 0 và nợ lại,
  cộng cả âm là tổng ra thiếu → rút quỹ theo đó là hụt tiền. Phần âm gom riêng ở
  `totals.thuc_lanh_am` + `am_count` (hiện ở thanh tóm tắt + dấu `*` ở chân bảng) để
  không mất dấu. Luật này có ở CẢ server lẫn `detail/PayrollTable.tsx::sumLanh` —
  lệch 1 bên là chân bảng khác thanh tóm tắt.
  `weekly` (nhận lương tuần) bật → ứng tự động += lương
  của tháng **TRƯỚC khi trừ ẩn**. ⚠ Lương tuần áp cho **CẢ lương SP LẪN lương THỜI
  GIAN** (Duy chốt 2026-08-05) — thợ TG bật cờ này thì lương thời gian cũng khử hết,
  đúng ý đồ. Phải lấy lương TRƯỚC trừ ẩn, lấy lương sau-trừ thì 2 số khử nhau
  ((L−T)−(L−T)=0) → gõ trừ ẩn cho thợ lương tuần mà thực lãnh đứng im, không báo gì.
  **TRỪ BHXH (2026-08-04, `salary_store/bhxh.py` + cột `salary_month.bhxh`,
  tests/test_salary_bhxh.py)**: khoản TRỪ hằng tháng, cùng luật KẾ THỪA THEO THÁNG với
  mốc lương (đặt tháng nào áp TỪ THÁNG ĐÓ trở đi, tháng sau tự kế thừa, tháng trước
  KHÔNG đổi; chưa đặt bao giờ = 0). ⚠ KHÁC mốc ở số 0: mốc dùng 0 = "bỏ đặt riêng",
  còn ở đây **0 là số CÓ NGHĨA** ("từ tháng này thôi trừ") → API `/api/payroll/adjust`
  phân biệt bằng `"bhxh" in body` (vắng = giữ nguyên · số ≥ 0 = đặt riêng · **null =
  bỏ đặt riêng**), đừng đổi sang `.get() is not None`. Row trả `bhxh`/`bhxh_ym`/
  `bhxh_own` (↩ = kế thừa) như bộ `moc_*`.
  **NGÀY CÔNG GÕ TAY + SỐ TRỪ ẨN (2026-08-05, cột `salary_month.cong_override` /
  `.tru_an`, ô nhập ở `detail/PayrollQuickEdit.tsx`)**: 2 ô nhập nằm TRONG popup ô
  bảng lương (`PayrollCellPopup`) — tab **Công** có ô gõ thẳng số ngày công **ĐÈ** số
  quy từ máy chấm (máy hỏng/quên chấm/công thoả thuận; `cong_auto` = số máy giữ lại để
  đối chiếu, `cong_manual` = đang đè, dấu ✎ trên ô bảng, nút "Bỏ ghi đè" quay về số
  máy) — đè NGAY tại nguồn nên **mọi thứ ăn theo công chạy theo**: lương ngày công,
  thưởng vệ sinh, phụ cấp đơn-giá×ngày, số in trên phiếu. Tab **Lương SP** có ô **SỐ
  TRỪ ẨN**: trừ thẳng vào lương sản phẩm, **phiếu lương in cho thợ KHÔNG có dòng/lý do
  nào** (chỉ thấy lương SP đã trừ), bảng lương của văn phòng thì hiện dấu ▾ + dòng
  "Trừ ẩn" trong popup. ⚠ Phụ cấp **%** tính trên `luong_goc` (lương TRƯỚC khi trừ ẩn)
  → tác động lên thực lãnh đúng BẰNG số đã nhập, không nhân thêm hệ số; trừ quá lương
  thì kẹp ở 0 (không cho lương âm). API: `/api/payroll/adjust {tru_an}` (0 = bỏ) và
  `{cong_override}` (**như bhxh**: số ≥ 0 = đặt · null = bỏ ghi đè · vắng = giữ nguyên
  → ghi qua `salary_store.set_cong_override`, KHÔNG nhét vào `set_month_adjust` vì ở
  đó `None` đã mang nghĩa "giữ nguyên"). Cả 2 **KHÔNG kế thừa** sang tháng sau.
  Tests: `tests/test_salary_store.py`.
  **LƯƠNG CHỜ HÀNG (2026-08-05, cột `salary_month.cho_hang`)**: tiền trả cho thời gian
  thợ ngồi chờ nguyên liệu/hàng về — khoản **CỘNG**, văn phòng **bấm thẳng vào ô** cột
  "Chờ hàng" của bảng lương để gõ số (1 số/tháng nên KHÔNG dùng panel nhiều khoản như
  phụ cấp/ứng; thao tác dùng chung `detail/payrollActions.ts::editChoHang`). Ghi qua
  `/api/payroll/adjust {cho_hang}` (0 = xoá; vắng field = giữ nguyên). **KHÔNG kế thừa**
  sang tháng sau (giống `weekly`/2 cờ thưởng, KHÁC mốc/BHXH). Đã vào `thuc_lanh` +
  `totals.cho_hang` + phiếu lương in. Tests: `tests/test_salary_store.py`.
  **2 khoản THƯỞNG bật/tắt (2026-08-04, `salary_store/bonus.py` + cột
  `salary_month.thuong_cc`/`.thuong_vs`, tests/test_salary_bonus.py)**: CHUYÊN CẦN =
  cố định `THUONG_CHUYEN_CAN` (200k); VỆ SINH = `THUONG_VE_SINH_MOI_NGAY` (12k) ×
  ĐÚNG số `cong` đang hiện ở cột Công. Đổi mức = sửa 2 hằng số đó (chưa có màn hình
  cấu hình). ⚠ 2 cờ này **KHÔNG kế thừa** sang tháng sau (giống `weekly`, KHÁC
  mốc/BHXH) — cố ý: thưởng là quyết định từng tháng, bò sang tháng sau là trả thừa
  âm thầm. Row trả `cc_on`/`vs_on` (cờ) + `thuong_cc`/`thuong_vs` (tiền, đã vào
  `thuc_lanh`). API
  `server_app/payroll_routes.py` (`/api/payroll/month|adjust|advance*|allowance*`,
  gồm `allowance/{id}/print-note` = **CHỮ IN TRÊN PHIẾU** của khoản phụ cấp — cột
  `salary_allowances.print_note`: có chữ thì phiếu lương in ĐÚNG chữ đó và KHÔNG kèm
  công thức (nội dung nội bộ + "10% lương gốc" không lộ cho thợ), rỗng = in nội dung
  khoản + công thức như cũ. Ô nhập ở `ui/MoneyEntryForm` (prop `printNote`, chỉ phụ
  cấp truyền), sửa sau bằng nút 🖨 ở CẢ 3 chỗ hiện khoản (EntryPanel · trang
  `#/nhap-phu-cap` view Thẻ · view Bảng `EntryTable`),
  TẤT CẢ chặn `office_user`). Khoản đã ghi: **VÔ HIỆU** (`.../{id}/void`, kèm lý do)
  hoặc **SỬA GHI CHÚ** (`.../{id}/note` — SỐ TIỀN/ngày BẤT BIẾN, sai tiền thì vô hiệu
  rồi ghi lại; khoản đã vô hiệu khoá luôn ghi chú). UI `MonthlyPayroll.tsx`
  (`#/luong-thang`, view Bảng/Thẻ — **2 view đều tách file riêng**: Bảng =
  `detail/PayrollTable.tsx`, Thẻ = `detail/PayrollCard.tsx` (trần 400 dòng);
  **Ô TÌM THỢ ghim (sticky) dưới app-bar** — không dấu (`foldVN`), lọc cho CẢ 2 view,
  dòng TỔNG của bảng cộng theo thợ ĐANG HIỆN + hiện "n/N" (thanh tóm tắt trên cùng
  vẫn là tổng CẢ THÁNG, cố ý). Thanh tiêu đề bảng ghim NGAY DƯỚI ô tìm nhờ biến CSS
  `--pr-search-h` = chiều cao thật của hàng tìm, do trang đo bằng ResizeObserver —
  đừng thay bằng hằng số px, đổi cỡ chữ là lúc hở lúc chồng;
  **SẮP XẾP bấm tiêu đề cột** = `detail/payrollSort.ts` (`COLS` là NGUỒN DUY NHẤT của
  nhãn/tooltip 14 cột — thứ tự phải khớp `<td>` thân bảng LẪN mảng `COL_EM` colgroup;
  cột Thợ GHIM trái nên `COL_EM[0]` hẹp lại ở mobile qua hook `useNarrow`
  (matchMedia 720px — width nằm inline trên `<col>`, CSS media query KHÔNG đè được);
  **`COL_EM` đo bằng Playwright** với nội dung dài nhất có thể + 0,35em đệm — tổng
  101,9em ≈ 1304px để LỌT màn 1366px không phải cuộn (đệm ngang ô `.pr-table td`
  cũng đã hạ 9px→6px cho đủ chỗ); sửa cột nào phải đo lại cột đó;
  **2 NGUỒN LƯƠNG là 2 CỘT RIÊNG** (2026-08-04): `luong_tg` = lương THỜI GIAN (công +
  tăng ca) · `luong_sp` = lương SẢN PHẨM; mỗi thợ chỉ ăn 1 trong 2 nên
  `luong_tg + luong_sp == luong`, cột kia hiện "—" (3 cột cũ L.công/L.TC/Lương gộp
  lại còn 2 — chi tiết công/TC vẫn xem trong popup của ô);
  bấm: sắp → đảo chiều → bỏ sắp, cột số lớn-trước, cột Thợ A→Z theo `localeCompare('vi')`,
  nhớ ở localStorage `payroll_sort`, áp cho CẢ view Thẻ; dòng TỔNG ở tfoot không đổi chỗ);
  **bấm ô TÊN → POPUP hồ sơ lương (`detail/PayrollWorkerPopup.tsx`, ở NGAY trang bảng
  — không rời trang rồi phải back + tải lại; nút ↗ trong popup mở thành TRANG
  `#/luong-thang/:worker_id?ym=`
  = `pages/PayrollWorker.tsx` + `detail/PayrollWorkerSheet.tsx` = HỒ SƠ LƯƠNG THÁNG** (**MỌI khối đều GẬP được** — Lương/Chấm công mặc định ĐÓNG,
  các khối tiền ngắn Thưởng/Phụ cấp/Ứng/BHXH mặc định MỞ; tiêu đề luôn hiện TỔNG, lối
  sang tab sửa nằm ở dòng "›" cuối phần đã bung. Hàm gộp dòng báo cáo SX tách ra
  `detail/payrollWageRows.ts` cho file dưới trần 400 dòng; hàng vừa thao tác ở bảng/thẻ/pivot được TÔ SÁNG
  giữ nguyên sau khi đóng popup để khỏi lạc chỗ):
  thực lãnh + thanh tỉ lệ cộng/trừ, nguồn lương [SP: view **CHI TIẾT = từng PHIẾU SX của
  từng NGÀY kèm tiền mỗi phiếu** HOẶC **theo NGÀY**, từ `getWorkerReport` — view "theo mã
  SP" cũ BỎ 2026-08-04 · TG mốc→công→tăng ca], **CHẤM CÔNG luôn hiện cho MỌI thợ** (khối
  "Chấm công" = tổng công/TC + từng ngày qua `detail/AttendanceDays.tsx`, dùng chung với
  `#/cham-cong/:id`; view "Theo ngày" của thợ SX còn GHÉP công/giờ chấm vào từng ngày →
  thấy ngay ngày đi làm mà chưa có báo cáo SX, hoặc có báo cáo mà quên chấm),
  TỪNG khoản phụ cấp + TỪNG lần ứng, cảnh báo ứng vượt lương — CHỈ ĐỌC, mỗi khối bấm mở `PayrollCellPopup` đúng tab để sửa nên không
  có editor thứ 2; 3 thao tác hồ sơ [đổi loại lương/lương tuần/mốc] dùng chung
  `detail/payrollActions.ts`)
  + `AdvanceEntry.tsx` (`#/nhap-ung` nhập ứng nhanh); ☰ Thêm
  → nhóm **Lương**. Tests: `tests/test_salary_store.py`. (Khác `production_allowances`
  = phụ cấp per-PHIẾU SX; đây là lương theo THÁNG.)
  **PHIẾU LƯƠNG THÁNG IN GIẤY (2026-08-05)** — nút "In phiếu" ở đầu popup hồ sơ lương
  thợ (`PayrollWorkerPopup`) + trang `#/luong-thang/:id` → tab mới
  `GET /api/payroll/payslip-html?ym=&worker_id=` (`server_app/payslip_routes.py`,
  office-only). Khổ giấy = HOÁ ĐƠN KiotViet của đơn (body 280px, `@page 76mm auto`).
  3 khối: bảng tiền → THỰC NHẬN · CHẤM CÔNG từng ngày (4 mốc giờ chia theo BUỔI + giờ
  công + giờ TC, đủ mọi ngày của tháng, tháng đang chạy dừng ở hôm nay) · ỨNG LƯƠNG
  từng lần, cuối phiếu in TÊN cỡ lớn. ⚠ Phiếu KHÔNG in mốc lương và KHÔNG in dòng
  "trong đó phụ cấp phiếu SX" — 2 số đó là số nội bộ / đã nằm TRONG dòng lương,
  in ra thành dòng tiền riêng là cộng dọc phiếu sai. Luật phiếu: **mọi dòng tiền
  in ra đều là khoản cộng/trừ thật, cộng dọc phải ra đúng THỰC NHẬN** (test khoá). Nút **🖨 In phiếu** nổi góc dưới-phải gọi
  `window.print()` + **thanh CHUYỂN THỢ** trên đầu (chip tên mọi thợ của tháng, in
  xong 1 người bấm sang người kế) — cả hai ẩn trong `@media print`. href của chip do
  JS dựng từ CHÍNH URL đang mở (chỉ đổi `worker_id`) nên giữ nguyên tháng + token và
  **token không bị nhúng vào HTML**; khung chip cao tối đa ~3 hàng rồi cuộn, tự kéo
  tên đang xem vào tầm mắt. ⚠ Phiếu **KHÔNG tính lại tiền** — lấy nguyên
  dòng `compute_month_payroll` nên luôn khớp bảng lương; giờ công quy bằng
  `attendance_store.domain.work_stats` (cùng luật CN = tăng ca). Nội dung thuần =
  `salary_store/payslip.py` (tests: `tests/test_payslip.py`, có test "cộng mọi dòng =
  THỰC NHẬN"), vẽ HTML = `renderers/phieu_luong_thang.py`. (Khác `#/in-luong` =
  phiếu lương TUẦN theo sản xuất, `renderers/phieu_luong.py`.)
  **PHỤ CẤP TỰ ĐỘNG theo ghi chú báo cáo (`production_store/allowance_auto.py`)**: bảng
  `RULES` = (tên thợ đã bỏ dấu, từ khoá ghi chú, **mốc**) → phụ cấp = tiền SP của mốc đó
  trong CÙNG phiếu. Mốc 2 kiểu: **SỐ = HẠNG** (0 = cao nhất bảng, 1 = cao nhì…) hoặc
  **CHỮ = TÊN 1 THỢ ĐÍCH DANH** (Tâm "vô kẹo" + Tâm/Vĩ việc DỪA → bằng tiền **Trọng**,
  vì Trọng lúc hạng 3 lúc hạng 4 nên hạng không tả được; thợ mốc VẮNG MẶT trong phiếu →
  không ghi gì, giữ nguyên số cũ). Việc DỪA gom ở hằng `_DUA` = 3 cách ghi cùng 1 việc
  ("rắc cơm dừa" · "rắc dừa" · "gắn dừa") — ⚠ `"rac com dua"` KHÔNG chứa chuỗi
  `"rac dua"` nên phải liệt kê cả hai. Cùng việc dừa nhưng mốc theo NGƯỜI: Tâm/Vĩ =
  Trọng, Duy = cao nhì (Duy chốt 2026-08-05). ⚠ Tên phải là **TÊN ĐẦY ĐỦ** đúng như `production_workers`
  ("bao xuyen", KHÔNG tách "bao"/"xuyen" — tách ra thì thợ trượt hết rule mà "Bảo" lại là
  người khác), và từ khoá phải khớp ĐÚNG chữ thợ hay ghi (Thủy Đặng ghi "vít kẹo" chứ
  không phải "quậy kẹo"; Bảo Xuyên từ 21/7 đổi sang ghi "vít" nên rule của cô ấy có CẢ
  2 từ khoá). ⚠ **HẠNG ĐI THEO NGƯỜI, KHÔNG theo việc** — cùng ghi "vít" mà Kim hạng 0
  còn Thủy Đặng/Duy hạng 1; thợ đổi việc thì THÊM TỪ KHOÁ vào rule sẵn có của họ, đừng
  tạo rule mới hạng khác (Duy chốt 2026-08-04, có bằng chứng: văn phòng trả tay Bảo Xuyên
  đúng số hạng 0 cho phiếu #40998). Rule CHỈ áp lúc **lưu báo cáo** (`set_bang`) → sửa `RULES` KHÔNG
  tự tính lại phiếu cũ; chạy bù bằng `tools/backfill_auto_allowances.py --from --to`
  (mặc định CHẠY THỬ in ra, `--apply` mới ghi; tôn trọng số văn phòng nhập tay). Logic
  thuần = `compute_auto_allowances`, dự tính 1 phiếu = `plan_auto_allowances` (chỉ đọc).
  Tests: `tests/test_allowance_auto.py`.
  ⚠ **KHOẢN ứng/phụ cấp HIỆN Ở 2 CHỖ — sửa gì phải đồng bộ CẢ HAI**: (1) 2 trang nhập
  `pages/AdvanceEntry.tsx` + `pages/AllowanceEntry.tsx` (`#/nhap-ung`, `#/nhap-phu-cap`
  — mỗi trang có 2 kiểu xem **Thẻ / Bảng** (`detail/useEntryView.ts` nhớ theo trang);
  view **Bảng dùng chung `detail/EntryTable.tsx`**: cột Thợ/Ngày/Số tiền/Nội dung/Tạo,
  **bấm tiêu đề để sắp xếp** [sắp → đảo chiều → bỏ sắp, nhớ localStorage], dòng vô hiệu
  gạch ngang + lý do, dòng "lương tuần tự động" không sửa/vô hiệu được, chân bảng =
  tổng khoản CÒN HIỆU LỰC),
  (2) panel `detail/EntryPanel.tsx` — dùng cho popup ô P.cấp/Ứng của bảng lương tháng
  LẪN view Thẻ. Cùng dữ liệu, cùng API; thêm nút/cột/thông tin dòng ở 1 bên mà quên bên
  kia là người dùng thấy tính năng "lúc có lúc không". **Ô NHẬP TIỀN của CẢ HAI = `ui/
  MoneyEntryForm.tsx`** (ô to hết chiều ngang + dấu chấm nghìn khi gõ + dòng ĐỌC LẠI
  bằng chữ "1 triệu 500 nghìn" + chip cộng nhanh +10k…+1tr + chip gợi ý nội dung) —
  cần ô nhập tiền ở chỗ khác thì dùng lại nó, đừng quay về `<input class="pw-input">`
  rộng 82px (gõ tiền triệu trên điện thoại sai số 0 như chơi).
- **`attendance_store/` — CHẤM CÔNG máy Ronald Jack (`app.db`, 2026-07-19).** Collector
  Windows (PC văn phòng, task 30ph/lần, SDK ZKTeco) đọc máy chấm công LAN rồi đẩy batch
  qua Tailscale vào `POST /api/attendance/events` (`server_app/attendance_routes.py` —
  bearer token RIÊNG của máy, env `ATTENDANCE_BEARER_TOKEN`, so constant-time; miễn
  web_auth ở middleware + miễn audit). Bảng `attendance_events` = RAW punch bất biến,
  `event_id` SHA-256 PRIMARY KEY → idempotent (batch trùng/retry vẫn 2xx, chỉ 2xx SAU
  commit); `attendance_employee_map` map mã NV trên máy → `production_workers.id`
  (POST `/api/attendance/map` backfill event cũ; mã chưa map = hàng chờ `unmapped` trong
  GET `/api/attendance/summary?ym=`). XEM mở cho MỌI người dùng đăng nhập (2026-07-22:
  summary + day + today-image; trang `#/cham-cong` staff chỉ xem); SỬA (map, manual
  add/delete, suppress) + GET list/map vẫn office. **Trang CHẤM CÔNG 1 THỢ 1 THÁNG =
  `#/cham-cong/:worker_id?ym=` (`pages/WorkerAttendance.tsx`)** — vào từ bảng lương
  (ô Công/TC, hồ sơ lương thợ); tóm tắt công/TC + từng ngày, bấm ngày mở popup giờ
  DÙNG CHUNG với bảng cả xưởng (`detail/AttendanceCellEditor.tsx`). Số công/TC trên
  app tính bằng `detail/attendanceStats.ts::workStats` = GƯƠNG của `domain.work_stats`
  — đổi luật phải đổi CẢ HAI, không thì app lệch số tính lương.
  ⚠ **ĐI LÀM CHỦ NHẬT = TĂNG CA TOÀN BỘ** (2026-08-04): ngày CN không sinh ngày công
  nào, mọi phút có mặt vào `ot_min`. `work_stats(times, ymd)` phải được TRUYỀN NGÀY mới
  biết là CN (thiếu ymd = tính như ngày thường, giữ hành vi cũ) — chỗ gọi:
  `attendance_store.store.month_worker_stats`, client `AttendanceDays` +
  `PayrollCellPopup`. Lưu ý loại **TG\*** gộp TC vào công nên luật này KHÔNG đổi tiền
  của họ; chỉ thợ **TG** mới được trả CN theo đơn giá tăng ca ×1,2. Luật thuần
  `domain.py` (validate batch + token). Tính LƯƠNG/ca từ raw CHƯA làm (nối vào
  `salary_store` wage_type 'time' sau — đừng suy ca từ punch đầu/cuối khi chưa chốt luật).
  KHÔNG sửa phía collector từ repo này (máy Windows riêng). Tests:
  `tests/test_attendance_store.py`.
- `inventory_store/` — kho thùng (`app.db`). Bảng:
  - `inventory_boxes` (`schema.py`+`queries.py`): 1 row = 1 thùng vật lý. Mã thùng =
    **SỐ GỌI TOÀN KHO, xoay vòng 27 BLOCK** (mở rộng 2026-07-17): `001`–`999` →
    `A001`…`A999` → `B001` … `Z999` rồi quay về 001 (`domain.next_call_numbers`, MAX
    26.973; tiếp từ số cấp gần nhất, nhảy qua số của thùng còn hàng/vô hiệu — ngoài
    kho hô "thùng 347"/"thùng A047"; bản đồ `#/so-thung` vẽ theo block đã dùng).
    Số TÁI DÙNG khi thùng hết hàng → `box_code`
    KHÔNG unique; danh tính bất biến = `id` (lịch sử/link đều theo id). Mã cũ kiểu
    `K2L-001`/base36 vẫn parse (`code_call_number`) + chiếm số tới khi xuất hết.
    Pool tồn gom theo `product_code`. Cột:
    `quantity`, `mfg_date`, `note`, `disabled`+`disabled_reason`, `source_thread_id`
    (phiếu SX nguồn), `source_purchase_id`/`source_return_id` (thùng tạo từ phiếu NHẬP
    HÀNG / hàng TRẢ về — link "Nguồn" ở BoxDetail + guard cấm xoá lẻ khi phiếu đã
    xử lý hàng), **`unit_id`** → `inventory_units` (đơn vị chứa: Thùng/Kiện/Hũ…),
    **`unit_label`** (nhãn chứa SNAPSHOT = tên đơn vị NGUYÊN KIỆN lúc nhập — ưu tiên
    hơn unit_id), **`place_id`** → `inventory_places` (vị trí kho Kho A/B…).
    (`status`/`order_thread_id` legacy.) `list_boxes`/`get_box` join thêm `place_name`,
    `unit_name` (= COALESCE(unit_label, inventory_units.name)), `product_unit`
    (đơn vị đếm của SP từ `products.unit` — cây/gói…) + `display_unit_name`/
    `display_unit_factor` (vai 👁 — BoxTile quy đổi số hiển thị).
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
    `list_order_allocations(kind=)` lọc. **Xoá thùng thành phẩm** hoàn NL theo ratio ×
    số cây, MỌI loại phiếu (`release_production_amount`, LIFO, KẸP theo tổng đã tiêu
    của phiếu — đóng gói hoàn NL chính+phụ, phiếu sản xuất hoàn NL PHỤ; mã không tiêu
    hoàn 0, trả chi tiết thùng NL nhận); rã thùng nguyên kiện (`return-material`) cùng
    rule; xoá cả phiếu hoàn nốt residue (`release_production_consumption`).
  - `domain.py` (pure, unit-tested) = sinh mã base36 + gộp nhóm size. Thùng **vô hiệu**
    → loại khỏi tồn/phân bổ. Admin **xoá thùng** (`box_delete_handler`, cấm nếu đã xuất) +
    gỡ entry khỏi phiếu SX (`production_store.remove_number_by_note`).
  - **PHIẾU ĐIỀU CHỈNH tồn thùng (`inventory_store/adjustments.py` + `server_app/adjustment_routes.py`,
    2026-07-16)**: bảng `inventory_adjustments`, mỗi phiếu = 1 allocation `kind='adjustment'`
    quantity = −delta — KHÔNG sửa quantity gốc, remaining tự đúng mọi công thức. Tạo =
    văn phòng (`POST /api/inventory/box/{id}/adjust` {new_remaining, reason bắt buộc} —
    delta tính trong transaction); gỡ = admin (hoàn nguyên, guard tồn âm). Event
    `adjustment.created/deleted` ghi CẢ scope box LẪN place
    (`inventory_audit.log_box_adjustment`, snapshot sau biến động — cả đường áp
    kiểm kho `stocktake_routes.stocktake_apply_handler` cũng ghi) → 3 timeline kho
    (thùng/SP/vị trí) hiện điều chỉnh, chiều +/− theo dấu delta, tồn-chạy đúng.
    UI `detail/BoxAdjust.tsx` ở chi tiết thùng.
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
  - API `server_app/inventory_routes.py` (DDL/migrate kho chạy ở BOOT — `db_migrate.
    run_boot_migrations`; `_ensure` chỉ là guard 1-lần/process cho test/chạy lẻ): `/api/inventory`
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
  = KHÔNG cần NL chính; phiếu **đóng gói** = BẮT BUỘC có công thức + chọn đủ thùng NL
  cho MỌI nguyên liệu → trừ kho qua
  `inventory_store.allocate_picks(kind='production')` (cột `kind` phân biệt xuất-đơn ↔
  tiêu-hao-SX; `remaining` = quantity − Σ mọi allocation nên tồn NL giảm đúng).
  **NGUYÊN LIỆU PHỤ (2026-07-16)**: cột `aux` trên `product_recipes` (0 = NL chính,
  1 = NL phụ — bao bì/tem…; 1 cặp SP↔NL là chính HOẶC phụ, upsert đổi được). NL phụ
  bắt buộc trừ kho ở **CẢ 2 loại phiếu** (san_xuat + dong_goi) khi cờ
  `products.aux_required` bật (INTEGER DEFAULT 0 — **mặc định TẮT, opt-in**; interpret
  `== 1`; reset 1-lần các SP cũ về 0 ở `db_migrate` marker `aux_required_default_off_v1`)
  — bật/tắt bằng toggle "Yêu cầu khi
  sản xuất" ở khu Nguyên liệu phụ của RecipeEditor (chi tiết SP). Gate server
  `inventory_routes` (needs = chính[dong_goi] + phụ[aux_required], coverage + cap
  chung); client `ProductionBoxes.tsx` cùng rule (requiredLines). `list_recipe`/
  `recipe_needs`/`set_recipe_line` nhận tham số `aux`; API recipe trả `aux` từng
  dòng + `aux_required`. Tests: `tests/test_recipe_aux.py`.
  **Dashboard HAO HỤT NL phụ (`inventory_store/aux_loss.py` + `server_app/aux_loss_routes.py`,
  GET `/api/inventory/aux-loss`, CHỈ VĂN PHÒNG)**: so NL phụ *dùng cho SX theo công
  thức* (Σ số cây THÙNG THÀNH PHẨM tạo trong kỳ × tỉ lệ NL phụ) với *sụt giảm thực*
  đo qua 2 lần KIỂM KHO liên tiếp của kho `aux_source`. 1 KỲ = giữa 2 phiếu kiểm kho
  ĐÃ CHỐT; mỗi NL phụ: `used`(A) · `cham` (châm thêm trong kỳ = bút toán
  transfer_in/out + purchase_in + return_in, cộng thùng MỚI tạo trong kho) ·
  `consumed` = đếm_trước + châm − đếm_sau (CHỈ số ĐẾM THỰC, không đụng sổ sách) ·
  `gap` = consumed − used (dương = hao hụt thật). Mốc chuẩn hoá epoch UTC
  (`strftime('%s')` vì created_at/completed_at = UTC còn allocated_at = ISO giờ VN).
  Kỳ 'open' (chưa kiểm lần sau) chỉ có used/cham. Phạm vi = NL phụ (ingredient aux=1).
  UI `pages/AuxLoss.tsx` (`#/hao-hut-nl`, ☰ Thêm — office-only). Tests: `tests/test_aux_loss.py`.
  **Đơn vị nhập tỉ lệ**: cột `ratio_unit`/`ratio_factor` — tỉ lệ nhập theo đơn vị
  quy đổi của NL (product_units, chọn ở RecipeEditor); `ratio` DB LUÔN quy về
  đơn vị GỐC (needs/gate không đổi), unit/factor chỉ là snapshot hiển thị.
  **KHO ĐẶC BIỆT nguồn NL PHỤ**: cột `inventory_places.aux_source` (tối đa 1 kho —
  `set_place_aux_source` bật là tắt kho khác; backfill 1 lần theo tên "Kho nguyên
  liệu đang dùng"). Có kho này → thùng NL PHỤ bắt buộc đang ở đó (gate `auxplace`
  server + `StockPickerModal placeFilter` client); chưa chỉ định → không ràng buộc.
  Đặt/bỏ = chip ⭐ ở PlaceDetail (admin, POST /api/places/{id} {aux_source}).
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
    + hiện tóm tắt. Audit `return.goods_handled` + event kho scope box/place
    (`box.created` kèm `return_id` / `box.return_in` — route ghi từ `extra['audit']`
    snapshot) → timeline thùng/SP/vị trí thấy hàng trả về. Auto-mở modal qua
    sessionStorage `rg_open`.
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
- **`bean_store/` — KHO ĐẬU (2026-08-10, app.db 100% local, HỆ KHO RIÊNG).** Tách
  HẲN kho hàng hoá (`inventory_store`): hàng hoá riêng, vị trí riêng, phiếu riêng —
  không dùng chung `products`/`inventory_boxes`/`inventory_places` và KHÔNG đụng
  `inventory_changed`. 5 bảng: `bean_places` (Kho A/B…) · `beans` (danh mục đậu,
  cột `unit` = ĐƠN VỊ GỐC kg/bao…) · **`bean_units`** (đơn vị quy đổi của từng loại
  đậu: `factor` = 1 đơn vị này bằng bao nhiêu đơn vị GỐC) · `bean_slips` (kind
  `nhap`|`xuat`|`dieu_chinh`, 1 kho/phiếu) + `bean_moves` (1 dòng = 1 loại đậu
  trong phiếu). **KHÔNG có bảng tồn** — tồn =
  `SUM(delta)` các dòng của phiếu CÒN SỐNG (`stock.py`), nên xoá mềm phiếu là tồn tự
  đúng, khỏi bút toán hoàn. Luật dấu ở `domain.delta_for`: nhập `+q` · xuất `−q` ·
  **điều chỉnh: `quantity` là SỐ ĐẾM THỰC TẾ, delta = đếm − tồn** (đừng nhập chênh
  lệch vào đó). Guard tồn âm ở CẢ 2 chiều: tạo phiếu xuất/điều chỉnh quá tồn bị chặn,
  xoá phiếu mà làm tồn âm cũng bị chặn. Trùng tên đậu/kho so bằng Python `.lower()`
  chứ KHÔNG `COLLATE NOCASE` (SQLite chỉ fold ASCII → "Đậu xanh" vs "đậu xanh" lọt).
  **QUY ĐỔI ĐƠN VỊ (`bean_store/units.py`)**: MỌI số trong DB (tồn/`delta`/`quantity`)
  luôn theo ĐƠN VỊ GỐC; `unit_id` gửi lên lúc tạo phiếu chỉ là CÁCH GÕ — server quy
  về gốc ngay (`to_base`) rồi lưu snapshot `bean_moves.entered_qty/unit_name/unit_factor`
  để in lại đúng thứ đã nhập ("2 bao (100 kg)"). Hệ quả cố ý: **đổi tỉ lệ hay xoá đơn
  vị KHÔNG tính lại phiếu cũ** (tồn quá khứ đứng yên) — KHÁC hẳn `set_base_unit`
  (ĐỔI ĐƠN VỊ CHÍNH, vd kg→bao): cái đó CÓ quy đổi lại MỌI số của loại đậu đó
  (`bean_moves.quantity/delta/before_qty/unit_factor` + factor các đơn vị còn lại,
  chia cho factor đơn vị được chọn, làm tròn 6 số) nên **lượng hàng thực không đổi,
  chỉ đổi thước đo**; đơn vị gốc CŨ tự thành đơn vị quy đổi (1/factor) → đặt ngược
  lại được. Đổi TÊN đơn vị chính (`updateBean {unit}`) thì chỉ đổi CHỮ, số giữ nguyên.
  Guard tồn âm so bằng số GỐC nên
  xuất "3 bao" khi chỉ còn 100 kg vẫn bị chặn. Tên đơn vị so bằng `vn_normalize`
  (bỏ dấu, không phân biệt hoa thường), trùng đơn vị gốc bị chặn.
  DDL ensure per-module (`schema.py`, gọi từ route — KHÔNG qua db_migrate); 3 cột
  snapshot thêm sau nên `ensure_tables` tự `ALTER TABLE` bù cho DB tạo bởi bản trước.
  API `server_app/bean_routes.py` (dashboard tồn + danh mục + kho; mỗi loại đậu trả
  kèm `units`), `bean_slip_routes.py` (phiếu), `bean_unit_routes.py` (đơn vị quy đổi
  — ⚠ route `/api/beans/items/{id}/units*` phải đăng ký TRƯỚC `POST /api/beans/items/{id}`):
  tạo phiếu/danh mục/đơn vị = MỌI user đăng nhập, sửa tên/tỉ lệ =
  văn phòng, xoá = admin (xoá mềm, chặn khi còn phiếu). Realtime `bean_changed`;
  **THÔNG BÁO mỗi phiếu nhập/xuất/điều chỉnh** (2026-08-15, `server_app/bean_notify.py`)
  — `notify_bean_slip(slip, actor)` gọi ở `bean_slip_create_handler` → chuông trong app
  + push FCM qua `server_app.notify.push_bg`, type `bean_slip`. Nội dung dựng THUẦN ở
  `build_bean_notif` (tests/test_bean_notify.py): nhập/xuất nói theo ĐƠN VỊ NGƯỜI GÕ
  ("3 bao"), điều chỉnh nói số ĐẾM + chênh lệch theo ĐƠN VỊ GỐC (delta luôn là gốc,
  ghép với "bao" là sai nghĩa), tối đa 3 dòng rồi "+N dòng nữa". ⚠ Thông báo này KHÔNG
  thuộc đơn hàng nên deep-link bằng **cột MỚI `notifications.route`** (hash webapp,
  `#/kho-dau/phieu/<id>`; `notif_store/schema._migrate` tự ALTER cho DB cũ) —
  `NotifCenter.go()` ưu tiên `route` trước nhánh `thread_id`. Thêm thông báo cho thực
  thể ngoài đơn thì dùng lại `data['route']`, đừng mượn `thread_id`;
  **ẢNH + TRAO ĐỔI trên từng PHIẾU** = entity media scope **`bean_slip`** (giống đơn
  hàng: `Images`/`Comments`/`History` ở BeanSlipDetail; `entity_media_routes._emit`
  bắn `bean_changed`, `realtime.ts::eventMatchesBase` nhận `bean_changed` cho base
  `/bean_slip/`). ⚠ **Audit tách 3 scope THEO THỰC THỂ** (2026-08-10):
  `bean_slip` (id phiếu) · `bean_item` (id loại đậu, gồm cả `bean.unit_*` +
  `bean.base_unit_changed`) · `bean_place` (id kho) — 3 bảng có id riêng nên gộp 1
  scope `bean` là lịch sử phiếu #5 lẫn với loại đậu #5; scope `bean` cũ còn trong dữ
  liệu trước ngày đó nên `activity_format._SCOPE_LABEL` giữ cả 4. Action giữ nguyên
  tiền tố `bean.*` (`bean.slip_nhap/xuat/dieu_chinh`, `bean.item_*`, `bean.place_*`,
  `bean.unit_*`, `bean.base_unit_changed`); parts ghép bằng `_join` (client render
  parts LIỀN NHAU — thiếu dấu là dòng lịch sử dính chữ).
  UI: `#/kho-dau` (BeanBoard — tồn xem theo LOẠI ĐẬU hoặc theo KHO, cùng dữ liệu đổi
  trục; card bấm được) · **`#/kho-dau/dau/:id` (BeanDetail) + `#/kho-dau/kho/:id`
  (BeanPlaceDetail)** = trang chi tiết loại đậu / kho, **SỬA NGAY TẠI TRANG** (tên ·
  đơn vị chính · ghi chú, văn phòng) + tồn chia theo kho/loại + phiếu gần đây + xoá
  (admin) ← `GET /api/beans/items/{id}` · `GET /api/beans/places/{id}`; trang thiết
  lập chỉ còn LIỆT KÊ (bấm dòng để mở chi tiết) · `#/kho-dau/phieu` (BeanSlips) →
  `#/kho-dau/phieu/:id` (BeanSlipDetail) · card phiếu dùng chung `detail/BeanSlipRows.tsx` ·
  `#/kho-dau/tao?kind=` (BeanSlipCreate — mỗi dòng có ô chọn đơn vị, hiện "= n <gốc>"
  và tồn để đối chiếu) · `#/kho-dau/thiet-lap` (BeanSetup — thêm kho/loại đậu bằng
  POPUP `detail/BeanAddPopup.tsx`, nút ⇄ mở POPUP `detail/BeanUnits.tsx` = khai quy
  đổi + đổi tên đơn vị chính + nút ★ đổi đơn vị chính). ⚠ Route
  `#/kho-dau` phải đứng TRƯỚC nhánh `#/kho` trong `main.tsx` (startsWith nuốt). Guide:
  `webapp/src/guides/data_dau.ts`. Tests: `tests/test_bean_store.py`.
- `area_store/` — KHU VỰC XƯỞNG (`workshop_areas`) + BÁO CÁO VỆ SINH hằng ngày
  (`area_hygiene_reports`), app.db 100% local. Nhân viên chụp ảnh báo cáo vệ sinh
  từng khu vực mỗi ngày; dashboard cho biết khu nào đã/chưa báo cáo hôm nay. Ảnh
  gắn vào TỪNG BÁO CÁO qua media scope `area_report` (1 báo cáo tính là "đã báo
  cáo" chỉ khi có ≥1 ảnh). `get_or_create_report` idempotent theo (khu, ngày) —
  ngày = `today_vn()` tính SERVER; partial unique index `ux_area_report_day` cho
  phép xoá mềm rồi báo cáo lại cùng ngày. DDL ensure per-module (`schema.py`,
  gọi từ route, KHÔNG qua db_migrate); logic thuần `domain.py`
  (`build_dashboard_rows`, unit-tested). Quyền: xem + tạo khu vực + báo cáo +
  ảnh = mọi user; sửa tên/ghi chú = văn phòng; xoá khu vực/báo cáo = admin (xoá
  mềm). API `server_app/area_routes.py` (`/api/areas*`); realtime `area_changed`;
  audit scope `area` (event `area.created/updated/deleted/report_created/report_deleted`).
  UI: `#/khu-vuc` (AreasBoard — dashboard 7 ngày) → `#/khu-vuc/:id` (AreaDetail —
  báo cáo photo-first qua CameraBox); menu ☰ Thêm → Sản xuất → "Vệ sinh khu vực".
  Tests: `tests/test_area_store.py`.
- `quality_store/` — CHẤT LƯỢNG MÂM KẸO (`tray_quality_reports`), app.db 100% local,
  2026-08-01. **CÙNG KHUÔN với vệ sinh khu vực**, chỉ khác THỰC THỂ: ở đây là **THỢ**
  (bảng `production_workers` có sẵn của `worker_store` — KHÔNG tạo danh sách người thứ
  hai; thêm/xoá/đổi tên thợ vẫn ở `#/tho`). Mỗi ngày chụp ảnh mâm kẹo từng thợ làm
  được; dashboard cho biết thợ nào đã/chưa chụp hôm nay. Ảnh gắn TỪNG BÁO CÁO qua media
  scope `quality_report` (báo cáo tính là XONG chỉ khi có ≥1 ảnh). `get_or_create_report`
  idempotent theo (thợ, ngày) — ngày = `today_vn()` tính SERVER; partial unique index
  `ux_tray_quality_day` cho phép xoá mềm rồi chụp lại cùng ngày. Quyền: xem + chụp =
  mọi user; xoá báo cáo = admin (xoá mềm). API `server_app/quality_routes.py`
  (`/api/quality*`); realtime `quality_changed`; audit scope `quality` (event
  `quality.report_created/report_deleted`). UI: `#/chat-luong` (QualityBoard) →
  `#/chat-luong/:worker_id` (QualityDetail — photo-first qua CameraBox, nút sang
  `#/sx-tho/:name`); menu ☰ Thêm → Sản xuất → "Chất lượng mâm kẹo"; **CSS dùng chung
  `.area-*`** với trang vệ sinh. Tests: `tests/test_quality_store.py`.
  ⚠ **SẢN PHẨM của tấm ảnh**: cột `product` trên `entity_images` (ADD COLUMN cho DB
  cũ; ảnh cũ = `''`). Client gắn field `product` vào multipart lúc upload
  (`uploadProcessed(base, p, kind, product)`). Người dùng chọn SP ở `detail/ProductPick`
  (nút trên bảng + trang chi tiết thợ) — lựa chọn nhớ theo **MÁY** (localStorage
  `quality_product`), CỐ Ý không lưu server: hai người có thể đang sửa hai loại kẹo
  cùng lúc, lưu chung sẽ gắn nhầm SP cho ảnh của người kia. Danh sách SP lấy từ
  **`GET /api/quality/products`** (không phải `/api/products`) để vai trò `chat_luong`
  gọi được mà không phải mở quyền vào cả kho SP. Response kèm **`recent` = mã SP gắn
  cho ảnh GẦN ĐÂY NHẤT của CẢ XƯỞNG** (`entity_media_store.recent_products` — quét
  400 ảnh mới nhất scope `quality_report`, gộp mã, mới-dùng-trước; cache RAM 30s DÙNG
  CHUNG mọi user, `quality_routes._recent_products_cached`) → popup ProductPick hiện
  khối "Dùng gần đây" trên đầu, phần còn lại là danh mục đầy đủ (đang gõ tìm thì bỏ
  tách khối). Đây là số liệu CHUNG (ai cũng thấy cùng gợi ý), KHÁC lựa chọn SP đang
  chụp vốn nhớ theo máy. Mã đã đổi/xoá khỏi danh mục tự rụng khỏi gợi ý.
  Tests: `tests/test_recent_products.py`.
  ⚠ Ảnh mâm kẹo là BẰNG CHỨNG → CameraBox nhận prop **`captureOnly`** (QualityDetail
  + nút chụp nhanh ở QualityBoard bật) để ẩn nút "Chọn ảnh": chỉ được chụp tại chỗ,
  không lấy từ thư viện. Các trang khác vẫn chọn ảnh bình thường (mặc định false).
  ⚠ VAI TRÒ **`chat_luong`** (user_store ROLES): chỉ xem/thao tác **2 trang báo cáo
  ảnh hằng ngày** — chất lượng mâm kẹo (`#/chat-luong`) + **vệ sinh khu vực
  (`#/khu-vuc`, mở 2026-08-19: cùng người chụp cả 2 loại báo cáo)** — không thấy
  đơn/kho/lương/khách. Chặn THẬT ở **`server_app/web_auth/role_scope.py`** —
  middleware `web_auth` từ chối 403 mọi `/api/*` ngoài `auth` · `quality` · `areas` ·
  `media/{quality_report,quality_image,area_report,area_image}` · `fcm/register`
  (mặc định TỪ CHỐI, so khớp
  theo TỪNG ĐOẠN đường dẫn để `/api/quality-secret` không lọt; `fcm/register` mở để
  máy dùng chung đổi chủ row token → server loại máy khỏi push). Webapp
  `isQualityOnly()` chỉ ẩn menu/nhốt hash trong `QUALITY_PAGES` (main.tsx — PHẢI khớp
  danh sách mở API ở server) cho gọn mắt — KHÔNG
  phải hàng rào; thanh dưới của vai trò này rút gọn còn 2 tab (không có thì kẹt ở
  trang đang mở vì menu ☰ Thêm bị ẩn). Vai trò này KHÔNG thuộc OFFICE_ROLES nên mọi
  gate office/admin sẵn có tự động vẫn chặn (sửa tên khu vực = văn phòng, xoá báo cáo
  = admin — họ chỉ chụp + xem). Thêm tính năng cho vai trò này thì mở đường trong
  `role_scope.py`. **Realtime /ws cũng lọc theo role**: client chat_luong chỉ nhận
  `ping`/`app_reload`/`quality_changed`/`area_changed`
  (`role_scope.ws_event_allowed_for_quality`,
  đánh dấu socket ở `websocket_routes` → lọc trong `realtime._send`).
  Test: `tests/test_web_auth_role_scope.py`.
  ⚠ BẢNG #/chat-luong: **2 CỘT ĐỘC LẬP** (`.qb-cols` + 2 `.qb-col`, không phải grid
  so hàng), mỗi card có **nút chụp nhanh** (mở camera ngay tại bảng — nút nằm NGOÀI
  thẻ `<a>` để bấm không nhảy trang). Hai kiểu hiện: **đầy đủ** (ảnh + dải 7 ngày) và
  **gọn** (chỉ tên + nút chụp) — nút bật/tắt ở đầu trang, lưu `localStorage`
  (`quality_board_compact`) vì là sở thích của TỪNG MÁY. Nút **🖼 Ảnh** →
  `#/chat-luong/anh` (`pages/QualityGallery.tsx`, API `GET /api/quality/gallery?days=`),
  xem mọi ảnh gom theo ngày–thợ, chạm ảnh mở đúng `PhotoReportViewer` nên chấm điểm
  ngay tại gallery được.
  Chỉ vài thợ sửa kẹo → **⚙ Cài đặt** (văn phòng): tick thợ hiện · kéo thứ tự ·
  bấm **C1/C2** chọn thợ nằm cột nào (`ReorderList` + prop `trailing`). Cấu hình lưu
  SERVER ở `settings_store['quality_board_workers']` = **`{"columns": [[…],[…]]}`**;
  vẫn ĐỌC ĐƯỢC dạng cũ (mảng phẳng → rải trái→phải) nên bản đã lưu không vỡ.
  API `POST /api/quality/settings` nhận `columns` (hoặc `worker_ids` của client cũ),
  gate `is_office_request`; `GET /api/quality` trả `board_columns` + `board_worker_ids`.
  **Rỗng = hiện TẤT CẢ thợ.** Logic thuần `quality_store/domain.py:
  clean_board_ids/clean_board_columns/flatten_columns/select_board_rows`, test
  `tests/test_quality_board_settings.py`.
  ⚠ GIỜ hiển thị: **luôn dùng `fmtHourVN`/`fmtDateTimeVN` (webapp/src/format.ts)**,
  TUYỆT ĐỐI không `String(created_at).slice(11,16)` — server lưu UTC nên cắt thô ra
  sớm 7 tiếng. Test hồi quy: `webapp/tests/fmtHourVN.test.ts` (chạy được ở mọi TZ máy).
  ⚠ Logic THUẦN của CẢ HAI trang (mốc ngày VN + ghép hàng dashboard 7 ngày) nằm ở
  **`utils/daily_photo_report.py`** (`today_vn`/`last_n_days`/`build_dashboard_rows`,
  tham số `entity_key='area_id'|'worker_id'`); `area_store/domain.py` +
  `quality_store/domain.py` chỉ là lớp chốt entity_key. Sửa luật "đã báo cáo" ở đó là
  đổi cả hai — đừng chép lại. Thêm trang báo-cáo-ảnh-hằng-ngày thứ 3 thì dùng lại module này.
- **CHẤM ĐIỂM 0–10 + TRAO ĐỔI trên báo cáo-ảnh (2026-08-01, áp cho CẢ 2 trang trên).**
  3 tầng trao đổi/đánh giá, tất cả xây trên `entity_media_store`:
  - **Bình luận TỪNG NGÀY** = scope báo cáo (`area_report`/`quality_report`,
    entity_id = report_id) — có sẵn, chỉ thêm UI.
  - **Bình luận TỪNG BỨC ẢNH** = scope MỚI `area_image`/`quality_image` với
    **entity_id = image_id** (id trong `entity_images`), chỉ dùng cho comments (ảnh
    của ảnh là vô nghĩa) — nhớ khoảng cách ngữ nghĩa này khi đọc `entity_comments`.
  - **Điểm 0–10 mỗi ảnh — RIÊNG TỪNG NGƯỜI** = `entity_media_store/scores.py`
    (bảng `entity_image_scores`, PK **(scope, image_id, scored_by)** → 1 ảnh nhiều
    người chấm, mỗi người giữ điểm của mình; chấm lại chỉ đè điểm CỦA MÌNH, DELETE
    chỉ bỏ điểm CỦA MÌNH). `scored_by` = **username**. Bảng cũ PK (scope,image_id)
    được `_migrate_per_user` tự nâng cấp (SQLite không ALTER được PK → dựng bảng mới
    + copy + rename), dữ liệu cũ thành điểm của chính người đã chấm.
    `scores_for(scope, ids, viewer)` trả `{score (TB), score_count (số NGƯỜI),
    my_score, raters[]}`; `avg_by_entity` gộp **2 tầng** (TB từng ảnh rồi mới TB
    theo báo cáo) để ảnh nhiều người chấm không nặng hơn ảnh 1 người chấm.
    Mọi lần chấm/bỏ đều **GHI LOG** audit (`quality.image_scored` /
    `*.image_score_cleared`, có `old_score` → nhìn log thấy sửa từ mấy lên mấy);
    nhãn ở `server_app/event_format.py`. Test: `tests/test_image_scores.py`.
    API `server_app/image_score_routes.py` POST/DELETE
    `/api/media/{scope}/{entity_id}/images/{image_id}/score` (mọi user đăng nhập chấm
    được — đổi thành office chỉ cần thêm gate ở 2 handler đó). `avg_by_entity` JOIN
    `entity_images` cho điểm TB theo ngày/hôm nay.
  - **Trang xem 1 ảnh** = `webapp/src/detail/PhotoReportViewer.tsx` (dùng chung 2 trang).
    Đầu trang hiện **tên thợ/khu vực** (props `subject` + `subjectLabel` do trang cha
    truyền) · **người chụp** · **giờ chụp** — lấy theo TỪNG ảnh từ
    `entity_images.uploaded_by/created_at`, do `photo_report_view._image_row` trả kèm;
    ảnh cũ chưa có 2 trường này thì lùi về `created_by`/`created_at` của báo cáo
    (props `reportBy`/`reportAt`). Khung dùng ĐÚNG CSS `.pv-*` của trình xem ảnh đơn
    hàng (ảnh full-screen + `.pv-topbar` + dải `.pv-thumbs` + `.pv-controls`; chấm
    điểm & trao đổi nằm trong tấm trượt `.pv-panel`).
  - ⚠ **CỬ CHỈ XEM ẢNH chỉ có MỘT bản**: `detail/useImageGestures.ts` (pinch-zoom,
    kéo, double-tap, vuốt trái/phải đổi ảnh, vuốt xuống đóng, lăn chuột zoom).
    `PhotoViewer` (ảnh đơn hàng) VÀ `PhotoReportViewer` cùng gọi hook này — sửa cảm
    giác cử chỉ ở đó là cả hai cùng đổi, ĐỪNG chép lại. Mấu chốt để mượt: trạng thái
    nằm trong `useRef` + ghi thẳng `style.transform`, **không `setState` mỗi lần ngón
    di chuyển** (setState mỗi frame = giật, zoom "nhảy" — lỗi đã gặp).
  - Dựng payload xem cho cả 2 trang: **`server_app/photo_report_view.py`**
    (`enrich_reports` → images[{id,score,scored_by,comment_count}] + photo_count +
    comment_count + score_avg/score_count; `attach_today_scores` → today.score_avg).
    Sửa hình dạng report trả về thì sửa Ở ĐÂY, cả 2 route dùng chung.
  - UI dùng chung: **`webapp/src/detail/PhotoReportDays.tsx`** (thẻ từng ngày: badge
    điểm TB + nút Trao đổi ngày + ô ảnh có nhãn điểm/💬) → **`PhotoReportViewer.tsx`**
    (ảnh to + chips 0–10 + Comments của ảnh; `scoreClass` = màu theo thang điểm, cả 2
    dashboard import). `promptDialog` có thêm `multiline: true` (dùng cho "Ghi chú tổng"
    của khu vực — hiện luôn trên card ở `#/khu-vuc`). `eventMatchesBase` (realtime.ts)
    nhận `area_changed`/`quality_changed` để luồng trao đổi đang mở tự tải lại.
  Tests: `tests/test_image_scores.py`.
- `supplier_store/` + `purchase_store/` — NHẬP HÀNG + NHÀ CUNG CẤP (app.db,
  **100% local, không KiotViet**). `suppliers` (tên/SĐT/địa chỉ/ghi chú, xoá mềm,
  chặn xoá khi còn phiếu) + `purchase_slips` (items JSON [{sp, sp_id?, sl, price}]
  — **hàng hoá dùng chung bảng sản phẩm**: mã resolve qua `product_store` gắn
  `sp_id`, hiển thị bản hiện hành như đơn; giá ≥ 0, snapshot). Tạo/sửa phiếu + tạo
  NCC = MỌI người dùng đăng nhập (mở 2026-07-17; sửa NCC vẫn văn phòng), xoá =
  admin (xoá mềm). **`update_purchase_items` chặn hạ tổng dưới số
  đã trả VÀ chặn đổi NCC khi `paid > 0`** (gỡ các lần trả trước mới đổi được). API `server_app/supplier_routes.py` +
  `purchase_routes.py` (`/api/suppliers*`, `/api/purchases*`); realtime
  `purchase_changed`/`supplier_changed`; ảnh/trao đổi/lịch sử = entity media scope
  `supplier`/`purchase`. UI: dashboard `#/nhap-hang` (PurchasesList) → tạo phiếu =
  **trang riêng `#/nhap-hang/tao`** (`pages/PurchaseCreate.tsx`, thay popup cũ —
  chọn NCC gõ tên lạ → tạo mới ngay, `?ncc=<id>` prefill từ trang NCC; **nháp tự
  lưu localStorage `purchase_create_draft_v1`** — rời trang giữa chừng quay lại
  khôi phục, tạo xong/Xoá nháp mới xoá) → `#/nhap-hang/:id` (PurchaseDetail);
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
  - POST `/receive-goods` (mọi người dùng — mở 2026-07-17, nhiều lần): mỗi dòng
    `restock_new` (tạo N thùng GIỐNG NHAU như phiếu SX — `{count, quantity/thùng,
    unit_id, place_id}`, thùng gắn `source_purchase_id` → link "Nguồn") |
    `restock_existing` (allocation ÂM `kind='purchase_in'` — remaining tăng,
    quantity gốc giữ) | `skip`. Validate TRƯỚC khi ghi: mã có trên phiếu, đúng SP
    thùng, thùng sống/còn hàng, không vượt trần cộng dồn theo SP (trần = phiếu − đã nhập).
  - Gỡ từng dòng khi ĐANG MỞ: xoá thùng mới qua DELETE box (mọi người dùng với
    thùng `source_purchase_id` phiếu mở — `box_delete_handler`; thùng khác
    admin-only, `_box_delete_lock` chặn phiếu chốt/thùng đã dùng); gỡ dòng cộng
    qua POST `/unreceive {allocation_id}` (mọi người dùng, guard phần cộng chưa tiêu).
  - POST `/confirm-goods` (mọi người dùng): CHỐT — CAS `goods_handled_at` + snapshot
    `goods_result` từ trạng thái đang nhập → phiếu KHOÁ sửa items + chặn xoá.
    CHỈ chốt khi đã nhập ĐỦ mọi mã theo phiếu (như chốt xuất kho đơn; UI mờ nút
    kèm lý do) — hàng về thiếu/vỡ thì sửa SL trên phiếu về số thực nhận rồi chốt.
    (Endpoint cũ `/handle-goods` nhập+chốt 1 phát đã XOÁ 2026-07-17 — UI không dùng.)
  - **HỦY CHỐT** (admin) POST `/undo-goods`: all-or-nothing — giữ thùng mới, gỡ
    allocation purchase_in, clear goods_* → phiếu QUAY VỀ trạng thái đang nhập;
    CHẶN nếu hàng đã dùng (thùng mới có allocation, remaining thùng có sẵn < số cộng).
  - Guard nhất quán khi kho còn dấu vết nhập: `soft_delete_purchase` chặn xoá
    phiếu; `update_purchase_items` chặn hạ hàng dưới phần đã nhập
    (`_retained_box_totals` = thùng + purchase_in) + re-check khoá TRONG transaction.
  Events: `purchase.goods_line_added/line_removed/received/undone` (event_format)
  + event KHO scope box/place mỗi biến động (`box.created` kèm `purchase_id` /
  `box.purchase_in` / `box.purchase_in_removed` — route ghi qua `inventory_audit`
  từ `extra['audit']` snapshot purchase_goods trả về) → timeline thùng
  (`box_timeline`) / sản phẩm (`product_timeline`) / vị trí (`place_timeline`)
  đều thấy nhập hàng, tồn-chạy (`total_after`) tính đúng.
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
  UI `detail/PurchaseUnitPicker.tsx` (hiện khi SP có trong danh mục — kể cả chưa
  có quy đổi; option "➕ Thêm đơn vị quy đổi…" khai ngay trong popup →
  `purchaseProduct.addUnitChoice` POST product_units + invalidate cache; chọn ở
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
- **`profit_dashboard/` — dashboard LỢI NHUẬN `/loi-nhuan/*` (2026-08-25, CHỈ VĂN
  PHÒNG).** Port nguyên trang từ repo anh em `profit-dashboard` (app riêng port 8091
  — từ nay là LEGACY, đừng sửa bên đó nữa): trang HTML server-render (tailwind CDN +
  alpinejs, KHÔNG thuộc webapp/) — lãi theo đơn/SP/khách theo khoảng ngày, nhập giá
  vốn bulk, freeze giá vốn vào đơn cũ, cấu hình tiền vay năm + trọng số tháng
  (file JSON `PROFIT_SETTINGS_FILE`, mặc định `~/letrang-db/profit_settings.json`).
  Routes = `server_app/profit_routes.py` (đăng ký app_factory): gate văn phòng theo
  token — lượt đầu mang `?token=` (webapp `#/loi-nhuan` = `pages/ProfitRedirect.tsx`
  chuyển CẢ cửa sổ kèm token, mục ☰ Thêm → Tài chính → Lợi nhuận, office) → server
  đóng dấu cookie `pd_token` (Path=/loi-nhuan) nên link giữa các trang không cần
  token. Mọi generator quét FULL bảng orders (thread_id ≥ 460000) nên chạy trong
  `asyncio.to_thread` với connection riêng — đừng gọi thẳng trên event loop. Logic
  JSON feed + freeze tách ở `profit_dashboard/queries.py` (tests:
  `tests/test_profit_queries.py`). ⚠ Nợ kỹ thuật: `pages/dashboard.py` ~990 dòng
  (vượt trần 400 — vendored nguyên khối, tách sau). Mọi URL nội bộ trong pages đã
  prefix cứng `/loi-nhuan` — thêm trang/endpoint mới nhớ prefix + thêm route.
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
- **`integrations/vnpt_invoice/` — HĐ ĐIỆN TỬ VNPT NHÁP (TT78, 2026-08-26).** SOAP
  client tự dựng (lxml + urllib blocking → caller bọc `asyncio.to_thread`), env
  `VNPT_INV_*` (.env). **CHỈ nháp chưa phát hành** — dùng ImportInvByPattern
  (convert=0) / deleteInvoiceByFkey / getStatusInv, CẤM gọi nhóm `Publish*`.
  ⚠ `updateInvoice` bị VNPT KHOÁ trên TT78 ("deprecated function", thực nghiệm)
  → SỬA nháp = import fkey MỚI trước rồi xoá fkey cũ (thứ tự đó để lỗi giữa chừng
  không mất nháp); xoá fkey đã mất trên portal → ERR:5, `delete_draft(missing_ok=True)`
  nuốt. XSD của VNPT chặt: KHÔNG có thẻ `Email` trong Invoice (đã thử). Mẫu số/ký
  hiệu CỐ ĐỊNH `1/001`/`C26TTP` (env đổi được); thuế = 1 MỨC CHUNG cả HĐ
  (KCT=-1/0/5/8/10), giá nhập CHƯA gồm VAT (Duy chốt 2026-08-26). `xml_build.py`
  + `amount_words.py` (đọc số VND thành chữ) thuần, test `tests/test_vnpt_invoice.py`.
  **App-side**: routes `server_app/vnpt_invoice_routes.py` (GET/POST/DELETE
  `/api/order/{tid}/vnpt-invoice` — xem/tạo/sửa văn phòng, xoá admin, khoá theo
  đơn kiểu `_invoice_create_lock`), logic thuần `server_app/vnpt_invoice_domain.py`
  (test `tests/test_vnpt_invoice_domain.py`). **Độc lập hoàn toàn với HĐ KiotViet**;
  dữ liệu nháp = key `$.vnpt_invoice` blob đơn; **CACHE THEO KHÁCH** = key
  `$.vnpt_profile` blob customers (buyer + vat_rate + tên/giá/ĐVT từng SP theo
  sp_id + extra_lines thêm tay) — GET trộn cache với dòng hàng đơn thành `prefill`,
  mỗi lần POST tự cập nhật cache. Tên/giá/ĐVT trên HĐ điện tử ĐƯỢC PHÉP khác dữ
  liệu đơn/KiotViet (cố ý). UI: khối `#od-vnpt` OrderDetail (office) + trang
  `#/order/:id/vnpt` (`pages/OrderVnptInvoice.tsx`); event
  `order.vnpt_draft_saved/deleted` (event_format); guide `hddt-vnpt` (data_don.ts).
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
    = không cần NL chính; đóng gói = bắt buộc công thức +
    chọn đủ thùng NL mọi nguyên liệu → trừ kho (`allocate_picks kind='production'`).
    NGUYÊN LIỆU PHỤ (`aux=1`) trừ ở CẢ 2 loại phiếu khi `products.aux_required` bật
    (toggle ở RecipeEditor) — xem mục `recipe_store/` phần Data stores.
  - **PIVOT lương SP theo ngày (`production_store/wage_pivot.py` + GET
    `/api/production/wage-pivot?from=&to=`, office-only)**: THỢ theo CỘT, NGÀY theo HÀNG
    (ngược sheet cũ — thêm ngày là dài xuống, khỏi kéo ngang), kèm TỪNG PHIẾU SX trong
    ngày cho view "Chi tiết phiếu". KHÔNG tính tiền lại — chỉ XOAY BẢNG kết quả
    `report_slips.compute_range_report` (nguồn sự thật duy nhất của tiền công) nên số
    luôn khớp phiếu báo cáo + bảng lương tháng; chỉ lấy thợ `wage_type='product'`.
    Trả kèm `max_cell` để client tô heatmap. UI `pages/WagePivot.tsx` (`#/luong-ngay`,
    ☰ Thêm → Lương): bảng siêu gọn (chữ .62rem, đệm 1–3px), sticky 2 trục trong khung
    cuộn GIỐNG BẢNG LƯƠNG THÁNG (KHÔNG ép chiều cao khung: trang cuộn dọc bình
    thường, bảng chỉ cuộn NGANG trong `.wp-tbody-scroll`, hàng tiêu đề tách ra thanh
    `.wp-thead-bar` sticky `top:44` + JS đồng bộ scrollLeft — cột Ngày ghim trái, tiêu
    đề ghim trên), ô đậm nhạt theo tiền, số hiện theo NGHÌN đồng (title = số đầy đủ),
    **bấm 1 ô = popup CẤU THÀNH số tiền ô đó** (`detail/WagePivotCell.tsx`: ô ngày →
    các phiếu trong ngày · ô phiếu → cây × đơn giá + phụ cấp phiếu · ô Tổng ngày →
    chia theo thợ), nhớ tháng/kiểu xem/vị trí cuộn theo phiên.
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
  view-slider 4 ô (chi tiết/gọn/siêu gọn/**📅 lịch giao**). **Menu ☰ Thêm (`#/home`)**:
  danh mục mục nằm ở **`webapp/src/homeMenu.ts`** (nguồn DUY NHẤT — thêm tính năng mới =
  thêm 1 dòng vào `GROUPS`; `findMenuItem(hash)` khớp route DÀI NHẤT theo TỪNG ĐOẠN nên
  `#/kho` không nuốt `#/kho-dau`, `#/tho` không nuốt `#/thung`), đầu trang có khối
  **GẦN ĐÂY 6 mục vừa mở** (`webapp/src/recent.ts` — ghi theo hashchange TOÀN CỤC ở
  `main.tsx::initRecent` nên vào từ menu/thanh dưới/deep-link đều tính; lưu localStorage
  `home_recent_v1` THEO MÁY, lọc lại theo quyền lúc hiện, ẩn khi đang tìm kiếm).
  Tests: `webapp/tests/homeMenu.test.ts`. Trang: orders list/detail, tasks, payments, comments, create order,
  **thu tiền = `pages/OrderPayment.tsx` (`#/order/:id/thanh-toan`) — trên cùng có
  khối **THU NHANH** (`detail/QuickCollect.tsx`): 1 CHẠM thu ĐÚNG số nợ của ĐƠN ĐANG
  MỞ, không gộp nợ cũ / đơn khác, cố ý KHÔNG hỏi xác nhận (nút in sẵn số tiền + hình
  thức); luồng chọn-đơn + phân bổ vẫn ở dưới cho ca gộp. Cả hai gọi CÙNG `bulkPayment`
  nên không có đường ghi tiền thứ hai**,
  **sửa hoá đơn = trang riêng `pages/OrderInvoiceEdit.tsx` (`#/order/:id/hoa-don`,
  2 TAB như trang tạo đơn, cùng mount: ⚡ Nhanh = sửa TEXT + preview parse, lưu qua
  `/api/order/fix` [text sửa → nhận diện lại khách, cảnh báo nếu đổi; text nguyên →
  preview theo khách hiện tại, Lưu khoá]; 📋 Nâng cao = ① Khách hàng [nợ KV + bảng
  giá + Đổi khách qua `/api/order/assign-customer`] → ② InvoiceEditor lấy giá theo
  khách bước 1 — đổi khách là editor xoá cache giá bảng, tra lại; KHOÁ nếu đã có HĐ
  KiotViet; popup bảng giá dùng chung `detail/PriceListModal.tsx`; chế độ gõ chia
  đôi màn dùng chung `ui/useTypingSplit.ts` với CreateOrder)**,
  - ⚠ **`ui/useTypingSplit.ts` — CẤM đoán bằng ngưỡng/đồng hồ** (2026-08-12): focus ô
    nhập là layout chia đôi NGAY nên `click` (phát SAU focus) rơi vào preview → phải bỏ
    qua ĐÚNG 1 click "đuôi" mỗi lần focus (đếm sự kiện) + xét `getBoundingClientRect`,
    KHÔNG dùng cửa sổ thời gian (bản cũ bỏ qua 400ms đầu: máy khựng là click tới muộn
    hơn → blur oan, "bấm vào ô nhập không gõ được"). Dò bàn phím đóng cũng so với mốc
    chiều cao lúc CHƯA có bàn phím, KHÔNG dùng ngưỡng tương đối (bàn phím chỉ ĐỔI CỠ —
    emoji/clipboard/đổi bàn phím/IME bật hàng gợi ý — cũng bị tính là "đã đóng").
  - ⚠ **Preview khi gõ (2 trang) gửi TRỄ 120ms + `AbortController`** huỷ request lỗi
    thời; nháp ghi localStorage trễ 500ms (I/O đồng bộ). Trước đây 1 request/phím +
    1 lượt ghi/phím → gõ nhanh là khựng. `postJSON` nhận `signal`, và huỷ KHÔNG bị
    tính là mất mạng (đừng để AbortError rơi vào nhánh offline queue).
  customers/debt (bảng giá riêng `personal_price_list`), **photos (camera in-page HTTPS +
  gallery, 2-way Telegram sync)**, **phiếu sản xuất (🏭 SX)** + sửa báo cáo thợ + dashboard SX,
  **kho (📦 Kho: thùng/vị trí/sản phẩm — xem `inventory_store`)**, lịch giao (`#/lich`),
  lịch sử thao tác (`#/lich-su`).
  - **Admin xoá**: đơn (`order_api_delete.py`, cấm nếu còn HĐ KiotViet/phân bổ kho), thùng, SP,
    vị trí, HĐ KiotViet. **Đơn vị SP** (`products.unit`) sửa ở chi tiết SP; hiện đúng khắp nơi.
  - **UI dùng chung (đừng tự chế lại — tổng duyệt 2026-07-17 đã quy mọi trang về bộ này)**:
    `ui/PageHead` = header trang chuẩn (BackLink + tiêu đề + phụ đề + slot phải; class
    `.page-head` alias `.prod-detail-head`) — đừng chế `.xx-head` mới. `ui/SelectPopup`
    (chọn tĩnh) + `ui/PickerPopup` (autocomplete) = mọi dropdown/select là **popup neo
    đỉnh** (bàn phím không che); mọi popup gọi `ui/usePopupBack` (nút BACK đóng popup
    trước) + `useScrollLock`. Ô thùng = `detail/BoxLabelGrid`. **Nhập TIỀN =
    `ui/MoneyEntryForm`** (ô to hết chiều ngang + chấm nghìn khi gõ + đọc lại bằng chữ +
    chip cộng nhanh) — đừng dùng `<input class="pw-input">` bé cho ô tiền.
    Toast/confirm/**prompt** =
    `ui/feedback` (`toast`/`confirmDialog`/`promptDialog`/`noticeDialog` [1 nút, thay
    alert] — cấm alert/confirm/prompt native; toast LUÔN kèm kind "ok"/"err"; confirm
    XOÁ kèm `okLabel: "Xoá <đối tượng>"`). States = `ui/states` (Loading/LoadingInline/
    EmptyState/SkeletonList/ErrorState — lỗi tải PHẢI hiện ErrorState + retry, đừng nuốt
    im lặng thành empty; retry thành công phải reset err).
    Chip lọc = `.chips`/`.chip` (+`.chip-n` badge số); segmented = `.seg`/`.seg-btn`;
    toggle = `.tgl`; nhãn khu = `.ie-head`; màu chữ ngữ nghĩa = `.t-ok/.t-warn/.t-danger`;
    nhóm theo ngày = `dayKey`/`dayLabel`; tiền/pad/tháng = `money/moneyR/moneyD/pad2/
    isoDate/curYM/shiftYM/ymLabel` (format.ts — đừng chép helper local). **Tuần LƯƠNG =
    `payWeek(back)`** (format.ts): 1 tuần = **thứ 7 tuần trước → thứ 6 tuần này** (đúng 7
    ngày), mốc chốt là thứ 6 gần nhất ĐÃ QUA (không lấn ngày chưa làm) và 2 kỳ liên tiếp
    KHÔNG đè ngày nào (đè = trả lương 2 lần) — dùng cho `#/bao-cao` + `#/in-luong`, mọi chỗ
    tính tuần lương mới phải gọi helper này, đừng tự tính thứ 2. Cuộn = `scroll.ts`.
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
  `cd webapp && npm run build` (= `vite build` + **`scripts/precompress.mjs`** sinh
  `.br`/`.gz` cạnh mỗi asset — `web.FileResponse` của aiohttp tự phục vụ bản nén theo
  Accept-Encoding; server KHÔNG có middleware nén, mà APK đặt `cacheMode=LOAD_NO_CACHE`
  nên mỗi lần mở nguội là tải lại TOÀN BỘ bundle: 1,3MB → ~280KB) →
  served at `/app` (`server_app/webapp_routes.py`). Image UI: `webapp/src/detail/
  Images.tsx` (+ `imageProcess.ts` client-side WebP resize/thumbnail).
  - **TỰ TẢI LẠI KHI CÓ BẢN MỚI (2026-08-13)** — APK giữ WebView sống nhiều ngày
    (foreground service + wake lock) nên máy để lâu rồi mở lại vẫn chạy bundle nạp từ
    lần khởi động trước ⇒ **giao diện cũ gọi API mới**; `/api/app/reload` chỉ tới được
    máy ĐANG kết nối lúc admin bấm. Chốt: `/ws` gửi `{"type":"hello","build":"index-XXXX.js"}`
    ngay khi mở socket (`server_app/app_build.py` = tên file bundle trong dist/index.html,
    cache theo mtime → deploy xong đổi ngay, KHÔNG cần restart); client so với bundle
    của CHÍNH nó (`import.meta.url` trong `webapp/src/realtime.ts`) → khác là
    `location.reload()`. Mọi lần resume đều nối lại socket nên kiểm tra chạy đúng lúc
    cần. 2 lớp an toàn: **hoãn reload khi đang gõ dở** (ô nhập/textarea — làm tiếp ở
    watchdog 15s + lúc resume) và **chống lặp** (sessionStorage `build_reload`: đã tải
    lại vì build đó rồi mà vẫn lệch thì thôi, chạy tiếp còn hơn reload vô tận). Build id
    rỗng (chưa build/không đọc được) = client bỏ qua. Tests: `tests/test_app_build.py`.
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
nags Duy every 15 min when delivery done but payment not — **TẮT mặc định từ
2026-08-03**, `start_reminder` no-op trừ khi `NOP_TIEN_REMINDER_ENABLED=true`),
and **`order_commands_v3.py`** — a real
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
- **Mọi đường TẠO PHIẾU THU serialize qua `server_app/payment_lock.py`**
  (1 asyncio.Lock toàn cục — web bulk, #/thu-tien-nhanh batch, Telegram `tm`):
  validate còn-thiếu → tạo phiếu KiotViet → ghi local phải là 1 khối (2026-07-25,
  cùng vai `_invoice_create_lock` bên nhánh hoá đơn). Ghi local fail SAU khi KV
  đã thu → trả `kv_paid: true` để client KHÔNG mời bấm thu lại. Thêm đường thanh
  toán mới = đi qua khoá này. SL hoá đơn có thể LẺ — parse/format qua `utils/qty.py`
  (parse_qty/fmt_qty/line_total/qty_for_api), cấm `int(sl)`.
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
