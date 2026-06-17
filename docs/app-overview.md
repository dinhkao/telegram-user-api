# telegram-user-api — Giải thích chi tiết toàn bộ hệ thống

## 1. App này làm gì?

Đây là hệ thống **quản lý đơn hàng qua Telegram** cho một doanh nghiệp bán sỉ bánh kẹo (Lê Trang Phát). Toàn bộ quy trình từ lúc nhận đơn, soạn hàng, giao hàng, xuất hóa đơn, thu tiền — đều diễn ra trong Telegram. App này là **phiên bản Python** đang được port dần từ Node.js, mục tiêu cuối cùng là bỏ hoàn toàn Node.js.

---

## 2. Kiến trúc

```
┌─────────────────────────────────────────────────────────────┐
│                      Telegram Cloud                         │
│  ┌──────────────┐  ┌──────────────────┐  ┌──────────────┐  │
│  │ #don_hang    │  │ Order Group      │  │ KhachHang    │  │
│  │ (channel)    │  │ (forum -10021..) │  │ (forum)      │  │
│  │ -10021384..  │  │ mỗi topic = 1 đơn│  │ mỗi topic =  │  │
│  │              │  │                  │  │ 1 khách hàng │  │
│  └──────┬───────┘  └────────┬─────────┘  └──────┬───────┘  │
└─────────┼───────────────────┼───────────────────┼──────────┘
          │                   │                   │
     ┌────▼───────────────────▼───────────────────▼─────┐
     │           telegram-user-api (Python)              │
     │           Port 8090                               │
     │  ┌──────────────┐  ┌────────────────────────────┐ │
     │  │ Telethon      │  │ aiohttp Web Server         │ │
     │  │ (user account │  │ (REST API + WebSocket)     │ │
     │  │  "Duy")       │  │                            │ │
     │  └──────┬───────┘  └───────────┬────────────────┘ │
     └─────────┼──────────────────────┼──────────────────┘
               │                      │
          ┌────▼─────┐          ┌─────▼──────┐
          │  SQLite  │          │  Firebase  │
          │  app.db  │          │  RTDB      │
          │  (shared │          │  (sync +   │
          │   với     │          │   print    │
          │  Node.js) │          │   queue)   │
          └──────────┘          └────────────┘
               │
          ┌────▼─────┐
          │ KiotViet │  ← Hệ thống kế toán/POS bên ngoài
          │ REST API │
          └──────────┘
```

Có **3 app** chạy song song (xem `start_all.sh`):

| App | Port | Ngôn ngữ | Vai trò |
|-----|------|----------|---------|
| **telegram-user-api** (app này) | 8090 | Python | Xử lý chính: lắng nghe Telegram, quản lý đơn hàng, in ấn, API |
| **final_telegram** | 3000 | Node.js | App cũ, đang được port dần sang Python |
| **bot-don-hang** | 3002 | Python | Bot Telegram về đơn hàng |

---

## 3. Luồng xử lý một đơn hàng

### Bước 1: Nhận đơn từ channel
Một tin nhắn được gửi vào channel **#don_hang** → `channel_handler.py` bắt sự kiện:
- Tạo một **forum topic** trong Order Group
- Xây dựng object đơn hàng (text, task_status, flow_version=2...)
- Lưu vào SQLite + Firebase
- Gửi tin nhắn welcome, ghim vào topic
- **Auto-parse**: tự động nhận diện khách hàng + sản phẩm từ text
- **Picking sheet**: tự động tạo phiếu soạn hàng, đẩy ra máy in

### Bước 2: Xử lý đơn trong topic
Nhân viên gõ lệnh trong topic của đơn hàng:

| Lệnh | Handler | Việc làm |
|------|---------|----------|
| `soan` | order_commands.py | Đánh dấu đã soạn hàng xong, refresh channel post |
| `giao` | order_commands.py | Đánh dấu đã giao hàng xong |
| `gtr` | gtr_handler.py | Đánh dấu nhận tiền nhanh (có note="gtr") |
| `nop` | order_commands.py | Đánh dấu đã nộp tiền |
| `nhan` | order_commands.py | Đánh dấu đã nhận tiền |
| `ban` | order_commands.py | Đánh dấu đã bán hóa đơn |
| `,` | order_commands_v3.py | Thêm sản phẩm vào đơn (parse từ text) |
| `fix` / `fixapp` | order_commands_v3.py | Sửa text đơn hàng, auto-parse lại, in picking sheet mới |
| `ck <số tiền>` | order_commands_v3.py | Thanh toán chuyển khoản → tạo payment trong KiotViet |
| `tm <số tiền>` | order_commands_v3.py | Thanh toán tiền mặt → tạo payment + phiếu thu quỹ |
| `tao hd` | order_commands_v3.py | Tạo hóa đơn trong KiotViet |
| `print` | order_commands_v3.py | In 2 hóa đơn + 1 phiếu giao hàng |
| `gdt` | gdt_handler.py | Tạo giấy dán thùng |
| `what data` | what_data.py | Xem chi tiết đơn hàng dạng HTML |
| `profit` | product_commands.py | Tính lợi nhuận đơn hàng |

### Bước 3: In ấn
Có 2 kênh in qua Firebase:
- **`meta/to_print`**: Hóa đơn + Phiếu giao hàng (từ `print-giao`)
- **`meta/to_print2`**: Phiếu soạn hàng (từ `picking_sheet.py`)
- **`html-to-png`**: Render HTML → PNG → gửi ảnh vào Telegram

### Bước 4: KiotViet
Khi tạo hóa đơn (`tao hd`), app gọi KiotViet REST API để:
- Tạo invoice với danh sách sản phẩm
- Tạo payment record (khi `ck`/`tm`)
- Tra cứu công nợ khách hàng
- Lấy giá sản phẩm theo bảng giá khách hàng

---

## 4. Các module chính

### Core
| File | Chức năng |
|------|-----------|
| `server.py` | Entry point: khởi động Telethon client + aiohttp server, đăng ký tất cả handler |
| `order_db.py` | Data access layer: đọc/ghi `orders`, `customers` trong SQLite, parse invoice, detect khách hàng |
| `order_html.py` | Sinh HTML cho channel post chính (icons trạng thái, bảng sản phẩm, tổng tiền) |
| `kiotviet.py` | Client gọi KiotViet REST API (OAuth2, CRUD customers/invoices/payments) |
| `firebase_sync.py` | Đọc/ghi Firebase RTDB, share credential với Node.js |

### Telegram handlers
| File | Chức năng |
|------|-----------|
| `channel_handler.py` | Lắng nghe channel #don_hang, tạo topic đơn hàng mới |
| `order_commands.py` | Lệnh V1: `soan`, `giao`, `ban`, `nop`, `nhan`, `clear` |
| `order_commands_v2.py` | Lệnh V2: delete, search, media, customer, task admin (~40 handler) |
| `order_commands_v3.py` | Lệnh V3: KiotViet invoice, payment, print, debt, profit, fix |
| `what_data.py` | Lệnh `what data`: xem chi tiết đơn |
| `gtr_handler.py` | Lệnh `gtr`: đánh dấu nhận tiền nhanh |
| `gdt_handler.py` | Lệnh `gdt`/`ingdt`: giấy dán thùng |
| `newkh_handler.py` | Lệnh `newkh`: tạo khách hàng mới |
| `khachhang_commands.py` | Tra cứu giá sản phẩm trong group KhachHang |
| `product_commands.py` | Quản lý sản phẩm: `sp list`, `sp add`, `profit` |
| `order_chat_logger.py` | Log tất cả tin nhắn trong topic vào SQLite |

### In ấn
| File | Chức năng |
|------|-----------|
| `picking_sheet.py` | Phiếu soạn hàng (danh sách sản phẩm cần lấy) |
| `delivery_ticket.py` | Phiếu giao hàng (có QR code) |
| `inhoadon.py` | HTML hóa đơn (lấy dữ liệu thật từ KiotViet) |
| `print_service.py` | Logic in giao: 2 hóa đơn + 1 phiếu giao |
| `receipt_print.py` | Biên lai thanh toán |
| `firebase_html_to_png.py` | Render HTML → PNG qua Playwright, gửi ảnh vào Telegram |

### APIs (cho app khác gọi)
| File | Chức năng |
|------|-----------|
| `tg_edit.py` | API sửa tin nhắn Telegram (dùng user account) |
| `tg_send.py` | API gửi tin nhắn Telegram |
| `tg_send_file.py` | API gửi file Telegram |

### Database phụ
| File | Chức năng |
|------|-----------|
| `donhang_db.py` | SQLite FTS5 cache riêng cho #don_hang messages (tìm kiếm nhanh) |
| `donhang_indexer.py` | Backfill + index realtime messages từ #don_hang channel |
| `product_db.py` | CRUD bảng `products` (mã SP, giá vốn), tính profit |
| `payment_db.py` | Quản lý payments + công nợ trong order JSON |
| `quy_db.py` | Tạo phiếu thu quỹ cho thanh toán tiền mặt |
| `customer_notify.py` | Gửi thông báo thanh toán vào topic khách hàng |

### Khác
| File | Chức năng |
|------|-----------|
| `listener.py` | Listener độc lập cho một chat khác |
| `fetch.py` | CLI fetch tin nhắn cũ |
| `vn.py` | Chuẩn hóa tiếng Việt (bỏ dấu) để tìm kiếm |
| `frontend/` | Next.js frontend xem danh sách đơn hàng |

---

## 5. API endpoints (aiohttp, port 8090)

| Method | Path | Dùng bởi |
|--------|------|----------|
| GET | `/api/orders` | Frontend (danh sách đơn) |
| GET | `/api/order/{id}` | Frontend (chi tiết đơn) |
| GET | `/api/donhang` | WebSocket realtime |
| POST | `/api/order/soan` | final_telegram |
| POST | `/api/order/ban` | final_telegram |
| POST | `/api/order/giao` | final_telegram |
| POST | `/api/order/nop-tien` | final_telegram |
| POST | `/api/order/fix` | final_telegram |
| POST | `/api/order/reply` | final_telegram |
| POST | `/api/order/print-giao` | **bot-don-hang** |
| POST | `/api/order/payment/tm` | final_telegram |
| POST | `/api/order/payment/ck` | final_telegram |
| POST | `/api/order/totals` | bot-don-hang |
| POST | `/api/order/auto-parse` | final_telegram |
| POST | `/api/order/invoice/update` | final_telegram |
| POST | `/api/order/refresh-view` | final_telegram |
| POST | `/api/order/{id}/task_status/clear` | bot-don-hang |
| POST | `/api/tg/edit-message` | final_telegram |
| POST | `/api/tg/send-message` | final_telegram |
| POST | `/api/tg/send-file` | bot-don-hang |
| POST | `/api/customer/price` | final_telegram |
| GET | `/api/product/sp/list` | (tra cứu) |

---

## 6. Thứ tự đăng ký handler (trong `server.py` → `main()`)

1. `register_handlers(client)` — Saved Messages, AI reply, edit/delete broadcast
2. `register_what_data_handler(client)` — lệnh `what data`
3. `register_gtr_handler(client)` — lệnh `gtr`
4. `register_order_commands(client)` — V1: soan, giao, ban, nop, nhan
5. `register_order_commands_v2(client)` — V2: delete, search, customer...
6. `register_order_commands_v3(client)` — V3: KiotViet, payment, print...
7. `register_channel_handler(client)` — channel #don_hang → topic mới
8. `register_gdt_handler(client)` — gdt/ingdt
9. `register_newkh_handler(client)` — newkh
10. `register_khachhang_commands(client)` — tra giá trong group KH
11. `register_product_commands(client)` — quản lý sản phẩm
12. `register_chat_logger(client)` — log tin nhắn vào SQLite
13. `_start_html_to_png(client)` — Firebase → HTML → PNG
14. `register_live_handlers(...)` — index realtime #don_hang
15. `_bootstrap_donhang()` — backfill dữ liệu cũ

---

## 7. Mối quan hệ với app khác

### final_telegram (Node.js, port 3000)
- **Chia sẻ SQLite**: Cả 2 app đọc/ghi cùng file `~/Documents/final_telegram/data/app.db` (WAL mode)
- **final_telegram gọi API của app này** khi cần dùng user account (thay vì bot) để tránh rate limit
- **App này đọc dữ liệu** từ SQLite mà final_telegram quản lý schema

### bot-don-hang (Python, port 3002)
- Gọi `POST /api/order/print-giao` để in hóa đơn giao hàng
- Gọi `POST /api/order/totals` để lấy suggested amounts
- Gọi `POST /api/tg/send-file` để forward media bằng user account
- Gọi `POST /api/order/{id}/task_status/clear` để clear task

---

## 8. Chiến lược port từ Node.js → Python

Đang port dần từng phần. Những thứ đã port xong:
- ✅ KiotViet invoice creation
- ✅ Payment processing (ck/tm)
- ✅ Task commands (soan/giao/ban/nop/nhan)
- ✅ Print-giao
- ✅ Picking sheet generation
- ✅ Delivery ticket
- ✅ GTR (nhận tiền nhanh)
- ✅ Invoice HTML generation
- ✅ Customer creation (newkh)
- ✅ Product management
- ✅ Chat logger

Những thứ còn phụ thuộc Node.js:
- Task scheduler / notifications (taskAggregator.js)
- Money report (moneyReportServer.js)
- Một số bot handler trong `bots/groupDonHang.js`
