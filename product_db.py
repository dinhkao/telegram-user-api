"""product_db.py — Manage product codes and cost prices.

Provides functions to:
- Create/migrate products table
- CRUD operations for products
- Calculate profit for orders
"""
from __future__ import annotations
import json
import logging
import time
from typing import Optional

log = logging.getLogger("product_db")

# ── Table creation ─────────────────────────────────────────────────

def create_products_table(conn):
    """Create products table if not exists."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS products (
            code        TEXT PRIMARY KEY,
            name        TEXT,
            cost_price  INTEGER DEFAULT 0,
            note        TEXT,
            created_at  TEXT DEFAULT (datetime('now')),
            updated_at  TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()


def migrate_products_table(conn):
    """Add missing columns if needed."""
    cur = conn.execute("PRAGMA table_info(products)")
    columns = {row[1] for row in cur.fetchall()}
    
    if "name" not in columns:
        conn.execute("ALTER TABLE products ADD COLUMN name TEXT")
    if "cost_price" not in columns:
        conn.execute("ALTER TABLE products ADD COLUMN cost_price INTEGER DEFAULT 0")
    if "note" not in columns:
        conn.execute("ALTER TABLE products ADD COLUMN note TEXT")
    if "created_at" not in columns:
        conn.execute("ALTER TABLE products ADD COLUMN created_at TEXT DEFAULT (datetime('now'))")
    if "updated_at" not in columns:
        conn.execute("ALTER TABLE products ADD COLUMN updated_at TEXT DEFAULT (datetime('now'))")
    
    conn.commit()


# ── CRUD Operations ────────────────────────────────────────────────

def get_product(conn, code: str) -> Optional[dict]:
    """Get product by code."""
    cur = conn.execute(
        "SELECT code, name, cost_price, note, created_at, updated_at FROM products WHERE code = ?",
        (code.upper().strip(),)
    )
    row = cur.fetchone()
    if not row:
        return None
    return {
        "code": row[0],
        "name": row[1],
        "cost_price": row[2] or 0,
        "note": row[3],
        "created_at": row[4],
        "updated_at": row[5],
    }


def get_all_products(conn) -> list[dict]:
    """Get all products ordered by code."""
    cur = conn.execute(
        "SELECT code, name, cost_price, note, created_at, updated_at FROM products ORDER BY code"
    )
    return [
        {
            "code": row[0],
            "name": row[1],
            "cost_price": row[2] or 0,
            "note": row[3],
            "created_at": row[4],
            "updated_at": row[5],
        }
        for row in cur.fetchall()
    ]


def upsert_product(conn, code: str, name: str = None, cost_price: int = None, note: str = None) -> bool:
    """Insert or update product. Returns True on success."""
    code = code.upper().strip()
    if not code:
        return False
    
    existing = get_product(conn, code)
    now = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
    
    if existing:
        # Update
        updates = []
        params = []
        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if cost_price is not None:
            updates.append("cost_price = ?")
            params.append(cost_price)
        if note is not None:
            updates.append("note = ?")
            params.append(note)
        
        if not updates:
            return True  # Nothing to update
        
        updates.append("updated_at = ?")
        params.append(now)
        params.append(code)
        
        conn.execute(
            f"UPDATE products SET {', '.join(updates)} WHERE code = ?",
            params
        )
    else:
        # Insert
        conn.execute(
            "INSERT INTO products (code, name, cost_price, note, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (code, name or "", cost_price or 0, note or "", now, now)
        )
    
    conn.commit()
    return True


def delete_product(conn, code: str) -> bool:
    """Delete product by code. Returns True on success."""
    code = code.upper().strip()
    conn.execute("DELETE FROM products WHERE code = ?", (code,))
    conn.commit()
    return True


def bulk_update_cost_prices(conn, updates: list[dict]) -> int:
    """Bulk update cost prices. updates = [{"code": "SP001", "cost_price": 10000}, ...]
    Returns count of updated products."""
    count = 0
    for item in updates:
        code = item.get("code", "").upper().strip()
        cost_price = item.get("cost_price")
        if code and cost_price is not None:
            if upsert_product(conn, code, cost_price=cost_price):
                count += 1
    return count


# ── Profit Calculation ─────────────────────────────────────────────

def calculate_order_profit(conn, order: dict) -> dict:
    """Calculate profit for an order.
    
    Uses frozen cost price from invoice item if available (saved at order time).
    Falls back to current cost price from products table if frozen price not set.
    
    VAT and additional fees (pvc/shipping) are added to revenue.
    Discount is subtracted from revenue.
    
    Returns dict with:
    - items: list of item profits
    - total_revenue: total selling price + vat + pvc - discount
    - total_cost: total cost price
    - total_profit: profit = revenue - cost
    - fees: {vat, pvc, discount}
    """
    invoice = order.get("invoice") or order.get("invoice_items") or []
    vat = int(order.get("vat", 0))
    pvc = int(order.get("pvc", 0))
    discount = int(order.get("discount", 0))
    fee_total = vat + pvc - discount
    
    items_profit = []
    total_revenue = 0
    total_cost = 0
    
    for item in invoice:
        code = (item.get("sp") or "").upper().strip()
        if not code:
            continue
        
        qty = int(item.get("sl", 0))
        sell_price = int(item.get("price", 0))
        revenue = qty * sell_price
        
        # Use frozen cost_price from invoice item if available
        # Otherwise fall back to current cost price from products table
        frozen_cost = item.get("cost_price")
        if frozen_cost is not None:
            cost_price = int(frozen_cost)
            is_frozen = True
        else:
            product = get_product(conn, code)
            cost_price = product.get("cost_price", 0) if product else 0
            is_frozen = False
        
        cost = qty * cost_price
        # If cost is 0 (no cost price), profit is 0 (not revenue)
        profit = (revenue - cost) if cost_price > 0 else 0
        
        items_profit.append({
            "code": code,
            "qty": qty,
            "sell_price": sell_price,
            "cost_price": cost_price,
            "revenue": revenue,
            "cost": cost,
            "profit": profit,
            "has_cost": cost_price > 0,
            "is_frozen": is_frozen,
        })
        
        total_revenue += revenue
        if cost_price > 0:
            total_cost += cost
    
    # Calculate total profit only from items with cost, plus fees
    items_profit_total = sum(i["profit"] for i in items_profit)
    total_revenue += fee_total
    total_profit = items_profit_total + fee_total if total_cost > 0 else 0
    
    return {
        "items": items_profit,
        "total_revenue": total_revenue,
        "total_cost": total_cost,
        "total_profit": total_profit,
        "item_count": len(items_profit),
        "items_with_cost": sum(1 for i in items_profit if i["has_cost"]),
        "fees": {"vat": vat, "pvc": pvc, "discount": discount, "fee_total": fee_total},
    }


def freeze_invoice_cost_prices(conn, invoice: list) -> list:
    """Freeze current cost prices into invoice items.
    
    Call this when saving invoice items to lock in the cost price at order time.
    Returns the updated invoice list with cost_price added to each item.
    """
    updated_invoice = []
    for item in invoice:
        # Don't overwrite if already frozen
        if "cost_price" not in item:
            code = (item.get("sp") or "").upper().strip()
            if code:
                product = get_product(conn, code)
                if product and product.get("cost_price", 0) > 0:
                    item = {**item, "cost_price": product["cost_price"]}
        updated_invoice.append(item)
    return updated_invoice


def get_products_from_orders(conn, limit: int = 200) -> list[str]:
    """Extract unique product codes from recent orders."""
    cur = conn.execute(
        "SELECT json FROM orders WHERE deleted_at IS NULL AND json IS NOT NULL "
        "ORDER BY updated_at DESC LIMIT ?",
        (limit,)
    )
    
    codes = set()
    for row in cur.fetchall():
        order = json.loads(row[0])
        invoice = order.get("invoice") or order.get("invoice_items") or []
        for item in invoice:
            code = (item.get("sp") or "").upper().strip()
            if code:
                codes.add(code)
    
    return sorted(codes)
