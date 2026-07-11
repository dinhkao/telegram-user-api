from __future__ import annotations


def create_production_table(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS production_slips (
            thread_id   INTEGER PRIMARY KEY,
            channel_id  INTEGER,
            message_id  INTEGER,
            date        TEXT,
            date_code   TEXT,
            sp_name     TEXT,
            sp_mam      REAL,
            sp_luong    REAL,
            sx_target   INTEGER,
            total       REAL DEFAULT 0,
            numbers     TEXT,
            bang        TEXT,
            ghi_chu     TEXT,
            kind        TEXT DEFAULT 'san_xuat',
            updated_at  TEXT DEFAULT (datetime('now'))
        )
        """
    )
    conn.commit()


def migrate_production_table(conn):
    columns = {row[1] for row in conn.execute("PRAGMA table_info(production_slips)").fetchall()}
    if "channel_id" not in columns:
        conn.execute("ALTER TABLE production_slips ADD COLUMN channel_id INTEGER")
    if "message_id" not in columns:
        conn.execute("ALTER TABLE production_slips ADD COLUMN message_id INTEGER")
    if "date" not in columns:
        conn.execute("ALTER TABLE production_slips ADD COLUMN date TEXT")
    if "date_code" not in columns:
        conn.execute("ALTER TABLE production_slips ADD COLUMN date_code TEXT")
    if "sp_name" not in columns:
        conn.execute("ALTER TABLE production_slips ADD COLUMN sp_name TEXT")
    if "sp_mam" not in columns:
        conn.execute("ALTER TABLE production_slips ADD COLUMN sp_mam REAL")
    if "sp_luong" not in columns:
        conn.execute("ALTER TABLE production_slips ADD COLUMN sp_luong REAL")
    if "sx_target" not in columns:
        conn.execute("ALTER TABLE production_slips ADD COLUMN sx_target INTEGER")
    if "total" not in columns:
        conn.execute("ALTER TABLE production_slips ADD COLUMN total REAL DEFAULT 0")
    if "numbers" not in columns:
        conn.execute("ALTER TABLE production_slips ADD COLUMN numbers TEXT")
    if "bang" not in columns:
        conn.execute("ALTER TABLE production_slips ADD COLUMN bang TEXT")
    if "ghi_chu" not in columns:
        conn.execute("ALTER TABLE production_slips ADD COLUMN ghi_chu TEXT")
    if "kind" not in columns:
        conn.execute("ALTER TABLE production_slips ADD COLUMN kind TEXT DEFAULT 'san_xuat'")
    if "updated_at" not in columns:
        conn.execute("ALTER TABLE production_slips ADD COLUMN updated_at TEXT DEFAULT (datetime('now'))")
    if "product_id" not in columns:  # → products.id (danh tính SP bất biến; sp_name = snapshot mã)
        conn.execute("ALTER TABLE production_slips ADD COLUMN product_id INTEGER")
    if "lock_override" not in columns:  # admin ghi đè khoá: NULL=auto(24h) | 'locked' | 'unlocked'
        conn.execute("ALTER TABLE production_slips ADD COLUMN lock_override TEXT")
    if "luong_1sp" not in columns:  # đơn giá lương /1SP CHỐT THEO PHIẾU (NULL = chưa chốt → bảng lương hiện tại)
        conn.execute("ALTER TABLE production_slips ADD COLUMN luong_1sp REAL")
    # Backfill product_id theo sp_name (idempotent — chỉ row còn NULL; tên không phải mã giữ NULL)
    conn.execute(
        "UPDATE production_slips SET product_id = "
        "(SELECT p.id FROM products p WHERE p.code = UPPER(TRIM(COALESCE(production_slips.sp_name,'')))) "
        "WHERE product_id IS NULL"
    )
    # Backfill luong_1sp: chốt đơn giá bảng lương HIỆN TẠI cho phiếu chưa chốt
    # (idempotent — chỉ row NULL; từ đây đổi bảng lương KHÔNG ảnh hưởng phiếu đã chốt)
    try:
        from production_store.wages import ensure_table as _ensure_wages
        _ensure_wages(conn)
        conn.execute(
            "UPDATE production_slips SET luong_1sp = "
            "(SELECT w.luong FROM production_wages w JOIN products p ON UPPER(p.code) = w.code "
            " WHERE p.id = production_slips.product_id) "
            "WHERE luong_1sp IS NULL AND product_id IS NOT NULL"
        )
        # phiếu KHÔNG có product_id (sp_name là mã tự do, vd K2NT128 chưa có trong
        # danh mục SP) → khớp thẳng sp_name với bảng lương
        conn.execute(
            "UPDATE production_slips SET luong_1sp = "
            "(SELECT w.luong FROM production_wages w "
            " WHERE w.code = UPPER(TRIM(COALESCE(production_slips.sp_name, '')))) "
            "WHERE luong_1sp IS NULL AND TRIM(COALESCE(sp_name, '')) != ''"
        )
    except Exception:  # noqa: BLE001 — DB test thiếu bảng products
        pass
    conn.commit()
