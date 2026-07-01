-- Bước 2 (chuẩn hóa) — bước đầu AN TOÀN: view unnest invoice[] blob -> dòng SQL.
-- Read-only, luôn tươi (dẫn xuất từ orders.json), KHÔNG đụng write-path → 0 rủi ro.
-- Mở khóa báo cáo mà blob chặn: doanh thu theo SP, số lượng bán, v.v.
-- Đây là bước đệm; đích cuối là bảng order_items THẬT (ghi được, bỏ blob) — làm dần.
CREATE OR REPLACE VIEW order_items_v AS
SELECT o.thread_id,
       o.firebase_key,
       (elem->>'sp')                                                        AS sp,
       CASE WHEN elem->>'sl'    ~ '^-?[0-9]+(\.[0-9]+)?$' THEN (elem->>'sl')::numeric    END AS sl,
       CASE WHEN elem->>'price' ~ '^-?[0-9]+(\.[0-9]+)?$' THEN (elem->>'price')::numeric END AS price,
       elem->>'qc_type'                                                     AS qc_type,
       CASE WHEN elem->>'so_qc' ~ '^-?[0-9]+(\.[0-9]+)?$' THEN (elem->>'so_qc')::numeric END AS so_qc,
       elem->>'note'                                                        AS note
FROM orders o,
     LATERAL jsonb_array_elements(o.json::jsonb->'invoice') elem
WHERE o.deleted_at IS NULL
  AND jsonb_typeof(o.json::jsonb->'invoice') = 'array'
  AND jsonb_typeof(elem) = 'object';
