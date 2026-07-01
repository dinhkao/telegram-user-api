-- PostgreSQL schema for app.db (Bước 1: lift-and-shift, blob giữ TEXT byte-identical).
-- Sinh từ schema SQLite thật (xem docs/postgres-migration.md §Phase C).
--
-- Nguyên tắc:
--   * cột `json` = TEXT (KHÔNG jsonb) → giữ nguyên bytes blob (req "data y hệt").
--     Query/index cast tại chỗ `json::jsonb`.
--   * emulation functions json_extract/json_set/json → 80+ site SQL không phải sửa.
--   * generated columns & index type-sensitive viết native jsonb (không qua emulation).
--   * bỏ orders_fts (dựng lại lúc boot thành bảng thường — xem server_app/orders_db.py).
--   * bỏ sqlite_sequence / sqlite_stat1 (nội bộ SQLite).

-- ---------------------------------------------------------------------------
-- Collation `nocase` — mô phỏng SQLite COLLATE NOCASE (không phân biệt hoa/thường).
-- PG fold `COLLATE NOCASE` (không quote) -> "nocase" nên SQL app không phải đổi.
-- ICU level2 = case-insensitive, accent-sensitive (gần SQLite NOCASE; thứ tự tie-break
-- dấu tiếng Việt có thể khác chút — chỉ ảnh hưởng danh sách khách hiển thị, không tiền).
-- ---------------------------------------------------------------------------
CREATE COLLATION IF NOT EXISTS nocase (provider = icu, locale = 'und-u-ks-level2', deterministic = false);

-- ---------------------------------------------------------------------------
-- Emulation SQLite JSON functions (semantics khớp cho các site đang dùng)
-- ---------------------------------------------------------------------------

-- '$.a.b'  ->  text path array {a,b}. '$' -> {}. Trả TEXT như SQLite #>> (unquoted).
CREATE OR REPLACE FUNCTION _sqlite_json_path(path text)
RETURNS text[] AS $$
  SELECT CASE
    WHEN path IN ('$', '') THEN '{}'::text[]
    ELSE string_to_array(regexp_replace(path, '^\$\.?', ''), '.')
  END
$$ LANGUAGE sql IMMUTABLE;

-- json_extract(json, '$.a.b') -> giá trị dạng TEXT (scalar unquoted), như SQLite.
CREATE OR REPLACE FUNCTION json_extract(j text, path text)
RETURNS text AS $$
  SELECT (j::jsonb) #>> _sqlite_json_path(path)
$$ LANGUAGE sql IMMUTABLE;

-- json(x) -> validate + normalize; ở đây trả về jsonb text. Dùng trong json_set(...json(?)).
CREATE OR REPLACE FUNCTION json(x text)
RETURNS jsonb AS $$
  SELECT x::jsonb
$$ LANGUAGE sql IMMUTABLE;

-- json_set(json, '$.a.b', value_jsonb) -> đặt path, trả TEXT (giữ cột kiểu text).
-- Khớp site duy nhất: UPDATE orders SET json = json_set(json, ?, json(?)).
CREATE OR REPLACE FUNCTION json_set(j text, path text, val jsonb)
RETURNS text AS $$
  SELECT jsonb_set(j::jsonb, _sqlite_json_path(path), val, true)::text
$$ LANGUAGE sql IMMUTABLE;

-- datetime('now') / strftime của SQLite (UTC, không timezone suffix).
CREATE OR REPLACE FUNCTION sqlite_datetime_now()
RETURNS text AS $$
  SELECT to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')
$$ LANGUAGE sql VOLATILE;

CREATE OR REPLACE FUNCTION sqlite_strftime_iso_now()
RETURNS text AS $$
  SELECT to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')
$$ LANGUAGE sql VOLATILE;

-- ---------------------------------------------------------------------------
-- Tables (giữ nguyên cấu trúc; kiểu ánh xạ: INTEGER->bigint, TEXT->text, REAL->double)
-- ---------------------------------------------------------------------------

CREATE TABLE kv_store (
    path       text PRIMARY KEY,
    value      text NOT NULL,
    updated_at bigint NOT NULL
);
CREATE INDEX idx_kv_updated ON kv_store(updated_at);

CREATE TABLE orders (
    firebase_key  text PRIMARY KEY,
    thread_id     bigint UNIQUE,
    channel_id    bigint,
    message_id    bigint,
    json          text NOT NULL,
    -- epoch mili. SQLite lẫn int(10146) + chuỗi ISO legacy(6868); migrate convert ISO
    -- -> epoch ms (cùng thời điểm) để ordering đúng số. deleted_at chỉ dùng IS NULL nên
    -- giữ text (bảo toàn 22 giá trị str legacy nguyên vẹn).
    updated_at    bigint NOT NULL,
    deleted_at    text,
    -- generated: native jsonb (không qua emulation) để đúng type-sensitive '=1'.
    -- SQLite json_extract(done)=1 khớp cả JSON true lẫn 1 -> so text 'true'/'1'.
    nop_nhan_done integer GENERATED ALWAYS AS (
        CASE WHEN (json::jsonb #>> '{task_status,nop_tien,done}') IN ('true','1')
              AND (json::jsonb #>> '{task_status,nhan_tien,done}') IN ('true','1')
        THEN 1 ELSE 0 END
    ) STORED,
    order_created text GENERATED ALWAYS AS ((json::jsonb #>> '{created}')) STORED
);
CREATE INDEX idx_orders_thread   ON orders(thread_id);
CREATE INDEX idx_orders_message  ON orders(message_id);
CREATE INDEX idx_orders_updated  ON orders(updated_at);
CREATE INDEX idx_orders_created  ON orders(order_created);
CREATE INDEX idx_orders_nop_nhan ON orders(nop_nhan_done, order_created) WHERE deleted_at IS NULL;

CREATE TABLE order_key_by_thread (
    thread_id    bigint PRIMARY KEY,
    firebase_key text NOT NULL
);
CREATE TABLE order_key_by_message (
    message_id   bigint PRIMARY KEY,
    firebase_key text NOT NULL
);
CREATE TABLE order_discussion_mirror (
    channel_message_id bigint PRIMARY KEY,
    json               text NOT NULL,
    updated_at         bigint NOT NULL
);
CREATE TABLE kv_revisions (
    path text PRIMARY KEY,
    rev  bigint NOT NULL DEFAULT 0
);

CREATE TABLE customers (
    firebase_key text PRIMARY KEY,
    json         text NOT NULL,
    updated_at   bigint NOT NULL,  -- convert ISO(15)->epoch ms lúc migrate, xem orders
    deleted_at   bigint
);
CREATE INDEX idx_customers_updated ON customers(updated_at);

CREATE TABLE tasks (
    firebase_key text PRIMARY KEY,
    json         text NOT NULL,
    updated_at   bigint NOT NULL,
    deleted_at   bigint
);
CREATE INDEX idx_tasks_updated  ON tasks(updated_at);
CREATE INDEX idx_tasks_dhthread ON tasks(((json::jsonb #>> '{dhThreadID}')));

CREATE TABLE products (
    code       text PRIMARY KEY,
    name       text,
    cost_price bigint DEFAULT 0,
    note       text,
    created_at text DEFAULT sqlite_datetime_now(),
    updated_at text DEFAULT sqlite_datetime_now()
);

CREATE TABLE order_chat_messages (
    id          bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    thread_id   bigint NOT NULL,
    message_id  bigint NOT NULL UNIQUE,
    sender_id   bigint,
    sender_name text,
    text        text,
    media_type  text,
    created_at  text DEFAULT sqlite_datetime_now(),
    event_type  text DEFAULT 'new',
    raw_json    text,
    edited_at   text,
    deleted_at  text
);
CREATE INDEX idx_chat_thread ON order_chat_messages(thread_id);

CREATE TABLE audit_events (
    id           bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    ts           text NOT NULL DEFAULT sqlite_strftime_iso_now(),
    request_id   text,
    actor_type   text,
    actor_id     text,
    action       text NOT NULL,
    direction    text,
    source       text,
    chat_id      bigint,
    thread_id    bigint,
    message_id   bigint,
    payload_json text,
    result_json  text,
    error        text,
    duration_ms  bigint
);
CREATE INDEX idx_audit_events_ts         ON audit_events(ts);
CREATE INDEX idx_audit_events_request_id ON audit_events(request_id);
CREATE INDEX idx_audit_events_action     ON audit_events(action);
CREATE INDEX idx_audit_events_thread_id  ON audit_events(thread_id);

CREATE TABLE production_slips (
    thread_id  bigint PRIMARY KEY,
    channel_id bigint,
    message_id bigint,
    date       text,
    date_code  text,
    sp_name    text,
    sp_mam     double precision,
    sp_luong   double precision,
    sx_target  bigint,
    total      double precision DEFAULT 0,
    numbers    text,
    bang       text,
    updated_at text DEFAULT sqlite_datetime_now()
);

CREATE TABLE bang_gia_slips (
    thread_id  bigint PRIMARY KEY,
    name       text,
    price_list text,
    updated_at text DEFAULT sqlite_datetime_now()
);

CREATE TABLE notes (
    thread_id  bigint PRIMARY KEY,
    text       text,
    tags       text,
    check_flag bigint DEFAULT 0,
    del_flag   bigint DEFAULT 0,
    channel_id bigint,
    message_id bigint,
    updated_at text DEFAULT sqlite_datetime_now()
);
