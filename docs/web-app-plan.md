# Plan: Web app quản lý đơn hàng (app.db) — 5-6 users, Android

Yêu cầu đã chốt:
- 5-6 người dùng nội bộ, truy cập qua **Tailscale**
- Tính năng: xem/tìm đơn, cập nhật task (soạn/giao/nộp/nhận), tạo/sửa đơn, thanh toán + công nợ, **comment trên trang chi tiết đơn**, **in** từ app
- **Tài khoản riêng từng user** (biết ai sửa gì)
- Ghi **DB-only** cho phần lớn mutation; **tạo đơn** thì đăng vào #don_hang → tạo
  topic Telegram thật (từ 2026-07-04)
- UI **tiếng Việt**, tối ưu **điện thoại Android cũ/chậm**, chịu được mạng chập chờn
- Đóng gói: **debug APK** (WebView), không cần lên store

## Đã có sẵn (tận dụng, không viết lại)

- aiohttp server (port 8090) đã có sẵn phần lớn API:
  - List đơn + FTS search/filter/pagination: `server_app/orders_api.py:10`
  - Chi tiết đơn: `server_app/orders_api.py:94`
  - Thanh toán TM/CK: `server_app/order_api_payments.py`
  - Task soạn/bán/giao/nộp: `server_app/order_api_tasks.py`
  - Sửa invoice: `/api/order/invoice/update`; auto-parse text → invoice: `/api/order/auto-parse`
  - In phiếu giao: `server_app/order_api_print.py:19`
- `frontend/` = Next.js WIP (read-only) — dùng làm tham khảo UI, không dùng trực tiếp (nặng cho máy cũ)
- **Chưa có auth** trên API đơn hàng — phải làm trước tiên
- `task_status`/`payments` trong JSON đã có field `by` → gắn username vào đây
- `order_chat_messages` (log chat Telegram theo đơn) → hiển thị read-only cạnh comment web

## Kiến trúc

```
Android APK (WebView wrapper mỏng)
  ├─ UI đóng gói trong APK assets (WebViewAssetLoader) → mở tức thì, shell chạy offline
  └─ gọi data → http://<tailscale-ip>:8090/api/*
Frontend: Vite + Preact + TypeScript (~15KB runtime) — nhẹ cho máy cũ, UI tiếng Việt
Backend: cùng process aiohttp hiện tại — thêm auth middleware + vài endpoint thiếu
```

- Không dùng Next.js frontend/: React + App Router nặng cho Android cũ, và nó mới read-only. Port cấu trúc component + Tailwind sang Preact.
- WebView APK thay vì PWA: đã yêu cầu APK; bundle assets trong APK tốt hơn service worker (SW đòi HTTPS, giữ Tailscale HTTP cho đơn giản).
- Cùng bundle static đó cũng serve tại `/app` trên aiohttp cho ai dùng máy tính.

## Các phase

### Phase 0 — Auth (nền móng) — ✅ XONG 2026-07-02
- ✅ Bảng `web_users` (username, pin_hash pbkdf2, display_name, role, disabled) — package `user_store/`
- ✅ `POST /api/auth/login` → token HMAC (TTL 30 ngày, env `WEB_AUTH_TOKEN_TTL`); `GET /api/auth/me`
- ✅ Middleware `server_app/web_auth/` chặn `/api/*` — CHỈ khi `WEB_AUTH_ENABLED=true`
  (mặc định TẮT để không phá UI cũ; token vẫn được đọc → attribution chạy sẵn).
  Miễn: `/api/auth/*`, `/api/tg/*` (có X-API-Key riêng), pages/static/ws (gate sau).
- ✅ Secret: env `WEB_AUTH_SECRET` hoặc file tự sinh cạnh app.db (`web_auth_secret`, chmod 600)
- ✅ CLI: `tools/add_web_user.py add|list|disable|enable`
- ✅ Tests: `tests/test_web_auth.py` (PIN, token, exempt rules) — 113 pass
- ⏳ Đóng dấu `by: <username>` vào write endpoints → làm cùng Phase 2 (mutations)

### Phase 1 — Read-only — ✅ XONG 2026-07-02
- ✅ Frontend mới `webapp/` (Vite + Preact + TS, 12.5KB gzip JS) — serve tại `/app`
  (`server_app/webapp_routes.py`), hash routing, UI tiếng Việt
- ✅ Danh sách đơn: FTS search, chip lọc xong/chưa, "Tải thêm" (`pages/OrdersList.tsx`)
- ✅ Chi tiết đơn: header, tổng/đã trả/nợ trước, text đơn (`pages/OrderDetail.tsx`)

### Phase 2 — Mutations — ✅ XONG 2026-07-02
- ✅ Nút 5 task (bán/soạn/giao/nộp/nhận) qua endpoint generic mới `POST /api/order/task`
  (`nhan_tien` trước đây không gọi được qua HTTP) — `detail/Tasks.tsx`
- ✅ Thanh toán TM/CK — `detail/Payments.tsx` (endpoint có sẵn)
- ✅ Comment: `comment_store/` (bảng `web_comments`) + GET/POST
  `/api/order/{id}/comments` (`server_app/comment_routes.py`), UI trộn với chat log
  Telegram theo thời gian — `detail/Comments.tsx`
- ✅ Attribution: task/payment/print endpoint tự đóng `request["web_user"]` vào
  `by`/`created_by`; `resolve_name` không tra Telegram entity cho username web

### Phase 3 — Tạo/sửa đơn + khách hàng — ✅ XONG 2026-07-02
- ✅ Tạo đơn: `POST /api/order/create` (`server_app/order_api_create.py`) — **đăng text
  vào kênh #don_hang** (CHANNEL_DON_HANG_MOI) rồi gọi thẳng `channel_handlers.create.
  process_new_order` → tạo forum topic + đơn (thread_id DƯƠNG, flow_version 2) **y hệt
  đơn gõ tay Telegram** (auto-parse khách/invoice + in phiếu soạn). Trả thread_id để web
  điều hướng thẳng — `pages/CreateOrder.tsx`. (Trước 2026-07-04: DB-only thread_id âm —
  đã bỏ; Telethon không phát NewMessage cho tin do chính client gửi nên phải gọi thẳng.)
- ✅ Sửa invoice: bảng edit sl/giá/thêm/xoá dòng — `detail/Invoice.tsx`; sửa text đơn
  → `/api/order/fix` (parse lại)
- ✅ Khách hàng: `GET /api/customers[?search]` + `/api/customers/{key}`
  (`server_app/customer_routes.py`) — tìm + công nợ — `pages/Customers.tsx`

### Phase 4 — In + offline — ✅ XONG 2026-07-02
- ✅ Nút in → `/api/order/print-giao` (print queue có sẵn)
- ✅ Offline (`src/offline.ts`): cache GET (localStorage, TTL 3 ngày, tự dọn khi đầy),
  banner mất mạng, hàng đợi POST CHỈ cho task-mark + comment (replay khi online
  lại / mỗi 30s); thanh toán/sửa invoice/tạo đơn chặn khi offline (RMW blob)

### Phase 5 — APK — ✅ XONG 2026-07-02
- ✅ `android/` — 1 Activity Java (WebView + WebViewAssetLoader), bundle web trong
  APK assets (gradle task `copyWebApp` tự copy `webapp/dist`), nút back = go back,
  minSdk 23 (Android 6+), mixed-content allow (shell https → API http Tailscale)
- ✅ CORS middleware (`server_app/cors.py`) — WebView origin khác server
- ✅ Build: `cd webapp && npm run build && cd ../android && ANDROID_HOME=~/Library/Android/sdk gradle assembleDebug`
  → `android/app/build/outputs/apk/debug/app-debug.apk` (3.1MB)
- Cài APK → mở app → màn hình đăng nhập nhập `http://<tailscale-ip>:8090` + username + PIN

## Vận hành (checklist go-live)
1. Tạo user: `.venv/bin/python tools/add_web_user.py add <username> --name "Tên" --role admin|staff`
2. Bật chặn API: thêm `WEB_AUTH_ENABLED=true` vào env → restart server
   (lưu ý: UI cũ `/orders` static sẽ cần token — hoặc để tắt nếu vẫn dùng UI cũ)
3. Build + phát APK cho 5-6 máy; mỗi máy nhập Tailscale IP ở màn đăng nhập
4. Đổi UI: sửa `webapp/`, `npm run build`, rebuild APK (hoặc dùng qua trình duyệt
   `http://<ip>:8090/app/` — không cần phát lại APK)

## Rủi ro đã ghi nhận (theo lựa chọn của bạn)

- **DB-only**: message Telegram sẽ cũ sau khi sửa từ web. Endpoint task/payment CŨ có thể đã tự refresh Telegram (giữ nguyên hành vi); chỉ endpoint comment là DB-only. **Tạo đơn KHÔNG còn DB-only** (2026-07-04): đăng vào #don_hang → tạo topic Telegram thật. Muốn bật sync cho endpoint khác: gọi `/api/order/refresh-view` có sẵn — rẻ.
- **Bảo mật**: Tailscale là lớp mạng; auth middleware là cổng thật. Có thể thêm Tailscale ACL giới hạn thiết bị.

## Quy tắc code

- **Tối đa 400 dòng mỗi file. Mỗi file làm tốt đúng một việc.** Vượt 400 dòng → tách theo trách nhiệm (route riêng, domain riêng, component riêng). Áp dụng cả backend (endpoint mới) lẫn frontend (component/page).
- Theo layering repo: store (transaction + IO) → domain (logic thuần, unit-test) → model.

## Kiểm thử
Logic thuần đặt trong module `domain` + chạy `./scripts/test.sh` (convention repo, 85 tests hiện có).

## Module Kho thùng (📦 Kho) — đã giao

Quản lý tồn kho theo **đơn vị thùng** (đã port + mở rộng ngoài plan gốc). Chi tiết
kiến trúc: xem `CLAUDE.md` §4 `inventory_store/`.

- **Nhập thùng** trong phiếu SX: mỗi lần 1 thùng (số cây tự do) + **ngày SX** (mặc
  định hôm nay) + ghi chú. Mã thùng tự sinh `<SP>-NNN`. Cộng vào tổng phiếu SX.
- **Theo dõi 2 dạng**: tổng tồn kho + theo từng thùng (mã, số cây, còn lại, NSX,
  trạng thái). Tab 📦 Kho → dashboard/product → list thùng → chi tiết 1 thùng.
- **Xuất kho cho đơn**: popup chọn thùng (info đủ để chọn) — lấy **1 phần** thùng
  được (mặc định full), **nhiều thùng**. Thùng **KHÔNG tách**: lưu phần lấy ở bảng
  `box_allocations`, thùng hiện "còn lại". Thu hồi = trả phần về kho.
- **Vô hiệu thùng** (cần lý do): loại khỏi tồn/phân bổ/phiếu SX, vẫn hiện mờ; cấm
  vô hiệu nếu thùng đã xuất phần nào.
- **Deep-link 2 chiều** thùng ↔ đơn ↔ phiếu SX (cuộn tới + nháy sáng).
