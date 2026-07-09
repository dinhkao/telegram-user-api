"""Schema product_recipes — 1 dòng = 1 nguyên liệu của 1 sản phẩm (theo tỉ lệ).

product_code cần ingredient_code với ratio (số cây nguyên liệu / 1 cây thành phẩm).
UNIQUE(product_code, ingredient_code) — mỗi cặp 1 dòng.
"""
from __future__ import annotations


def create_recipe_table(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS product_recipes (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
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
    # migrate DB cũ: BỎ cột optional (bắt buộc/không bắt buộc) — nhu cầu NL giờ do
    # LOẠI PHIẾU quyết định: sản xuất = không cần NL, đóng gói = cần đủ MỌI NL.
    cols = {r[1] for r in conn.execute("PRAGMA table_info(product_recipes)").fetchall()}
    if "optional" in cols:
        conn.execute("ALTER TABLE product_recipes DROP COLUMN optional")
    conn.commit()
