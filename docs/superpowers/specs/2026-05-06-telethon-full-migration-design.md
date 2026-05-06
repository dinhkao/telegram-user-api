# Design: Full Command Migration from Bot API to Telethon

**Date:** 2026-05-06
**Status:** Approved
**Scope:** Migrate all 75 order-chat commands from Node.js bot API handlers to Python Telethon handlers

## Architecture

```
telegram-user-api/  (Python, port 8090)
├── order_db.py             — SQLite DAL (existing, extend)
├── order_commands.py       — Phase 1: 13 task commands (DONE)
├── order_commands_v2.py    — Phase 1+2: 40 search/delete/task/admin/media commands
├── order_commands_v3.py    — Phase 3: 22 KiotViet/payment/invoice/analysis commands
├── kiotviet.py             — KiotViet REST API client
├── payment_db.py           — Payments/debt SQLite DAL
├── invoice_formatter.py    — Vietnamese receipt text formatting
└── server.py               — Register all 3 handler modules

Shared SQLite: ~/Documents/final_telegram/data/app.db (WAL mode, 78MB)
```

## Phase 1 (DONE)
13 task status commands: soan, giao, ban, nop/nop tien, nhan/nhan tien, xuat hd/xuat hd roi, add xuat hd, clear soan/giao/nop/nhan, skip nop tien

## Phase 1+2 — order_commands_v2.py (~400 lines)

### A. Write Operations (3)
- `del` — delete_order(thread_id)
- `del hd` — delete_order(thread_id, force=True)
- `reply` / `replysi` — forward message to customer topic
- `date YYYY-MM-DD` — set order date override
- `time HH:MM` — set order time override

### B. Search (6)
- `customer search` — search_customers(name) → format HTML list
- `add khach hang ...` — add_customer(json) → SQLite insert
- `editkh ...` — update_customer(key, json)
- `detect customer` — match customer from order text
- `,<product_code>` — search_products(code) → format product list
- `auto complete ban hd` — auto-fill product codes

### C. Task Management (7)
- `show task` — get_tasks() → format task list
- `delete all task` — delete_all_tasks()
- `sort tasks` — sort_tasks()
- `migrate tasks` — migrate_tasks_to_v2()
- `check tasks` — validate task consistency
- `send task notification` — send notification to customer

### D. Price/Display (3)
- `turn on money` — set price display flag
- `turn off money` — clear price display flag
- `update debt` — recalculate debt

### E. Media (3)
- Photo attachment → save to order
- Video attachment → save to order

### F. Admin/Debug (7)
- `test rate limit` — test MTProto speed
- `batcher stats` — show batcher stats
- `flush edits` / `cancel edits` — edit queue control
- `getjson2` — dump order JSON
- `get html` — dump order HTML
- `?` — help text

## Phase 3 — order_commands_v3.py (~500 lines)

### KiotViet Client (`kiotviet.py` ~300 lines)
- OAuth client_credentials token refresh
- GET /products?search= — product search
- POST /invoices — create invoice
- GET /invoices — fetch invoices by order
- POST /payments — process payment
- GET /paymentMethods — list payment methods

### A. Invoice + Print (4)
- `show invoice` — fetchInvoice → formatInvoiceHTML → send as HTML
- `print` — generateReceipt → formatReceiptText → send as text
- `in tam tinh` — parse provisional invoice → calculate amounts
- `global ignore list` — show HDDT ignore patterns

### B. Payment (5)
- `ck <code>` — processCashPayment via KiotViet API
- `tm <code>` — processTransferPayment via KiotViet API
- `/payments` — fetchPayments → format payment list
- `/del_payment_<id>` — deletePayment
- `/orders` — list recent orders

### C. Debt (3)
- `/debt` — calculateDebt → format debt summary
- `/view_debt` — show all debts
- `update debt` — recalculate and store

### D. Analysis + Product Management (10)
- `analyze products` — query top products → format report
- `add pattern <name>` — add product recognition pattern
- `test edit batching` — test batch edit performance
- `sort tasks`, `check tasks` — validation commands

## Data Flow
1. User sends command in Telegram order topic
2. Telethon catches message via events.NewMessage
3. Handler extracts thread_id via _extract_thread_id()
4. Handler reads/writes SQLite via order_db / payment_db
5. Phase 3 handlers call KiotViet API via kiotviet.KiotVietClient
6. Handler formats response text
7. Handler sends reply via client.send_message(reply_to=msg.id)
8. Phase 1 only: fire-and-forget POST to /api/order/refresh-view
9. TELETHON_TASKS_ENABLED=true on Node.js side prevents double-processing

## Error Handling
- SQLite errors → reply "❌ Lỗi database: <reason>"
- KiotViet API errors → reply "❌ Lỗi KiotViet: <reason>"
- Missing thread_id → reply "❌ Dùng lệnh này trong topic đơn hàng"
- Invalid input → reply with usage help

## Testing Strategy
Per handler group:
1. Unit test each DB function (order_db, payment_db)
2. Unit test KiotVietClient with mock responses
3. End-to-end: restart telegram-user-api, send command, verify reply + SQLite state
4. Verify Node.js side does NOT double-process (TELETHON_TASKS_ENABLED=true)
