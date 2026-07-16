"""Schema product_recipes — 1 dòng = 1 nguyên liệu của 1 sản phẩm (theo tỉ lệ).

Danh tính = product_id / ingredient_id (products.id bất biến); product_code /
ingredient_code là SNAPSHOT mã hiện hành (hiển thị nhanh + fallback khi SP xoá).
UNIQUE(product_code, ingredient_code) — mỗi cặp 1 dòng.
"""
from __future__ import annotations


def create_recipe_table(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS product_recipes (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id      INTEGER,
            ingredient_id   INTEGER,
            product_code    TEXT NOT NULL,
            ingredient_code TEXT NOT NULL,
            ratio           REAL NOT NULL DEFAULT 0,
            created_at      TEXT DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_recipe_pair ON product_recipes(product_code, ingredient_code)"
    )
    cols = {r[1] for r in conn.execute("PRAGMA table_info(product_recipes)").fetchall()}
    # migrate DB cũ: BỎ cột optional (bắt buộc/không bắt buộc) — nhu cầu NL giờ do
    # LOẠI PHIẾU quyết định: sản xuất = không cần NL, đóng gói = cần đủ MỌI NL.
    if "optional" in cols:
        conn.execute("ALTER TABLE product_recipes DROP COLUMN optional")
    # migrate DB cũ: thêm cột id danh tính + backfill theo mã (idempotent)
    if "product_id" not in cols:
        conn.execute("ALTER TABLE product_recipes ADD COLUMN product_id INTEGER")
    if "ingredient_id" not in cols:
        conn.execute("ALTER TABLE product_recipes ADD COLUMN ingredient_id INTEGER")
    # NGUYÊN LIỆU PHỤ (2026-07-16): aux=1 = NL phụ — trừ kho ở CẢ phiếu sản xuất
    # LẪN đóng gói khi products.aux_required bật (NL chính aux=0: chỉ đóng gói).
    # 1 cặp (SP, NL) là chính HOẶC phụ (UNIQUE pair giữ nguyên).
    if "aux" not in cols:
        conn.execute("ALTER TABLE product_recipes ADD COLUMN aux INTEGER NOT NULL DEFAULT 0")
    conn.execute(
        "UPDATE product_recipes SET product_id = "
        "(SELECT p.id FROM products p WHERE p.code = product_recipes.product_code) "
        "WHERE product_id IS NULL"
    )
    conn.execute(
        "UPDATE product_recipes SET ingredient_id = "
        "(SELECT p.id FROM products p WHERE p.code = product_recipes.ingredient_code) "
        "WHERE ingredient_id IS NULL"
    )
    conn.commit()
