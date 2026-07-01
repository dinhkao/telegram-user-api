-- Bước 2 — view báo cáo read-only (0 rủi ro write-path). Tiền round về đồng (int).
-- payments_v (thanh toán), customers_v (khách+nợ). Xem docs/postgres-migration.md.

-- payments_v: unnest payments[] blob -> dòng thanh toán (tiền round về đồng)
CREATE OR REPLACE VIEW payments_v AS
SELECT o.thread_id, o.firebase_key,
       CASE WHEN p->>'amount' ~ '^-?[0-9]+(\.[0-9]+)?$' THEN round((p->>'amount')::numeric)::bigint END AS amount,
       p->>'method' AS method, p->>'note' AS note,
       p->>'created_at' AS created_at, p->>'id' AS id
FROM orders o, LATERAL jsonb_array_elements(o.json::jsonb->'payments') p
WHERE o.deleted_at IS NULL AND jsonb_typeof(o.json::jsonb->'payments')='array' AND jsonb_typeof(p)='object';

-- customers_v: flatten customer blob (nợ round về đồng)
CREATE OR REPLACE VIEW customers_v AS
SELECT firebase_key,
       json::jsonb->>'name' AS name,
       CASE WHEN json::jsonb->>'kh_id' ~ '^-?[0-9]+$' THEN (json::jsonb->>'kh_id')::bigint END AS kh_id,
       CASE WHEN json::jsonb->>'debt' ~ '^-?[0-9]+(\.[0-9]+)?$' THEN round((json::jsonb->>'debt')::numeric)::bigint END AS debt,
       CASE WHEN json::jsonb->>'price_list' ~ '^-?[0-9]+$' THEN (json::jsonb->>'price_list')::int END AS price_list,
       CASE WHEN json::jsonb->>'thread_id' ~ '^-?[0-9]+$' THEN (json::jsonb->>'thread_id')::bigint END AS thread_id
FROM customers WHERE deleted_at IS NULL;
