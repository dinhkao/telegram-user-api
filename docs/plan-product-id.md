# Plan: Product ID cố định — mã SP chỉ là nhãn hiển thị, đổi tự do

> Trạng thái: **ĐÃ DUYỆT 2026-07-09 — ĐANG THỰC HIỆN.**
> Yêu cầu chốt (user): đổi mã SP sẽ diễn ra **thường xuyên**; khi đổi, **mọi nơi**
> (đơn cũ, kho, bảng giá, khách, invoice…) hiển thị mã mới ngay; toàn DB tham chiếu
> bằng `product_id`, mã chỉ để hiển thị/nhập liệu. Không đi đường tắt.

---

## 0. Spike KiotViet (ĐÃ CHẠY 2026-07-09 — kết quả thật)

KiotViet product có `id` (bất biến) và `code` (nhãn). Đã test trên tài khoản thật
(SP dummy + khách test, tạo xong xoá sạch):

1. ✅ `PUT /products/{id}` đổi `code` được (ZZTESTPID9 → ZZTESTPIDX).
2. ✅ `POST /invoices` với `invoiceDetails[].productId` **KHÔNG cần productCode** —
   KiotViet nhận, tự resolve mã (HD085018, đã xoá).
3. ✅ `DELETE /products/{id}` được.

→ Mọi giao tiếp KiotViet chuyển sang `productId` (= `products.kv_id` đã link,
86/97 SP). Đổi mã local không còn phụ thuộc KiotViet; đổi mã bên KiotViet cho khớp
báo cáo = best-effort PUT, fail chỉ cảnh báo.

## 1. Thiết kế đích

```
products:  id INTEGER PRIMARY KEY AUTOINCREMENT  ← danh tính BẤT BIẾN (nội bộ)
           code TEXT NOT NULL UNIQUE             ← nhãn nhập liệu/hiển thị, ĐỔI TỰ DO
           kv_id                                 ← danh tính KiotViet (ngoài)
           prod_mam REAL, prod_luong REAL        ← port từ SP_INFO (phase 2)

product_code_history: product_id, old_code, new_code, changed_at, changed_by
           ← nhật ký + alias: gõ mã cũ vẫn nhận, link cũ redirect, search mở rộng
```

Nguyên tắc (không thương lượng):
1. **Ghi**: mọi bản ghi mới lưu `product_id` (+ mã snapshot hiện hành).
2. **Đọc/hiển thị**: resolve id → mã/tên hiện hành; **fallback snapshot** nếu SP
   đã xoá (không bao giờ ô trống). Đơn cũ tự hiện mã mới — kể cả tin nhắn Telegram
   (re-render khi refresh).
3. **Tiền KHÔNG resolve lại**: giá bán/giá vốn đã chốt giữ nguyên vĩnh viễn.
4. **Không xoá dấu vết**: trường `sp` cũ trong blob giữ nguyên tại chỗ, chỉ thêm
   `sp_id`; đối chiếu tra `product_code_history`.
5. **Mã tái dùng**: resolve = danh mục hiện tại thắng; history chỉ tra khi mã
   không còn trong danh mục (entry mới nhất thắng).
6. Backfill sp_id 16k đơn làm NGAY (mã↔SP còn 1-1, chưa đổi lần nào) — batch,
   idempotent, mã mồ côi để NULL + báo cáo.

Giới hạn vật lý (không phải bug): giấy đã in, record KiotViet cũ, tem thùng đã dán
mang mã tại thời điểm in.

## 2. Phase (mỗi phase: backup → code + migrate + test + commit + deploy riêng)

### Phase 0 — Nền móng
- Rebuild `products` (SQLite không đổi PK được): tạo bảng mới id PK → copy → swap.
  Idempotent (check cột `id`), chạy trong `migrate_products_table` lúc boot.
- `product_code_history` + index old_code/product_id.
- `product_store`: `get_product_by_id`, `resolve_code` (hiện tại → history),
  `code_alias_map`; `_row` thêm `id`; cache giữ nguyên shape.
- ⚠ giữ `upsert_product` dạng UPDATE-else-INSERT (KHÔNG `OR REPLACE` — đổi id!).

### Phase 0.5 — KiotViet productId
- Helper `kv_ids_for_items(conn, items)` (product_store) → map cho 3 điểm gọi
  `create_kiotviet_invoice`: `order_commands_v3:362`, `bot_flows/invoice_create:52`,
  `return_routes:201` (HĐ âm trả hàng). Item có kv_id → gửi `productId`; chưa link
  → fallback `productCode` như cũ.

### Phase 1 — Kho + công thức
- `inventory_boxes.product_id`, `product_recipes.product_id/ingredient_id`: thêm
  cột + backfill theo code + dual-write (add_boxes, set_recipe_line) + reads join id
  (`list_boxes`, `get_box`, `product_totals/summary`, `allocations`, `recipe_needs`,
  subquery unit `inventory_routes:208`). Cột code giữ làm snapshot hiển thị nhanh.
- Verify: tổng tồn từng SP trước = sau.

### Phase 2 — Sản xuất + SP_INFO
- `production_slips.product_id` + `production_report_rows.product_id`: cột +
  backfill (theo sp_name/product_code) + dual-write (`set_sp`, `replace_report_rows`).
- Port `SP_INFO` → cột `prod_mam`/`prod_luong` trong products (seed 1 lần);
  `production_routes` (catalog :165, create :203, :237, :455) + `production_commands`
  (:90, :294, :409) đọc products trước, SP_INFO fallback.

### Phase 3 — Bảng giá (NHẠY: tiền) — verify diff=0 mới commit
- Migrate key `{MÃ: giá}` → `{"<id>": giá}`: `bang_gia_moi` (3 bảng) +
  `personal_price_list` (213 khách). Mã mồ côi → bucket `_legacy` (giữ nguyên, không xoá).
- `get_customer_price_list`/`get_customer_price_source` trả **mã-hiện-hành → giá**
  (build sống từ id) → parser + caller giữ nguyên interface.
- Ghi: `price_list_store.save_prices/set_price` (webapp), `customer_routes:109`
  (bảng giá riêng), `khachhang_commands:56`, đọc: `order_api_auto:18-46`,
  `order_commands_v3:1455`. API shape [{sp, price}] giữ nguyên (sp = mã hiện hành)
  → webapp không đổi.
- `tools/verify_product_id.py`: từng khách + từng bảng, map hiệu lực trước == sau.

### Phase 4 — Đơn hàng: sp_id + hiển thị sống
- Choke `freeze_invoice_cost_prices`: item thêm `sp_id`, chuẩn hoá `sp` = mã hiện
  hành lúc ghi. Parser (`free_text`, `comma_parser`, `channel_handlers/parse`):
  valid_codes + alias mã cũ → resolve về SP.
- **Backfill sp_id toàn bộ đơn** (boot guard 1 lần, marker kv_store, batch
  transaction, idempotent; mã mồ côi để NULL + log).
- Read path resolve hiển thị (fallback snapshot): API chi tiết đơn + list, render
  Telegram (`order_parts:35`), phiếu soạn (`picking_sheet:24`), feed khách, trả
  hàng, profit (id-first), `product_orders` (sp_id + mã cũ), search FTS mở rộng
  mã cũ qua history.

### Phase 5 — Tính năng đổi mã (đích)
- `rename_product(id, new_code)`: UPDATE 1 ô + INSERT history + refresh cột mã
  snapshot (boxes/slips/report_rows — thuần hiển thị) + invalidate cache + emit
  (`inventory_changed`, `price_lists_changed`, `productions_changed`, `orders_changed`)
  + audit + **PUT đổi code KiotViet best-effort** (fail → cảnh báo trong response).
- API `POST /api/products/{code}/rename` (admin). UI: chi tiết SP `#/kho/:code`
  ô sửa mã + confirm → navigate mã mới; mã cũ trong URL resolve qua history.

### Phase 6 — Dọn
- Gỡ `product_store/rename.py` bản cascade. CLAUDE.md + docs + memory.
- Đổi mã thử 1 SP thật end-to-end (đơn cũ, kho, bảng giá, tạo HĐ KiotViet, gõ mã
  cũ trong đơn mới).

## 3. An toàn & rollback
- `./scripts/backup_db.sh <nhãn>` trước MỖI phase (sqlite3 .backup, giữ 15 bản).
  Đã backup `pre-product-id` 2026-07-09 (app 334M + donhang + bot_sessions).
- Migration idempotent (check cột/bảng/marker) — chạy lại vô hại; backfill dở dang
  vô hại (thiếu sp_id → hiển thị fallback mã snapshot).
- Dual-write id+mã suốt phase 1–4 → rollback code về commit trước vẫn chạy bằng mã.
- `tools/verify_product_id.py` sau mỗi phase: tồn kho / bảng giá / coverage sp_id.
- Test: `./scripts/test.sh` (85 test cũ + test mới resolve/rename/price-id/backfill).

## 4. Rủi ro chính
| Rủi ro | Mức | Giảm thiểu |
|---|---|---|
| Migrate bảng giá sai → giá 0/sai tiền | CAO | verify từng khách diff=0 mới commit; _legacy không xoá; backup |
| Sót read path còn theo mã → hiển thị/tồn lệch sau đổi mã | VỪA | grep checklist theo 2 bản đồ khảo sát trong plan; dual-write; test đổi mã thật phase 6 |
| Backfill 16k blob RMW đụng writer đang chạy | VỪA | chạy trong boot guard TRƯỚC khi server nhận request; batch transaction |
| Rebuild products giữa chừng | THẤP | backup + transaction + idempotent |
| Mã tái dùng gây nhầm SP | THẤP | rule hiện-tại-thắng; đơn mới có sp_id nên hết mơ hồ |
