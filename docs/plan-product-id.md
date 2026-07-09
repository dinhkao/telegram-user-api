# Plan: Product ID cố định — đổi mã SP tự do không vỡ liên kết

> Trạng thái: **CHỜ DUYỆT** — chưa code gì. Đánh giá xong sửa/duyệt plan này rồi mới làm.
> Mục tiêu: mã SP (`K10LT`…) chỉ còn là **nhãn nhập liệu/hiển thị**; danh tính thật là
> `products.id` bất biến. Đổi mã = update 1 ô, mọi liên kết nội bộ tự đúng.

---

## 0. Hiện trạng (khảo sát 2026-07-09)

Mã SP đang là khoá liên kết ở **3 tầng**:

### Tầng A — bảng quan hệ (FK bằng TEXT code)
| Bảng | Cột | Ghi chú |
|---|---|---|
| `products` | `code` = **PRIMARY KEY** | kv_id/kv_full_name (link KiotViet) nằm cùng row → theo row, không lo |
| `inventory_boxes` | `product_code` | tồn kho, pool gom theo mã |
| `product_recipes` | `product_code`, `ingredient_code` | BOM 2 chiều |
| `production_slips` | `sp_name` | mã SP của phiếu SX |
| `production_report_rows` | `product_code` | dashboard SX |

### Tầng B — JSON blob (key = mã, KHÔNG phải cột)
| Chỗ | Cấu trúc | Quy mô |
|---|---|---|
| Bảng giá chung | `kv_store['bang_gia_moi']` = `{id_bảng: {price_list: {MÃ: giá}}}` | 3 bảng giá |
| Bảng giá riêng | `customers.$.personal_price_list` = `{MÃ: giá}` | **213 khách** |
| Invoice items trong blob đơn | `{"sp": "K10LT", ...}` | ~16k đơn lịch sử |

### Tầng C — text + nhập tay (không thể id hoá)
- Parser đơn (`order_store/free_text.py`): user gõ `"k10lt 2t 50"` → match theo mã.
- Lệnh Telegram, phiếu in, tem thùng, Google Sheets bot (đang tắt).
- `SP_INFO` (config cứng `bot_core/config.py`): map mã → mâm/lượng mặc định (legacy).

**Kết luận khảo sát**: tầng A id hoá được trọn; tầng B migrate key mã→id được;
tầng C bất khả kháng — mã vĩnh viễn là interface con người, nên mã vẫn phải
UNIQUE và parser vẫn match theo mã, chỉ khác là resolve ra id ngay khi ghi.

---

## 1. Thiết kế đích

```
products:  id INTEGER PRIMARY KEY   ← danh tính BẤT BIẾN, mọi liên kết nội bộ dùng nó
           code TEXT UNIQUE NOT NULL ← nhãn nhập liệu/hiển thị, ĐỔI TỰ DO
           (name, cost_price, unit, kv_id, … giữ nguyên)

product_code_history:  product_id, old_code, new_code, changed_at, changed_by
           ← nhật ký đổi mã. Bonus: parser tra mã CŨ vẫn nhận ra SP (alias miễn phí),
             tra "đơn theo SP" khớp cả đơn lịch sử mang mã cũ.
```

Nguyên tắc chuyển đổi:
- **Ghi**: mọi chỗ ghi mới lưu `product_id` (kèm mã snapshot nếu là bản ghi lịch sử).
- **Đọc**: join `products ON id` lấy mã/tên/đơn vị hiện hành — hiển thị luôn tươi.
- **Nhập liệu**: resolve mã→id tại choke point (parser, API nhận `product_code`);
  mã cũ resolve qua `product_code_history`.
- **Lịch sử** (blob đơn, hoá đơn in): giữ mã snapshot — KHÔNG sửa quá khứ.

---

## 2. Các phase (mỗi phase: code + migrate + test + commit riêng, chạy được độc lập)

### Phase 0 — Nền móng (không đổi hành vi)
1. Rebuild bảng `products` (SQLite không đổi PK được):
   `CREATE TABLE products_new (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT NOT NULL UNIQUE, …)`
   → copy data → drop/rename. Chạy trong migration guard lúc boot (idempotent).
2. Tạo `product_code_history` (trống).
3. `product_store`: `get_product_by_id`, `resolve_code(code) -> id` (kèm tra history),
   cache products đổi sang keyed-by-id + index code→id.
4. API `/api/products*` trả thêm `id` trong mọi payload (webapp type thêm `id?`).

*Rủi ro*: rebuild bảng products — backup file DB trước khi chạy (xem §4).
*Ước lượng*: ~½ ngày. Sau phase này hệ chạy y hệt cũ.

### Phase 1 — Kho + công thức (tầng A phần 1)
1. `inventory_boxes` + `product_recipes`: thêm cột `product_id` / (`product_id`,
   `ingredient_id`), backfill `UPDATE … SET product_id = (SELECT id FROM products WHERE code = product_code)`.
2. Mọi WRITE (add_boxes, set_recipe_line, allocate/fifo, transfer) ghi **cả 2** cột
   (id + code snapshot) — code column giữ lại làm hiển thị nhanh + rollback.
3. Mọi READ đổi sang join theo id (`list_boxes`, `get_box`, pool tồn, recipe_needs,
   stock picker `/api/inventory/*`, `sum_boxes_by_source`, validate đóng gói).
4. Thùng mồ côi (mã không còn trong products): backfill để NULL + log cảnh báo,
   liệt kê ra để xử tay (không tự đoán).

*Ước lượng*: 1 ngày. *Test chốt*: tổng tồn từng SP trước = sau migrate (script so sánh).

### Phase 2 — Sản xuất
1. `production_slips.product_id` + `production_report_rows.product_id`: thêm cột,
   backfill theo `sp_name`/`product_code`, dual-write chỗ `set_sp`/`set_bang`/`report_rows`.
2. Reads: `build_production_row`, dashboard SX, worker detail, ProductPicker.
3. `SP_INFO` giữ nguyên (legacy, chỉ cấp default mâm/lượng — tra theo mã hiện hành).

*Ước lượng*: ½ ngày. *Test chốt*: dashboard SX số liệu trước = sau.

### Phase 3 — Bảng giá (phần NHẠY nhất: tiền)
1. Migrate key: `{MÃ: giá}` → `{"<id>": giá}` cho bảng giá chung (3 bảng) +
   `personal_price_list` (213 khách) — 1 transaction, có script verify từng khách
   (giá theo mã trước == giá theo id sau, diff = 0 mới commit).
2. `get_customer_price_list` trả dict **code-hiện-hành → giá** (build từ id→code join)
   → parser + mọi caller giữ nguyên interface, không đụng.
3. Editor bảng giá (webapp + lệnh Telegram bang_gia): đọc/ghi theo id, hiển thị mã live.

*Ước lượng*: 1 ngày (nửa ngày code, nửa ngày verify). *Test chốt*: parse 20 đơn mẫu
ra giá y hệt trước migrate; chỉnh giá 1 SP qua editor → parse ăn giá mới.

### Phase 4 — Đơn hàng (mới đi tới, cũ giữ nguyên)
1. Choke point `freeze_invoice_cost_prices` + `parse_invoice_free_text`: item mới
   có thêm `sp_id` (mã `sp` vẫn giữ — snapshot lịch sử).
2. `product_orders` (đơn theo SP, json_each): query theo `sp_id` cho đơn mới, fallback
   `sp IN (mã hiện hành + mọi mã cũ từ history)` cho đơn cũ → tra cứu KHÔNG đứt sau đổi mã.
3. Profit/analysis: `get_product` theo id-first, fallback mã.

*Ước lượng*: ½–1 ngày. *Test chốt*: test_parsers + test_profit pass; đơn cũ vẫn hiện
đúng trong "đơn theo SP" sau 1 lần đổi mã thử.

### Phase 5 — Tính năng đổi mã (điểm đến)
1. `rename_product(id, new_code)`: UPDATE products.code + INSERT history + invalidate
   cache + emit (`inventory_changed`, `price_lists_changed`). KHÔNG cascade gì nữa —
   vì không còn gì trỏ theo mã.
2. Cập nhật cột mã snapshot denormalized còn lại (inventory_boxes.product_code…) —
   1 UPDATE mỗi bảng, thuần hiển thị, lệch cũng không sai logic.
3. Parser: mã cũ resolve qua history → gõ mã cũ vẫn nhận (đúng ý "không ảnh hưởng chỗ khác").
4. UI: chi tiết SP (admin) — ô sửa mã + confirm; đổi xong navigate route mã mới.
5. Route webapp `#/kho/:code` GIỮ theo mã (thân thiện); link cũ sau đổi mã sẽ resolve
   qua history → redirect mã mới.

*Ước lượng*: ½ ngày.

### Phase 6 — Dọn (tuỳ chọn, sau khi chạy ổn ≥1 tuần)
- Drop các cột `product_code` TEXT ở bảng quan hệ (hoặc giữ vĩnh viễn làm snapshot — đề xuất GIỮ).
- Gỡ `product_store/rename.py` bản cascade (được thay bằng rename theo id).
- Cập nhật CLAUDE.md + docs.

**Tổng ước lượng: 3.5–4.5 ngày làm tuần tự, hệ thống chạy bình thường giữa các phase.**

---

## 3. Những thứ CỐ Ý không làm
- **Không sửa blob đơn cũ** — lịch sử là snapshot (hoá đơn đã in, tiền đã thu).
- **Không id hoá tầng nhập liệu** — mã vẫn là thứ con người gõ; id vô hình với người dùng.
- **Không đụng sheets_bot** (đang tắt) — ghi chú TODO nếu bật lại.
- **Không migrate `SP_INFO`** (config legacy) — tra theo mã hiện hành là đủ.
- **Không đổi mã thùng/số gọi** — không liên quan.

---

## 4. An toàn & rollback
- Trước MỖI phase có migrate: `cp ~/letrang-db/app.db ~/letrang-db/backup/app-pre-phaseN-<ts>.db`
  (script tự làm, giữ 10 bản gần nhất).
- Migration idempotent (check cột/bảng tồn tại trước khi ALTER) — chạy lại vô hại.
- Dual-write (id + mã) suốt phase 1–4 → rollback code về commit trước là chạy lại
  bằng mã như cũ, data không hỏng.
- Script `tools/verify_product_id.py`: so tổng tồn/giá/boxed_total giữa 2 cách tính
  (theo mã vs theo id) — chạy sau mỗi phase, diff ≠ 0 là dừng.
- Mỗi phase 1 commit, deploy + quan sát thật rồi mới phase kế.

## 5. Rủi ro chính
| Rủi ro | Mức | Giảm thiểu |
|---|---|---|
| Bảng giá migrate sai → parse giá 0/sai tiền | CAO | script verify diff=0 mới commit; giữ key cũ trong backup |
| Sót 1 chỗ đọc theo mã → tồn kho ma sau đổi mã | VỪA | dual-write + verify script + grep checklist §0 |
| Thùng/recipe mã mồ côi khi backfill | THẤP | để NULL + báo cáo xử tay |
| Rebuild bảng products giữa chừng | THẤP | backup + transaction + idempotent |

## 6. Câu hỏi chốt trước khi làm
1. Gõ **mã cũ** trong tin nhắn đơn sau khi đổi → tự nhận SP mới (qua history)? *(plan: CÓ)*
2. Route `#/kho/:code` giữ theo mã + redirect mã cũ? *(plan: CÓ)*
3. Migration chạy lúc boot server (tự động) hay chạy tay từng phase? *(plan: tự động lúc boot, có backup)*
4. Ai được đổi mã? *(plan: admin only)*
