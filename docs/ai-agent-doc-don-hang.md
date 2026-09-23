# Hướng dẫn AI agent: đọc dữ liệu đơn hàng

Tài liệu này dành cho AI agent cần **tra cứu** đơn hàng của app Lê Trang Phát:
đơn đã giao chưa, đã nộp tiền chưa và nộp theo hình thức nào, khách đã trả bao
nhiêu, và lấy ảnh hoá đơn hoặc ảnh nộp tiền của đơn.

> **Chỉ ĐỌC.** Mọi cách dưới đây đều là đọc. Đừng tự `UPDATE` blob đơn hay gọi
> các API POST/DELETE: đơn gắn với KiotViet, két tiền và Telegram, sửa tay sẽ làm
> lệch dữ liệu ở những chỗ đó.

---

## 1. Dữ liệu nằm ở đâu

| Thứ cần | Nguồn |
|---|---|
| Đơn hàng (mọi trạng thái, tiền, hoá đơn) | SQLite `~/letrang-db/app.db`, bảng **`orders`**, cột **`json`** (1 blob JSON/đơn) |
| Metadata ảnh của đơn | cùng `app.db`, bảng **`order_images`** |
| File ảnh thật | `~/letrang-db/media/<thread_id>/<filename>` (env `ORDER_MEDIA_DIR`) |
| Tên người dùng | `web_users` (app.db) + `USER_NAMES` trong `bot_core/config.py` |

Có 2 cách đọc, chọn 1:

- **A. Đọc thẳng SQLite** (nhanh, không cần server chạy). Luôn mở **read-only**:
  `sqlite3 -readonly ~/letrang-db/app.db` hoặc trong Python
  `sqlite3.connect("file:" + path + "?mode=ro", uri=True)`.
- **B. Gọi REST API** của server ở `http://127.0.0.1:8090`. Gọi từ **chính máy
  Mac mini** (loopback) thì **không cần token**. Gọi từ máy khác (qua Tailscale)
  thì phải đăng nhập lấy token trước (xem mục 7). API đã tính sẵn nhiều thứ
  (còn nợ, tên người làm, ảnh gắn công đoạn), nên ít phải tự suy.

---

## 2. Tìm đơn

Khoá chính của đơn là **`thread_id`** (id topic Telegram của đơn, số dương, ví dụ
`516262`). Link trong app: `#/order/<thread_id>`.

Đơn đã xoá có `orders.deleted_at IS NOT NULL`. Luôn lọc `deleted_at IS NULL`.

```sql
-- 1 đơn
SELECT json FROM orders WHERE thread_id = 516262 AND deleted_at IS NULL;

-- đơn của 1 khách theo tên (không dấu thì dùng API search, xem dưới)
SELECT thread_id, order_created, json_extract(json,'$.customer_name')
FROM orders
WHERE deleted_at IS NULL AND json_extract(json,'$.customer_name') LIKE '%Phi Long%'
ORDER BY order_created DESC LIMIT 20;

-- đơn của 1 khách theo mã khách (nhanh, có index)
SELECT thread_id, order_created FROM orders
WHERE deleted_at IS NULL AND cust_key = '59'
ORDER BY order_created DESC LIMIT 20;

-- đơn theo mã hoá đơn KiotViet
SELECT thread_id FROM orders WHERE json_extract(json,'$.kiotvietInvoiceCode') = 'HD086870';
```

API tìm kiếm (không dấu, khớp tên khách + nội dung + mã SP):

```
GET /api/orders?search=phi%20long&limit=20&page=1
GET /api/orders?filter=chua_giao        # chua_soan | chua_giao | chua_nop | chua_nhan | pending | done
GET /api/order/<thread_id>              # chi tiết: {data: <blob>, user_names, chat_messages, ...}
```

Cột ảo tiện dùng trong bảng `orders` (đã có index):
`order_created` (= `$.created`), `cust_key` (mã khách), `is_done`,
`has_customer`, `nop_nhan_done`.

---

## 3. Cấu trúc blob đơn (các trường cần biết)

Ví dụ rút gọn (đơn thật 516262):

```jsonc
{
  "thread_id": 516262,
  "created": "2026-09-15T00:16:51.000Z",   // UTC! cộng 7 giờ ra giờ VN
  "text": "Phi long kddt3 2b k10lv87 20",  // nội dung đơn gốc
  "customer_name": "Bánh tráng Phi Long",
  "khach_hang_id": "59",                    // mã khách (đơn rất cũ: "khID")
  "ngay_giao": "2026-09-15T00:00",          // ngày hẹn giao
  "invoice": [ { "sp": "KDDT3", "sl": 2, "price": 390000, "sp_id": 101, ... } ],
  "vat": 0, "pvc": 0, "discount": 0,
  "kiotvietInvoiceID": 276554366,           // có = đã tạo HĐ KiotViet
  "kiotvietInvoiceCode": "HD086870",
  "khDebt": 890000.0,                       // nợ TỔNG của khách (mọi đơn) sau lần cập nhật gần nhất
  "stock_confirmed": { "at": "...+07:00", "by": "trinh" },  // đã chốt xuất kho
  "task_status": {                          // ★ trạng thái 5 công đoạn — xem mục 4
    "ban_hd":    { "done": true, "by": "duy",   "at": "...Z", "skip": false },
    "soan_hang": { "done": true, "by": "trinh", "at": "...Z", "skip": false, "note": "imgs:6499" },
    "giao_hang": { "done": true, "by": "tri",   "at": "...Z", "skip": false },
    "nop_tien":  { "done": true, "by": "tri",   "at": "...Z", "skip": false, "note": "tra_tien_mat;img:6507" },
    "nhan_tien": { "done": true, "by": "duy",   "at": "...Z", "skip": false }
  },
  "soan": true, "giao": true, "nop": true, "nhan": true,   // bản sao boolean của task_status
  "done_after_20250124": true,              // cả 5 công đoạn xong (done hoặc skip)
  "payments": [ { "amount": 1120000, "method": "Cash", "createdBy": "duy",
                  "created_at": "...Z", "old_debt": 2010000, "new_debt": 890000,
                  "id": "payment_...", "kiotvietData": { "code": "DH012712", ... } } ],
  "bypass_debt": false,                     // true = văn phòng ẩn đơn khỏi trang thu tiền
  "bo_theo_doi_no": false                   // true = bỏ theo dõi nợ
}
```

---

## 4. Trạng thái công đoạn (`task_status`)

5 công đoạn, theo thứ tự:

| Key | Nghĩa | Ai làm |
|---|---|---|
| `ban_hd` | Bán hoá đơn (tạo HĐ KiotViet) | văn phòng |
| `soan_hang` | Soạn hàng (lấy hàng, chụp ảnh) | kho |
| `giao_hang` | Giao hàng cho khách | người giao |
| `nop_tien` | Người giao **báo kết quả thu tiền** (nộp tiền về/khách nợ) | người giao |
| `nhan_tien` | Văn phòng **xác nhận đã nhận** tiền/toa từ người giao | văn phòng |

Mỗi công đoạn là `{done, skip, by, at, note?}`:

- `done: true`: đã làm xong. `skip: true`: bỏ qua công đoạn này, tính như xong.
- `at`: thời điểm, **ISO UTC** (đuôi `Z`). Đổi sang giờ VN thì cộng 7 giờ.
- `by`: người làm. Đơn mới là **username** web (`"tri"`, `"duy"`); đơn cũ là
  **id Telegram** dạng số (`1809874974`). Đổi ra tên qua `USER_NAMES`
  (`bot_core/config.py`, ví dụ `1809874974=Duy`) hoặc bảng `web_users`.
- Key vắng mặt = công đoạn **chưa làm**.

### 4.1 Đơn đã giao chưa?

```
đã giao  ⇔  task_status.giao_hang.done == true  (hoặc .skip == true)
```

- Thời điểm giao: `task_status.giao_hang.at`. Người giao: `task_status.giao_hang.by`.
- Có thể đọc nhanh cờ boolean `giao` (bản sao, luôn đồng bộ với task_status).
- `ngay_giao` chỉ là **ngày hẹn giao**, không có nghĩa là đã giao.

```sql
SELECT thread_id,
       json_extract(json,'$.task_status.giao_hang.done') AS giao_done,
       json_extract(json,'$.task_status.giao_hang.at')   AS giao_at,
       json_extract(json,'$.task_status.giao_hang.by')   AS giao_by
FROM orders WHERE thread_id = 516262;
```

### 4.2 Đã nộp tiền chưa, nộp theo hình thức nào?

Công đoạn `nop_tien` = người giao báo kết quả thu tiền ở nhà khách. **Kết quả
nằm trong `note`**, dạng `<mã>` hoặc `<mã>;img:<image_id>`. Lấy mã bằng
`note.split(";")[0]`.

| `note` (mã) | `done` | Ý nghĩa | Tiền đang ở đâu | Ảnh |
|---|---|---|---|---|
| `tra_tien_mat` | true | Khách **trả đủ tiền mặt**, người giao đã nộp về | két văn phòng | bắt buộc: ảnh tiền mặt + toa |
| `co_ky_toa` | true | Khách **nợ**, **có ký toa** | nợ của khách | bắt buộc: ảnh toa có chữ ký |
| `khong_ky_toa` | true | Khách **nợ**, **không ký toa** | nợ của khách | không có |
| `chieu_lay_tien` | **false** | Khách hẹn **chiều lấy tiền**, chưa thu được | người giao còn phải đi thu | không có |
| *(không có note)* | true | Đánh dấu xong mà không nói kết quả (đường cũ/lệnh tay) | **chưa rõ** | không có |
| bất kỳ | `skip: true` | Bỏ qua công đoạn nộp tiền | chưa rõ | không có |

Cách đọc:

- **Chưa nộp**: không có key `nop_tien`, **hoặc** `nop_tien.done == false`
  (thường đi kèm note `chieu_lay_tien`).
- **Đã nộp**: `nop_tien.done == true`. Xem mã note để biết khách trả hay nợ.
- `;img:<id>` ở đuôi note là **id ảnh** trong `order_images` (ảnh chụp lúc nộp,
  kind `nop_tien_task`). Xem mục 6.
- Đơn **đã giao** mà chưa có `nop_tien` = người giao đang giữ tiền/chưa báo. Hạn
  nộp là 17:00 VN cùng ngày giao (giao sau 17:00 thì hạn 17:00 hôm sau).

Công đoạn `nhan_tien` (văn phòng xác nhận): `done == true` là văn phòng đã nhận
tiền/toa. `note == "gtr"` là xác nhận qua lệnh Telegram `gtr`. Còn lại thường
không có note.

### 4.3 Khách đã trả bao nhiêu, còn nợ đơn này bao nhiêu?

"Nộp tiền" (`nop_tien`) là **báo cáo của người giao**. Tiền **thực sự ghi nhận**
là mảng **`payments`** (mỗi phần tử là 1 phiếu thu KiotViet):

```
tổng đơn  = Σ(price × sl) các dòng invoice + pvc + vat − discount
đã trả    = Σ payments[].amount
còn phải thu của ĐƠN NÀY = max(0, tổng đơn − đã trả)
```

- `method`: `"Cash"` (tiền mặt) hoặc `"Transfer"` (chuyển khoản).
- `createdBy`, `created_at`: ai ghi, lúc nào. `kiotvietData.code`: mã phiếu thu (`DH…`).
- Đừng dùng `hoadon.print_content.tongthanhtoan` làm tổng đơn: trường này **đã cộng
  nợ cũ** của khách.
- `khDebt` là nợ **của khách trên mọi đơn**, không phải nợ riêng đơn này.
- API đã tính sẵn: trong `GET /api/orders` mỗi dòng có `total`, `paid`, `remaining`.
- `sl` có thể là số lẻ (3.5), đừng ép `int`.

Tóm lại 3 câu hỏi về tiền là 3 nguồn khác nhau:

1. *Người giao báo gì?* → `task_status.nop_tien.note`
2. *Văn phòng đã nhận chưa?* → `task_status.nhan_tien.done`
3. *KiotViet đã ghi thu bao nhiêu?* → `payments`

---

## 5. Truy vấn mẫu

```sql
-- Trạng thái giao + nộp của 1 đơn
-- ⚠ phải đặt alias bảng (o.json): json_each() cũng có 1 cột tên "json",
--   viết trần `json` trong subquery sẽ đọc nhầm cột đó → da_tra = 0.
SELECT o.thread_id,
  json_extract(o.json,'$.customer_name')               AS khach,
  json_extract(o.json,'$.task_status.giao_hang.done')  AS da_giao,
  json_extract(o.json,'$.task_status.nop_tien.done')   AS da_nop,
  json_extract(o.json,'$.task_status.nop_tien.note')   AS nop_note,
  json_extract(o.json,'$.task_status.nhan_tien.done')  AS vp_da_nhan,
  (SELECT COALESCE(SUM(json_extract(p.value,'$.amount')),0)
     FROM json_each(json_extract(o.json,'$.payments')) p) AS da_tra
FROM orders o WHERE o.thread_id = 516262;

-- Đơn ĐÃ GIAO nhưng CHƯA NỘP (người giao đang giữ / chưa báo)
SELECT thread_id, json_extract(json,'$.customer_name'),
       json_extract(json,'$.task_status.giao_hang.by'),
       json_extract(json,'$.task_status.nop_tien.note')
FROM orders
WHERE deleted_at IS NULL
  AND order_created >= '2026-09-01'
  AND json_extract(json,'$.task_status.giao_hang.done') = 1
  AND COALESCE(json_extract(json,'$.task_status.nop_tien.done'),0) = 0
  AND COALESCE(json_extract(json,'$.task_status.nop_tien.skip'),0) = 0;

-- Thống kê kết quả nộp tiền trong tháng
SELECT substr(json_extract(json,'$.task_status.nop_tien.note'),1,
              instr(json_extract(json,'$.task_status.nop_tien.note')||';',';')-1) AS ma,
       count(*)
FROM orders WHERE deleted_at IS NULL AND order_created >= '2026-09-01'
GROUP BY 1 ORDER BY 2 DESC;
```

Python:

```python
import json, sqlite3, os
db = sqlite3.connect("file:" + os.path.expanduser("~/letrang-db/app.db") + "?mode=ro", uri=True)
row = db.execute("SELECT json FROM orders WHERE thread_id=? AND deleted_at IS NULL", (516262,)).fetchone()
o = json.loads(row[0])
ts = o.get("task_status") or {}
giao = ts.get("giao_hang") or {}
nop = ts.get("nop_tien") or {}
nop_code = (nop.get("note") or "").split(";")[0]
da_giao = bool(giao.get("done") or giao.get("skip"))
da_nop = bool(nop.get("done") or nop.get("skip"))
da_tra = sum(int(p.get("amount") or 0) for p in o.get("payments") or [])
```

---

## 6. Ảnh của đơn

### 6.1 Bảng `order_images`

1 dòng = 1 ảnh. Cột chính: `id`, `thread_id`, `filename` (bản đầy đủ), `thumb`
(bản nhỏ), `kind`, `uploaded_by`, `created_at` (epoch giây), `deleted_at`.

| `kind` | Là ảnh gì | `uploaded_by` thường gặp |
|---|---|---|
| `hoa_don` | **Ảnh hoá đơn KiotViet**, server tự render PNG khi tạo HĐ | `KiotViet HĐ` |
| `nop_tien_task` | **Ảnh nộp tiền** người giao chụp ở bước Nộp tiền (tiền mặt + toa, hoặc toa có chữ ký) | username người giao |
| `nop_tien` | **Ảnh phiếu thu** (nhận tiền), server tự render mỗi lần ghi thanh toán; hoặc ảnh nhận tiền chụp tay | `Phiếu thu` |
| `soan_hang` | Ảnh soạn hàng | username người soạn |
| `khac` | Ảnh khác | — |

- **Xoá mềm:** ảnh bị xoá vẫn còn dòng và file, chỉ có `deleted_at` khác NULL.
  Muốn ảnh còn hiệu lực thì lọc `deleted_at IS NULL`. Ảnh HĐ cũ bị xoá thường là
  do HĐ bị xoá/làm lại, hoặc ảnh render sai.
- Ảnh gắn đúng công đoạn: `task_status.nop_tien.note` đuôi `;img:<id>` là ảnh nộp
  tiền của lần báo đó; `task_status.soan_hang.note` = `imgs:<id>,<id>` là ảnh soạn.

### 6.2 Lấy file ảnh

**Cách A, đọc đĩa:**

```sql
SELECT id, kind, filename, thumb, uploaded_by, datetime(created_at,'unixepoch','+7 hours')
FROM order_images
WHERE thread_id = 516262 AND deleted_at IS NULL
  AND kind IN ('hoa_don','nop_tien_task','nop_tien')
ORDER BY created_at DESC;
```

Đường dẫn file: `~/letrang-db/media/<thread_id>/<filename>` (bản nhỏ: `<thumb>`).
Ví dụ: `~/letrang-db/media/516262/f3f2ded55c1043b4a01909b3df8b16fd.jpg`.
Agent có thể mở trực tiếp file này (ví dụ bằng Read tool) để xem ảnh.

**Cách B, qua API:**

```
GET /api/order/<thread_id>/images                     → {ok, images:[...]} (mới nhất trước, CÓ CẢ ảnh đã xoá mềm)
GET /api/order/<thread_id>/images/<image_id>/file             → file ảnh đầy đủ
GET /api/order/<thread_id>/images/<image_id>/file?size=thumb  → ảnh nhỏ
```

### 6.3 Ảnh hoá đơn: trường hợp chưa có ảnh

Đơn có `kiotvietInvoiceID` mà không có ảnh `hoa_don` (render nền từng lỗi, hoặc
HĐ tạo qua Telegram). Có 2 lựa chọn:

- `GET /api/order/<thread_id>/invoice-html`: HTML hoá đơn render trực tiếp từ
  KiotViet. Chỉ đọc, không ghi gì.
- `POST /api/order/<thread_id>/invoice-image/ensure`: nếu đã có ảnh thì trả ảnh
  đó; nếu chưa thì render PNG và **thêm vào gallery của đơn** rồi trả
  `{ok, image:{id, filename, ...}, created}`. Lệnh này **ghi dữ liệu** (thêm 1 ảnh
  vào đơn, hiện cho người dùng), nên chỉ gọi khi thật sự cần ảnh.

Lưu ý: ảnh HĐ ghi lại **nợ trước tại thời điểm render**. Sửa nợ sau đó không làm
ảnh cũ đổi theo.

---

## 7. Gọi API từ máy khác (cần token)

App đang public qua Tailscale Funnel và có bật chặn auth. Ngoài loopback thì phải
có token:

```
POST /api/auth/login   body {"username": "...", "pin": "..."}   → {token, ...}
```

Gửi kèm `Authorization: Bearer <token>` (hoặc `?token=` cho link mở file). Token
hết hạn sau 30 ngày; token hỏng/hết hạn trả **401**. Xin tài khoản từ người quản
trị, đừng dùng tài khoản của người khác vì mọi thao tác đều ghi lịch sử theo
người.

---

## 8. Bẫy thường gặp

- **Đơn cũ (trước ~06/2025) không có `task_status`**, và các cờ
  `soan/giao/nop/nhan` cũng trống. Với các đơn này không suy ra được đã giao/nộp
  hay chưa, hãy trả lời "không có dữ liệu", đừng kết luận là "chưa giao".
- **Giờ trong blob là UTC** (`created`, `task_status.*.at`, `payments[].created_at`).
  Riêng `stock_confirmed.at` có sẵn `+07:00`. Khi lọc hay báo "ngày" phải đổi sang
  giờ VN.
- `nop_tien.done == false` + note `chieu_lay_tien` nghĩa là **chưa nộp** (còn chờ
  thu). Vài đơn đời cũ có `done == true` với note này, hệ két coi đó là khách nợ.
- Nộp "xong" **không** có nghĩa khách đã trả: `co_ky_toa`/`khong_ky_toa` là khách
  **nợ**. Muốn biết tiền đã thu thật thì xem `payments`.
- `payments` có thể có nhiều lần thu, và 1 lần thu gộp nhiều đơn (cùng
  `payment_batch_id`) thì mỗi đơn chỉ ghi phần của nó.
- `bypass_debt == true`: văn phòng đã ẩn đơn khỏi trang thu tiền (không đòi nữa),
  dù `remaining > 0`.
- `order_images` có cả ảnh đã xoá mềm; API `/images` cũng trả cả chúng. Lọc
  `deleted_at` trước khi báo "đơn có ảnh HĐ".
- Mã SP trong `invoice[].sp` là **snapshot** lúc bán. Mã hiện hành tra qua
  `invoice[].sp_id` → `products.id`.

---

## 9. Code tham chiếu (nếu cần kiểm lại luật)

- Luật trạng thái 5 công đoạn: `order_store/domain.py` (`REQUIRED_STEPS`, `mark_task`).
- Dòng đơn trả cho dashboard (paid/remaining/nop_note/nop_img_id): `server_app/orders_api.py::_build_order_row`.
- Công thức tổng đơn: `server_app/customer_feed.py::_order_total_num`.
- Ý nghĩa mã nộp tiền → tiền nằm ở két nào: `cashbox_store/domain.py` (`_NOP_DEST`).
- Luồng nộp tiền trên app: `webapp/src/detail/NopTienWizard.tsx`.
- Ảnh: `order_images_store/images.py`, `server_app/image_routes.py`,
  `server_app/invoice_image.py` (ảnh HĐ), `server_app/receipt_image.py` (ảnh phiếu thu).
