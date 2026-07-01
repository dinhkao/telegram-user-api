# Kế hoạch chuyển SQLite → PostgreSQL

Mục tiêu: chuyển `app.db` (shared SQLite) sang PostgreSQL, **bảo toàn 100% dữ liệu
hiện có**, và chuyển **toàn bộ code Python** sang gọi Postgres — không mất hành vi,
không downtime dài, mỗi bước xanh test.

Nền tảng đã đọc: `docs/senior-review.md` (lộ trình strangler), schema thật của
`app.db`, và scope code thật (đo ngày lập kế hoạch).

---

## ⚡ TRẠNG THÁI: ĐÃ CUTOVER — APP ĐANG CHẠY POSTGRES (2026-07-02)

`server.py` đang chạy trên PostgreSQL (docker `letrang-pg`, volume bền
`letrang_pg_data`, `restart=unless-stopped`, cổng **5433**). app.db LIVE (17016 đơn)
đã migrate, verify byte-identity ✅, không ghi SQLite nữa.

- **Khởi động lại app:** `./scripts/start-pg.sh` (export env rồi launch — KHÔNG dùng
  `python server.py` trần vì mặc định về SQLite).
- **Backup rollback:** `~/letrang-db/app.db.precutover-20260702-000127` (SQLite nguyên
  trạng ngay trước cutover).
- **ROLLBACK về SQLite:** dừng app (`pkill -f server.py`) → chạy `python server.py`
  KHÔNG export DB_ENGINE (mặc định sqlite). ⚠️ Mọi write phát sinh trên PG sau cutover
  sẽ KHÔNG có trong app.db — chỉ rollback khi chấp nhận mất chúng, hoặc migrate ngược.
- **Test:** `./scripts/test.sh` luôn ép `DB_ENGINE=sqlite` (94/94), không đụng PG.

---

## QUYẾT ĐỊNH CHỐT (đọc trước)

Ba yêu cầu cứng của chủ dự án: **(1) người dùng không hề hay biết · (2) DB portable
· (3) data y hệt trước/sau.**

**Chiến lược: 2 BƯỚC, không big-bang.**
- **Bước 1 (migration này):** chuyển engine sang Postgres, **cột `json` GIỮ NGUYÊN
  `TEXT`** (byte-identical). Đạt cả 3 req ngay, rủi ro thấp. KHÔNG chuẩn hóa cùng lúc.
- **Bước 2 (sau, tách riêng):** chuẩn hóa dần sau `Order` façade — mỗi field thành
  cột riêng, **0 JSON** ở đích — nhưng từng key một, có round-trip test, luật ép
  kiểu tiền do chủ dự án chốt. Xem §6.

**Ba sửa bắt buộc để đạt 3 req** (khác bản nháp đầu):
1. **Cột `json` = `TEXT`, KHÔNG `jsonb`.** `jsonb` bỏ whitespace, đổi thứ tự key,
   gộp key trùng, chuẩn hóa số → **đổi bytes** → vỡ req 3. Query/index qua expression
   `(json::jsonb ->> 'x')` — bytes vẫn y nguyên.
2. **Pin `COLLATE "C"` + `NULLS FIRST/LAST`** mọi `ORDER BY`. SQLite mặc định BINARY
   + NULLs-first; PG mặc định locale + NULLs-last → **đảo thứ tự list user thấy** nếu
   không pin → vỡ req 1.
3. **KHÔNG migrate `orders_fts`.** Nó là cache dựng lại mỗi boot từ `orders`, query
   bằng `LIKE` (không phải `MATCH`/trigram ranking). Dựng lại lúc boot trên PG →
   `LIKE` chạy y hệt, 0 rủi ro parity. (FTS `MATCH` thật chỉ ở `donhang.db` — giữ
   SQLite.)

Thêm: **chạy PostgreSQL local (unix socket)** khi cutover để không thêm latency
(req 1). Portable giữ qua `DATABASE_URL` + docker-compose (req 2).

---

## 0. Bối cảnh & ràng buộc (đã xác minh)

- **Node đã bị cắt** (commit `e914f449`, phase 4). Không còn `_call_final_telegram`,
  không còn HTTP `:3000`. **Python là writer duy nhất của `app.db`.**
  → Không cần dual-write tới process ngoài. Đây là điều làm migration khả thi sạch.
- `kv_store(path, value)` giờ chỉ là **bảng KV nội bộ Python** (product search, bảng
  giá mới, `hddt_ignore_patterns`, bot_core config). Giữ nguyên như 1 bảng thật,
  KHÔNG phải cầu nối Firebase/Node nữa.
- **Connection chưa tập trung.** Ngoài `order_store._get_connection`, các store sau
  tự mở `sqlite3.connect`: `command_handlers/{what_data,newkh_handler,gtr_handler,
  bang_gia_commands,note_commands,production_commands}`, `donhang_store/api.py`,
  `audit/db.py`, `chat_log/db.py`, `bot_core/{db,session_store}.py`,
  `server_app/orders_db.py`. **Phải gom trước khi swap.**
- App là async (Telethon + aiohttp) nhưng DB call là **sync** (`sqlite3`). Giữ nguyên
  mô hình sync để giảm churn (xem §3 driver).

### Bề mặt code phải đổi (đo thật)
| Thứ | Số chỗ | Ghi chú chuyển đổi |
|---|---|---|
| File chạm conn/sqlite | 53 | |
| `_get_connection()` call | 28 | thay bằng adapter dùng chung |
| Raw SQL execute (SELECT/INSERT/UPDATE/DELETE/CREATE) | 86 | phần lớn giữ nguyên; đổi placeholder |
| `json_extract` / `json_set` / `json(` | 80 | **nặng nhất** — cú pháp JSON khác hẳn |
| `INSERT OR REPLACE/IGNORE`, `ON CONFLICT` | 12 | → `ON CONFLICT ... DO UPDATE` (PG có sẵn) |
| `PRAGMA` | 33 | bỏ hết (WAL/busy_timeout là khái niệm SQLite) |
| FTS5 / `MATCH` / VIRTUAL TABLE | 6 | → `pg_trgm` / `tsvector` |
| `sqlite3.Row` / `row_factory` | 17 | → `RealDictCursor` (psycopg) |

Hai điểm đau chính: **(a) 80 chỗ JSON function**, **(b) FTS5 `orders_fts` trigram**.
Mọi thứ còn lại là cơ học.

### Phạm vi DB
- **`app.db`** (`~/letrang-db/app.db`) → **PostgreSQL**. Đây là trọng tâm: giá trị
  cao, đồng thời, tiền thật.
- `donhang.db`, `bot_sessions.db`, `chat_log`, `audit` — SQLite local, **rebuildable
  hoặc ít giá trị**. Giai đoạn 1 **giữ SQLite**. Cân nhắc chuyển sau khi `app.db`
  ổn (giảm rủi ro, giảm bề mặt cùng lúc).

---

## 1. Nguyên tắc chỉ đạo

1. **Strangle, không rewrite.** Live order/money system — mỗi bước giữ hành vi y hệt,
   xanh test (`./scripts/test.sh`, 85 test), có thể rollback.
2. **Lift-and-shift TRƯỚC, chuẩn hóa SAU.** Giai đoạn đầu bê **nguyên schema blob**
   sang Postgres (cột `json` giữ `TEXT`, xem QUYẾT ĐỊNH CHỐT), KHÔNG chuẩn hóa cùng
   lúc. Chuẩn hóa (tách
   `order_items`, bỏ `debt`, FK…) là lộ trình riêng SAU khi đã chạy trên PG. Trộn 2
   việc = tự sát.
3. **Một cổng DB duy nhất.** Mọi truy cập đi qua 1 adapter (`utils/db.py`) → swap
   engine ở 1 nơi.
4. **Migration data phải verify được.** Đếm dòng, checksum blob, so mẫu trước/sau.

---

## 2. Các giai đoạn

### Phase A — Gom connection về một cổng (không đổi engine)
Vẫn SQLite. Mục tiêu: mọi store lấy connection từ **một** chỗ.

- Tạo `utils/db.py`: `get_connection()` + `transaction(conn)` (bê từ
  `order_store/schema.py`). Trả về đối tượng có API `conn.execute(sql, params)`,
  `.fetchone/.fetchall`, row-as-dict.
- Chuyển 12+ store đang tự `sqlite3.connect` sang gọi `utils.db.get_connection()`.
  `order_store._get_connection` thành shim mỏng gọi vào `utils.db`.
- **Không đổi SQL.** Chỉ đổi nguồn connection.
- ✅ Xanh test. Đây là bước an toàn nhất, tạo điểm swap.

### Phase B — Chuẩn hóa placeholder & SQL SQLite-riêng (vẫn SQLite)
Làm code SQL trở nên "PG-ready" trong khi vẫn chạy SQLite.

- Placeholder: SQLite `?` → Postgres `%s`. Cách an toàn: adapter dịch `?`→`%s` khi
  swap, HOẶC đổi dần sang named params `:name` (cả 2 driver hỗ trợ qua wrapper).
  Khuyến nghị: **giữ `?` trong code, adapter dịch** → không đụng 86 site.
- `INSERT OR REPLACE/IGNORE` (12 chỗ) → viết lại thành `ON CONFLICT ... DO UPDATE/
  DO NOTHING` (cú pháp này chạy CẢ SQLite mới lẫn PG → đổi 1 lần, chạy 2 nơi).
- Cô lập **JSON functions** (80 chỗ): bọc `json_extract(col,'$.x')` sau helper
  `utils/db.py::json_get(col, path)` phát SQL đúng theo engine. Đây là phần tốn công
  nhất — làm từng store, có test.
- Cô lập **FTS search** (`order_store/search.py`, `orders_fts`): đưa toàn bộ truy vấn
  tìm kiếm sau 1 interface `search_products()/search_orders()` (đã gần vậy) để Phase D
  chỉ đổi 1 chỗ.
- ✅ Xanh test sau mỗi store.

### Phase C — Dựng schema Postgres (lift-and-shift, blob giữ nguyên)
- File `migrations/pg/0001_init.sql`: tạo mọi bảng **giống hệt** cấu trúc hiện tại,
  chỉ đổi kiểu:
  - `json TEXT` → **`TEXT`** (GIỮ NGUYÊN — byte-identical, xem QUYẾT ĐỊNH CHỐT sửa 1).
    Query/index qua expression `(json::jsonb ->> 'x')`, KHÔNG lưu cột jsonb.
  - `updated_at INTEGER` (epoch) → giữ `bigint` (KHÔNG đổi ý nghĩa ở phase này)
  - `TEXT PRIMARY KEY` (firebase_key) → giữ nguyên (chuẩn hóa sau)
  - Generated columns `nop_nhan_done`, `order_created` → PG `GENERATED ALWAYS AS
    (...) STORED` cast text sang jsonb tại chỗ:
    `((json::jsonb #>> '{task_status,nop_tien,done}'))`.
  - Index `json_extract(...)` → PG **expression index** `((json::jsonb ->> 'x'))`.
  - `orders_fts` → **KHÔNG migrate** (xem QUYẾT ĐỊNH CHỐT sửa 3). Dựng lại lúc boot
    thành bảng thường, query `LIKE`. Không cần `pg_trgm`.
  - `kv_store`, `products`, `notes`, `bang_gia_slips`, `production_slips`,
    `order_chat_messages`, `customers`, `tasks`, `order_key_by_*`,
    `order_discussion_mirror`, `kv_revisions` → bê thẳng.

### Phase D — Data migration (bảo toàn 100%)
Script `tools/migrate_sqlite_to_pg.py`:
1. Đọc từng bảng SQLite → ghi Postgres theo batch (`execute_values`).
2. `json TEXT` **ghi nguyên bytes** vào cột `TEXT` (chỉ validate parse được để bắt
   blob hỏng NGAY — KHÔNG reserialize, giữ byte-identity).
3. **Verify:**
   - `COUNT(*)` mỗi bảng khớp (orders=17016, tasks=18220, customers=344,
     products=22, kv_store=914, order_chat_messages=2926 — số tại thời điểm lập KH).
   - Checksum: `md5(sorted json)` từng bảng khớp giữa 2 DB.
   - So 50 đơn mẫu field-by-field.
   - FTS: đếm kết quả 1 tập query mẫu khớp (chấp nhận sai số nhỏ do trigram engine
     khác — log ra).
4. Idempotent (chạy lại được), chạy trên **bản copy** app.db trước.

### Phase E — Swap engine (1 công tắc)
- `utils/db.py::get_connection()` đọc env `DB_ENGINE=sqlite|postgres` +
  `DATABASE_URL`. Mặc định vẫn `sqlite` cho tới khi verify xong.
- Driver: **psycopg 3 (sync)** — API `conn.execute/cursor` gần `sqlite3` nhất, giảm
  churn tối đa. Row = `dict_row`. (App vốn đã block sync trên event loop với sqlite —
  không tệ hơn. Chuyển async/`asyncpg` là việc tối ưu SAU, không thuộc migration.)
  - `transaction()`: PG mặc định KHÔNG autocommit → `BEGIN`/`COMMIT` tự nhiên, bỏ
    `BEGIN IMMEDIATE` (PG dùng MVCC, không cần). Giữ chữ ký hàm.
  - Bỏ mọi `PRAGMA` (33 chỗ) khi engine=postgres.
  - Placeholder `?`→`%s` do adapter dịch.
- Chạy song song: DB_ENGINE=postgres trên **staging/bản copy** trước, đối chiếu hành
  vi với sqlite prod vài ngày.

### Phase F — Cutover
- Freeze ngắn (đóng process), chạy migration lần cuối (delta), đặt
  `DB_ENGINE=postgres`, khởi động lại `server.py`. Giữ file SQLite làm backup
  read-only.
- Theo dõi. Rollback = đổi env về `sqlite` (dữ liệu ghi trong lúc PG chạy phải
  migrate ngược nếu rollback — nên cửa sổ theo dõi ngắn & có kịch bản).

### Phase G (BƯỚC 2, tách riêng) — Chuẩn hóa: mỗi field 1 cột, 0 JSON
Đích chủ dự án muốn: **không JSON trong DB, mỗi field 1 cột.** Đây là bước 2, làm
SAU khi đã chạy ổn trên PG. **Không mechanical được** — xem §6 (bằng chứng blob).

Cách làm an toàn (không big-bang 137 cột):
1. **Phân loại 137 key orders** (§6): mỗi key → giữ-thành-cột / ép-kiểu / bỏ (chết) /
   → bảng con. Chủ dự án duyệt luật, đặc biệt **luật ép kiểu tiền** (`khDebt` float).
2. Promote **key sạch tần suất cao trước** (`created, thread_id, channel_id,
   message_id, status, done, flow_version`), từng cái, sau `Order` façade.
3. Mảng → **bảng con** (`invoice[]`→`order_items`, `nguoi_giao_hang[]`, `media[]`);
   dict lồng → cột prefix hoặc FK (`khach_hang{}`→FK `customers`).
4. `personal_price_list{75 mã}` → bảng `customer_prices(customer_id, code, price)`.
5. Đích cuối: tách `payments` ledger, bỏ `debt` lưu sẵn, thêm FK, `firebase_key` PK →
   cột thường, timestamp về `timestamptz`. Mỗi bước round-trip test 16992 blob.
6. Key bẩn/thưa/version-drift để trong **vùng chờ** (cột `extras` tạm hoặc bảng EAV)
   tới khi hiểu & làm sạch từng cái — KHÔNG bỏ mù.

**"Y hệt" ở bước 2 = tái dựng không mất mát** (façade dựng lại đúng dict mỗi consumer
cần), verify bằng round-trip toàn bộ blob — KHÔNG phải byte-identity (vì cố ý đập cấu
trúc). Tương phản: bước 1 LÀ byte-identity.

---

## 3. Quyết định kỹ thuật chốt
- **Driver: psycopg 3 sync** (không asyncpg) — ưu tiên ít churn hơn tối ưu.
- **jsonb, không chuẩn hóa vội** — lift-and-shift, giữ hành vi.
- **1 adapter `utils/db.py`** dịch placeholder + JSON funcs + engine switch.
- **`?` giữ nguyên trong code**, adapter dịch → không đụng 86 SQL site cho placeholder.
- **FTS5 → pg_trgm** (tương đương trigram gần nhất).
- **donhang.db & các DB local: để SQLite** ở giai đoạn này.

## 4. Rủi ro
- **80 chỗ JSON function** — cao nhất. Giảm bằng helper tập trung + test từng store.
- **FTS trigram khác engine** → thứ hạng/kết quả tìm kiếm lệch nhẹ. Chấp nhận + log,
  hoặc tinh chỉnh `pg_trgm` threshold.
- **Blob hỏng ẩn** — Phase D validate parse sẽ lộ ra; xử lý trước cutover.
- **Money/epoch semantics** — KHÔNG đổi ở migration này (giữ bigint epoch, giữ số
  tiền như cũ) để cô lập biến. Đổi = Phase G.

## 5. Thứ tự làm (tóm tắt)
A gom conn → B chuẩn hóa SQL (vẫn SQLite) → C schema PG → D migrate+verify →
E swap sau adapter → F cutover → (G chuẩn hóa, sau).
Mỗi phase độc lập xanh test và rollback được.

---

## 6. Bằng chứng blob (profiling data thật — nền cho bước 2)

Quét toàn bộ blob còn sống (`deleted_at IS NULL`) ngày lập kế hoạch:

| Bảng | Rows | Key khác nhau | Ghi chú |
|---|---|---|---|
| orders | 16992 | **137** | chỉ ~7 key phủ 98-99%; đuôi dài thưa; có key tên `0` |
| customers | 343 | 23 | `personal_price_list` = 75+ mã SP lồng trong |
| tasks | 18220 | 24 | sạch nhất |

**Landmine kiểu lẫn lộn (phải ép kiểu khi promote — mỗi cái là 1 quyết định data):**
- `done` bool+str · `thread_id` int+str · `khach_hang_id` str+int · `invoice` list+int
  · `price_list` int+str · `kh_id` int+str · `updated_at` str+int
- **TIỀN là float (đụng luật kinh doanh):** `khDebt` int + **float×362** ·
  `invoice_debt_snapshot` int+float×361+None · `first_debt` int+float×1 · `vat` int+float
- **Trôi phiên bản nướng trong bảng:** `flow_version`, `data_structure_version`,
  `done_after_20250124`, `money_floating` vs `money_floating_boolean`.

**Lồng nhau → bảng con (không thể là cột):**
- Mảng: `invoice[]` (→`order_items`: note,price,qc_type,sl,sl1pc,so_qc,sp),
  `nguoi_giao_hang[]`, `nguoi_soan_hang[]`, `media[]`(file_id,type)
- Dict: `khach_hang{}`(debt,kh_id,name,price_list,thread_id,latest_hd…),
  `hoadon{}`, `task_status{}`, `current_view{}`
- `personal_price_list{75+ mã}` → `customer_prices(customer_id, code, price)`

Kết luận: full-normalize **không map cơ học được** — cần phân loại từng key + luật ép
kiểu (nhất là tiền float) do chủ dự án chốt. Vì vậy để BƯỚC 2 (§Phase G), sau khi
bước 1 (PG + blob TEXT) đã chạy ổn.

## 7. Trạng thái
- ✅ Chiến lược chốt: 2 bước (PG blob-TEXT → chuẩn hóa dần).
- ✅ Profiling blob xong (§6).
- ✅ **Phase A — cổng connection `utils/db.py`.** `get_connection(path, *, readonly,
  autocommit, busy_timeout)` + `transaction()`. 9 site trên `app.db` đã gom:
  `order_store.schema._get_connection`, 5 handler (`newkh/gtr/bang_gia/note/
  production`), `what_data` (readonly), `chat_log.db.connect_db` (autocommit off),
  `server_app.orders_db.get_orders_conn` (autocommit off). Hành vi giữ y hệt từng
  biến thể. 85/85 test xanh.
  - **Follow-up (còn tự connect `app.db`, ngữ nghĩa đặc biệt — chưa gom):**
    `bot_core/db.py` (thread-local + `_migrate` + `foreign_keys=ON`) và `audit/db.py`
    (path tham số). Gom sau khi `utils.db` hỗ trợ thread-local/extra-pragma, hoặc lúc
    swap engine.
  - Ngoài scope (DB khác): `donhang_store/api.py`, `bot_core/session_store.py`.
- ✅ **Phase B — SQL PG-ready qua adapter (không sửa 86 site).** Thay vì viết lại từng
  site, `utils/sql_translate.py` dịch runtime: `?`→`%s`, `INSERT OR IGNORE`→`ON
  CONFLICT DO NOTHING`, `BEGIN IMMEDIATE`→`BEGIN`, `datetime('now')`→`sqlite_datetime_now()`,
  escape `%`. `json_extract/json_set/json` KHÔNG dịch — làm SQL function phía PG. 9
  unit-test (`tests/test_sql_translate.py`).
- ✅ **Phase C — schema PG** (`migrations/pg/0001_init.sql`): 14 bảng, cột `json`=TEXT
  (byte-identical), emulation functions, generated columns native jsonb, expression
  index. Cột lẫn kiểu (`orders.updated_at/deleted_at`, `customers.updated_at`) → TEXT
  để bảo toàn 100%. `docker-compose.yml` (portable).
- ✅ **Phase D — migrate + verify** (`tools/migrate_sqlite_to_pg.py`): copy blob nguyên
  bytes, verify count + **json byte-identity** + full-row str-norm. **Chạy thật trên
  data thật (17014 đơn / 18220 task / 344 khách): RESULT ✅ KHỚP TUYỆT ĐỐI.**
- ✅ **Phase E — engine switch** (`utils/db.py` `DB_ENGINE`/`DATABASE_URL` +
  `utils/pg.py` `PgConnection`): bề mặt giống sqlite3 (execute/transaction/Row lai
  index+tên). **Chạy thật qua PG:** `get_order_by_thread_id`, `search_products`, ghi
  RMW `set_task_status`+`json_set`, generated columns, `orders_fts` (bảng thường+LIKE),
  `PRAGMA table_info`→information_schema, store `migrate_*` no-op an toàn. Site
  type-sensitive `orders_api` (`= 1` bool) đã nhánh theo engine.
- 🚧 **Phase F — cutover (runbook, cần PG prod + freeze):**
  1. Provision PG prod (local unix-socket, xem QUYẾT ĐỊNH CHỐT), chạy `0001_init.sql`.
  2. `pip install -r requirements.txt` (đã thêm `psycopg[binary]`).
  3. Freeze process; `migrate_sqlite_to_pg.py` lần cuối (delta); verify ✅.
  4. Đặt `DB_ENGINE=postgres` + `DATABASE_URL`, khởi động `server.py`. Giữ file SQLite
     read-only làm rollback (đổi env về `sqlite`).
  5. Soak: ✅ **write-path tiền đã test trên PG (bản copy):** `save_order_invoice`,
     `set_order_flag`, `_save_order`, `add_payment`/`get_payments`/`calculate_debt`
     (core lệnh thanh toán), `set_task_status` — tất cả OK, json parse lại đúng,
     `updated_at` int→text lưu sạch, re-migrate xác nhận identity. Còn lại thuần
     thao tác: chạy trên app.db PROD thật + theo dõi live.
- ✅ **Gom nốt bot_core + audit (hết split-brain).** `bot_core/db.py` (`_conn` qua
  cổng, `_migrate` no-op trên PG), `bot_core/db_queries.py` (3 predicate `done`
  type-sensitive → nhánh engine `IN ('true','1')`), `audit/db.py` + `audit/events.py`
  (qua cổng, init DDL no-op trên PG). Fix `bump_rev` bare self-ref → qualify
  `kv_revisions.rev` (chạy cả 2 engine). `utils/pg.py` thêm `lastrowid` (qua
  `lastval()`) + `executescript`. **Chạy thật trên PG:** order_store RMW, bot_core
  money queries, kv upsert, audit insert (lastrowid=460) — OK.
- ✅ **Xác nhận 0 self-connect app.db ngoài `utils/db.py`.** `donhang.db`/
  `bot_sessions.db` là DB RIÊNG (giữ SQLite đúng thiết kế) → không split-brain.
  **Code sẵn sàng bật PG toàn hệ** (chỉ còn Phase F: provision + migrate + flip env
  + soak write-path invoice/payment).
- ✅ **Fix ordering `updated_at` (tự kiểm phát hiện).** Ban đầu để `updated_at` text
  → PG sort chữ ≠ SQLite sort số → `orders_api` sort "updated" + `product_commands_
  profit` (top-50 mới nhất) lệch. Sửa: `updated_at` → `bigint`, migrate convert 6868/15
  chuỗi ISO → epoch ms **cùng thời điểm** (json blob vẫn byte-identical; verify
  full-row "coerced" chứng minh CHỈ updated_at đổi). Ordering giờ đúng số, monotonic.
  `deleted_at` giữ text (chỉ dùng IS NULL).
  - Hệ quả (tự kiểm phát hiện): cột `updated_at` bigint đòi **mọi writer ghi int ms**.
    5 site trước ghi chuỗi ISO vào cột (chính là nguồn 6868 giá trị lẫn) đã sửa →
    `int(epoch*1000)`: `api_helpers/payment_core._save`, `order_store/customers`
    (add/update), `order_store/task_admin` (delete_all/migrate_v2). Blob
    `data['updated_at']` giữ ISO (không đụng byte). SQLite 94/94 vẫn xanh.
- ✅ **Fix COLLATE NOCASE (tự kiểm phát hiện).** `order_commands_v2_html` sort danh
  sách khách `COLLATE NOCASE` — PG không có → crash. Tạo `CREATE COLLATION nocase`
  (ICU level2, case-insensitive) trong `0001_init.sql`; PG fold `NOCASE`→`nocase` nên
  SQL app KHÔNG đổi, chạy cả 2 engine. (Tie-break dấu tiếng Việt có thể khác chút —
  chỉ danh sách hiển thị, không tiền.)
- 🚧 **Bước 2 — chuẩn hóa (Phase G) ĐÃ KHỞI ĐỘNG.** Chiến lược chốt với chủ dự án:
  **view read-only trước** (0 rủi ro write-path trên hệ tiền live), tiền **round về
  đồng (int)**. Đã làm:
  - Phân loại 138 key orders (43 promote-scalar, 8 tiền, 6 mảng→child, 13 object→FK,
    12 coerce, 4 version, 52 drop-candidate gồm key `0` 38%).
  - `migrations/pg/0002_order_items_view.sql` — `order_items_v` unnest invoice[] →
    báo cáo doanh thu theo SP (blob chặn hoàn toàn thứ này).
  - `migrations/pg/0003_report_views.sql` — `payments_v` (thanh toán, tiền round đồng),
    `customers_v` (khách+nợ). Báo cáo thật: tổng nợ 1.33 tỷ, TT Transfer 11 tỷ/Cash 9.2 tỷ.
  - Phát hiện data-quality: khách trùng bản ghi (vd "Bạch (khuyến mãi)" ×2) — hệ quả
    denormalization, xử ở bước promote khach_hang→FK.
  - **Còn lại:** promote scalar sạch → cột thật (sau façade), invoice/payments →
    bảng THẬT ghi được (đụng write-path), coerce 4 key tiền float→đồng, quyết 52 key drop.
