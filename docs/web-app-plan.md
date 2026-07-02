# Plan: Web app quản lý đơn hàng (app.db) — 5-6 users, Android

Yêu cầu đã chốt:
- 5-6 người dùng nội bộ, truy cập qua **Tailscale**
- Tính năng: xem/tìm đơn, cập nhật task (soạn/giao/nộp/nhận), tạo/sửa đơn, thanh toán + công nợ, **comment trên trang chi tiết đơn**, **in** từ app
- **Tài khoản riêng từng user** (biết ai sửa gì)
- Ghi **DB-only** (không sync Telegram cho endpoint mới)
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

### Phase 1 — Read-only ~2 ngày
- Danh sách đơn: search/filter trạng thái/phân trang (endpoint có sẵn)
- Chi tiết đơn: thông tin, tasks, dòng invoice, thanh toán, công nợ, chat log
- Nhãn tiếng Việt khớp lệnh Telegram (soạn, giao, nộp, nhận)

### Phase 2 — Mutations ~1-2 ngày
- Nút task soạn/giao/nộp/nhận (endpoint có sẵn)
- Thanh toán TM/CK (có sẵn)
- Comment: bảng mới `web_comments(thread_id, user, text, created_at)` + 2 endpoint
- Mọi mutation bọc `with transaction(conn):` (JSON blob read-modify-write phải atomic — convention repo)

### Phase 3 — Tạo/sửa đơn + khách hàng ~2-3 ngày
- Tạo đơn: ô text tự do → `/api/order/auto-parse` → form sửa dòng → lưu (endpoint mới dùng `order_store._create_order`)
- Sửa dòng invoice (endpoint có sẵn)
- Tìm khách + xem công nợ (`order_store/customers.py` có sẵn, thêm endpoint HTTP mỏng)

### Phase 4 — In + offline ~1 ngày
- Nút in → endpoint print-giao / print queue firebase (`meta/to_print`)
- Offline: shell đã offline (trong APK); cache danh sách + đơn đã xem vào IndexedDB
- **Write queue offline CHỈ cho task-mark + comment** — sửa invoice offline rồi replay = nguy cơ mất update (JSON blob), nên tạo/sửa đơn bị chặn khi offline, báo rõ

### Phase 5 — APK ~1 ngày
- Project Android tối giản: 1 Activity, WebViewAssetLoader, xử lý nút back, màn hình cài server URL
- `./gradlew assembleDebug` → file APK chia cho 5-6 người

## Rủi ro đã ghi nhận (theo lựa chọn của bạn)

- **DB-only**: message Telegram sẽ cũ sau khi sửa từ web. Endpoint task/payment CŨ có thể đã tự refresh Telegram (giữ nguyên hành vi); chỉ endpoint MỚI (tạo đơn, comment) là DB-only. Muốn bật sync sau: gọi `/api/order/refresh-view` có sẵn — rẻ.
- **Bảo mật**: Tailscale là lớp mạng; auth middleware là cổng thật. Có thể thêm Tailscale ACL giới hạn thiết bị.

## Quy tắc code

- **Tối đa 400 dòng mỗi file. Mỗi file làm tốt đúng một việc.** Vượt 400 dòng → tách theo trách nhiệm (route riêng, domain riêng, component riêng). Áp dụng cả backend (endpoint mới) lẫn frontend (component/page).
- Theo layering repo: store (transaction + IO) → domain (logic thuần, unit-test) → model.

## Kiểm thử
Logic thuần đặt trong module `domain` + chạy `./scripts/test.sh` (convention repo, 85 tests hiện có).
