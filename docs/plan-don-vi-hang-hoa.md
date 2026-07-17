# Plan: Hệ đơn vị hàng hoá — 3 VAI trên đơn vị (nguyên kiện / hiển thị / kiểm kho)

> Chốt thiết kế 2026-07-17. Mục tiêu: `products.unit` chỉ còn ĐÚNG 1 nghĩa (đơn vị
> đếm/lưu số); mọi nghĩa khác đang nhồi vào nó tách ra thành VAI chỉ định trên đơn vị.
>
> **✅ ĐÃ TRIỂN KHAI đủ 6 phase cùng ngày 2026-07-17** (commit `44c22d69`…: Phase 0
> vai + backfill, Phase 1 UI chip, số gọi 27 block, Phase 2 nhập kiện 3 đường,
> Phase 3 ô thùng, Phase 4 kiểm kho nhập kép, Phase 5 guide + docs). File này giữ
> làm tài liệu thiết kế; trạng thái hiện hành xem CLAUDE.md mục "VAI ĐƠN VỊ".

## Mô hình

- 1 SP có 1 **đơn vị chính** (`products.unit` — mọi số trong DB lưu theo nó, không đổi)
  và nhiều **đơn vị phụ** quy đổi (`product_units`, factor = 1 phụ = ? gốc).
- Trên tập {gốc} ∪ product_units, mỗi SP chỉ định **tối đa 1 đơn vị cho mỗi VAI**:
  - **📦 NGUYÊN KIỆN** — nhập hàng bằng đơn vị này → mỗi đơn vị = **1 dòng thùng**
    (quantity = factor), **nhãn chứa = tên đơn vị** (không hỏi đơn vị chứa nữa).
    Thay thế luôn `self_container` suy-từ-tên-đơn-vị hiện tại.
  - **👁 HIỂN THỊ** — số trên ô thùng (BoxTile) MỌI NƠI quy đổi sang đơn vị này.
    Chỉ tầng hiển thị; mọi ô NHẬP liệu giữ đơn vị gốc.
  - **📋 KIỂM KHO** — phiếu kiểm kho bắt đếm bằng đơn vị này, kèm ô LẺ đơn vị gốc
    (`N thùng + M cây`); số sổ sách hiển thị cùng định dạng.

### Quyết định đã chốt (với user)
1. Đơn vị GỐC cũng chỉ định được làm nguyên kiện (SP self-container cũ kiểu KDXDB5).
2. Nhãn chứa của thùng = tên đơn vị nguyên kiện (text snapshot trên thùng, KHÔNG đi
   qua `inventory_units` — bảng đó chỉ còn phục vụ hàng xá nhập rời).
3. **1 đơn vị nguyên kiện = 1 dòng thùng** (mỗi kiện 1 số gọi riêng để điểm danh
   ngoài kho).
4. **Số gọi mở rộng sau 999**: … 998, 999, A001 … A999, B001 … Z999 rồi quay về
   001 (27 block × 999 = 26.973 số, vẫn hô được ngoài kho: "thùng A ba-bốn-bảy").

## Phase 0 — Schema + store (nền tảng, tự thân vô hại)

- `products` thêm 3 cột INTEGER NULL: `bulk_unit_id`, `display_unit_id`,
  `stocktake_unit_id`. Quy ước chung: **NULL = không chỉ định; 0 = đơn vị gốc;
  >0 = FK `product_units.id`** (cùng SP).
- Migration `db_migrate` marker `unit_roles_v1`: backfill
  `bulk_unit_id = 0 WHERE lower(trim(unit)) IN ('thùng','kiện')` — giữ nguyên hành
  vi self-container hiện tại.
- `product_store/queries.py`:
  - `_row()` bỏ dòng đè `self_container = is_self_container_unit(...)` (dòng 29);
    thay bằng `self_container = bulk_unit_id IS NOT NULL` (GIỮ key này trong payload
    cho client cũ). `_SELF_CONTAINER_UNITS`/`is_self_container_unit` chỉ còn dùng
    cho backfill + gợi ý UI.
  - `upsert_product` nhận 3 cột mới, validate: 0 hoặc id thuộc đúng SP.
- Helper thuần `product_store.unit_role(product, units, role) -> {name, factor}`
  (0 → `(products.unit, 1)`); unit-test.
- `product_store/units.py::delete_unit` **CHẶN** xoá đơn vị đang giữ vai
  (lỗi "Đơn vị đang được chỉ định … — gỡ vai trước"). `update_unit` đổi factor của
  đơn vị giữ vai: cho phép, client cảnh báo (Phase 1).
- API: mở rộng product update (patch 3 cột, quyền office như sửa đơn vị);
  GET product/units trả 3 vai resolve sẵn. Audit `product.unit_role_set`
  (+ nhãn trong `event_format`).

## Phase 1 — UI bảng đơn vị 3 vai

- `ProductUnits.tsx`: bảng = dòng đơn vị gốc + các đơn vị phụ; 3 cột radio
  📦/👁/📋 (tap lại = bỏ chọn); nút tắt "dùng đơn vị này cho cả 3".
  Cảnh báo khi sửa factor đơn vị đang giữ vai.
- `InventoryDetail.tsx`: bỏ hint khẳng định "đơn vị thùng/kiện = SP nguyên kiện"
  (dòng ~343–349) → thành GỢI Ý: đổi unit sang thùng/kiện thì nhắc bật vai 📦 cho
  đơn vị gốc.
- `api.ts` types + `updateProduct` patch mới.

## Phase 2 — Nhập kho nguyên kiện (MỌI đường tạo thùng)

- `inventory_boxes` thêm cột `unit_label TEXT` (snapshot tên đơn vị chứa);
  `add_boxes`/`update_box` nhận param. Hiển thị ưu tiên:
  `unit_label` > `unit_name` (join inventory_units cũ) > mặc định.
- Rule chung: dòng nhập có đơn vị == đơn vị nguyên kiện của SP (so theo VAI hiện
  hành, server tự resolve — không tin client) → tạo `N` dòng thùng, mỗi dòng
  `quantity = factor`, `unit_label = tên đơn vị`, bỏ qua picker đơn vị chứa.
- Điểm chạm:
  - **Nhập NCC**: `PurchaseGoodsModal` — dòng bulk vào chế độ rút gọn (chỉ nhập
    số kiện + vị trí; per khoá = factor; ẩn picker inventory_units).
    `purchase_goods.receive_goods` derive label server-side; validate trần theo
    base như cũ.
  - **Phiếu SX**: `ProductionBoxes.tsx` + route boxes — thành phẩm có vai 📦 →
    nhập "số kiện" tạo N dòng × factor, label auto.
  - **Hàng trả về**: `ReturnGoodsModal` nhánh "tạo thùng mới" cùng rule.
- **Mở rộng SỐ GỌI theo quyết định 4** (làm ĐẦU Phase 2 — trước khi 1-kiện-1-dòng
  tăng lượng số dùng; độc lập, ship riêng được):
  - `inventory_store/domain.py`: không gian số 1..26.973 (block 0 = không tiền tố,
    block 1–26 = 'A'–'Z'). `call_code(n)`: block 0 → `"047"`, block chữ →
    `"A047"`. `code_call_number`: nhận thêm dạng `^[A-Z]\d{3}$` (đúng 3 chữ số);
    dạng số trần + đuôi base36 mã cũ có gạch (`K2L-00A`) giữ nguyên, không va chạm
    (mã mới không có gạch, chữ đứng ĐẦU). `next_call_numbers`: MAX 26.973,
    Z999 quay về 001 — hết pool mới ValueError như cũ.
  - Hệ quả tốt: khoảng cách tái dùng số tăng 27× (số thường chỉ quay lại sau khi
    đi hết A–Z) — càng đỡ nhầm ngoài kho.
  - Bản đồ số gọi `#/so-thung` (`inventory_call_map.py` + `CallNumbers.tsx` đang
    hardcode 999): hiện block 001–999 mặc định, block chữ chỉ hiện khi block đó
    đã có số được cấp.
  - Tests `test_inventory_domain`: biên 999→A001, Z999→001, parse `A347`,
    mã cũ `K2L-00A` vẫn ra 10, loại `A47`/`AA47`.
- SP bulk = đơn vị gốc (factor 1) nhập 10 kiện → 10 dòng quantity 1 — đúng quyết
  định 3, khác hành vi gộp hiện tại (thấy được với người dùng).

## Phase 3 — Đơn vị hiển thị trên ô thùng

- Server: `list_boxes`/`get_box` join `products.display_unit_id → product_units`
  → thêm `display_unit_name`, `display_unit_factor` vào payload thùng. Rà các
  builder khác dùng ô thùng: purchase draft view (`purchase_goods_view`), boxes
  của phiếu SX, timeline kho — cho đi cùng 2 query trên hoặc bổ sung tương tự.
- Client `BoxTile`/`inventoryBoxTile`: có factor hiển thị → `current`/`total`
  ÷ factor; **chia hết → số nguyên, không → 1 chữ số lẻ**; nhãn đơn vị nhỏ trên ô
  (size regular/dense; mini chỉ tooltip); tooltip luôn dual
  ("85 cây = 2,8 Thùng"). Thanh fill giữ tỉ lệ (không đổi). KHÔNG đụng ô nhập.

## Phase 4 — Kiểm kho theo đơn vị bắt buộc

- Tạo phiếu (`inventory_store/stocktakes.py`): snapshot per item
  `count_unit_name`, `count_unit_factor` từ vai 📋 **tại thời điểm tạo** (NULL nếu
  SP không chỉ định — hành vi cũ). `resync` thêm dòng mới cũng snapshot lúc resync.
- `StocktakeDetail.tsx`: item có count unit → **2 ô nhập `[N] <đơn vị> + [M] <gốc> lẻ`**;
  sổ sách render cùng định dạng ("sổ: 2 Thùng + 25 cây"). Save gửi counted đã quy
  về base + raw (`counted_bulk`, `counted_loose`) lưu cột snapshot cho audit.
- `complete`/`apply`/dashboard hao hụt NL phụ KHÔNG đổi (đọc counted base như cũ).

## Phase 5 — Rã kiện + guards + docs + tests

- `box_return_material_handler` (inventory_routes.py:844): gate đổi
  `prod.self_container` → "SP có vai 📦" (payload đã derive sẵn ở Phase 0 nên chỉ
  đổi nguồn). Toán hoàn NL KHÔNG cần sửa — `recipe_needs(code, box.quantity)` đã
  nhận quantity base, kiện là đơn vị phụ thì quantity dòng = factor → tự đúng.
- Rà mọi chỗ đọc `self_container`/`is_self_container_unit` ngoài `_row()`
  (`inventory_routes`, `activity_format`, `app_factory`, webapp `api.ts`,
  `BoxDetail`, `InventoryDetail`) về cùng 1 nguồn.
- Guide mới trong `webapp/src/guides/` ("Đơn vị hàng hoá: 3 vai"); cập nhật
  CLAUDE.md mục product_store/inventory_store; nhãn event mới trong
  `event_format`.
- Tests: role resolver + validate + chặn xoá (`test_product_units_roles`);
  nhập kho bulk N dòng/label/trần (`test_purchase_goods`); kiểm kho mixed entry;
  gate rã kiện mới. Chạy `./scripts/test.sh` đủ bộ.

## Thứ tự ship & an toàn

`0 → 1` ship trước (chưa flow nào đọc vai — vô hại). `2`, `3`, `4` độc lập nhau,
ship từng phase. `5` chốt. Không migration phá huỷ: cột mới đều nullable, hành vi
cũ giữ nguyên qua backfill `bulk_unit_id=0`; client cũ vẫn đọc `self_container`.
