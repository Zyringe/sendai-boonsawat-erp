from database import get_connection
from datetime import date


# ── Unit conversion ──────────────────────────────────────────────────────────

def to_base_units(quantity: int, mode: str, product) -> int:
    if mode == 'carton':
        return quantity * (product['units_per_carton'] or 1)
    if mode == 'box':
        return quantity * (product['units_per_box'] or 1)
    return quantity


# ── Products ─────────────────────────────────────────────────────────────────

def get_products(search=None, low_stock=False, hard_to_sell=False, page=1, per_page=50):
    conn = get_connection()
    conditions = ["p.is_active = 1"]
    params = []
    if search:
        conditions.append("(p.product_name LIKE ? OR CAST(p.sku AS TEXT) LIKE ?)")
        params += [f"%{search}%", f"%{search}%"]
    if hard_to_sell:
        conditions.append("p.hard_to_sell = 1")

    where = " AND ".join(conditions)
    having = "HAVING s.quantity <= p.low_stock_threshold" if low_stock else ""

    sql = f"""
        SELECT p.*, COALESCE(s.quantity, 0) AS quantity,
               CASE WHEN COALESCE(s.quantity, 0) <= p.low_stock_threshold THEN 1 ELSE 0 END AS is_low
        FROM products p
        LEFT JOIN stock_levels s ON s.product_id = p.id
        WHERE {where}
        GROUP BY p.id
        {having}
        ORDER BY p.sku
        LIMIT ? OFFSET ?
    """
    params += [per_page, (page - 1) * per_page]
    rows = conn.execute(sql, params).fetchall()

    count_sql = f"""
        SELECT COUNT(*) FROM products p
        LEFT JOIN stock_levels s ON s.product_id = p.id
        WHERE {where}
        {having.replace('HAVING','AND') if having else ''}
    """
    total = conn.execute(count_sql, params[:-2]).fetchone()[0]
    conn.close()
    return rows, total


def get_product(product_id):
    conn = get_connection()
    row = conn.execute("""
        SELECT p.*, COALESCE(s.quantity, 0) AS quantity,
               CASE WHEN COALESCE(s.quantity, 0) <= p.low_stock_threshold THEN 1 ELSE 0 END AS is_low
        FROM products p
        LEFT JOIN stock_levels s ON s.product_id = p.id
        WHERE p.id = ?
    """, (product_id,)).fetchone()
    conn.close()
    return row


def get_product_by_sku(sku):
    conn = get_connection()
    row = conn.execute("SELECT * FROM products WHERE sku = ?", (sku,)).fetchone()
    conn.close()
    return row


def create_product(data: dict) -> int:
    conn = get_connection()
    cur = conn.execute("""
        INSERT INTO products (sku, product_name, units_per_carton, units_per_box,
            unit_type, hard_to_sell, cost_price, base_sell_price, low_stock_threshold,
            shopee_stock, lazada_stock)
        VALUES (:sku, :product_name, :units_per_carton, :units_per_box,
            :unit_type, :hard_to_sell, :cost_price, :base_sell_price, :low_stock_threshold,
            :shopee_stock, :lazada_stock)
    """, data)
    # ensure stock_levels row exists
    conn.execute("INSERT OR IGNORE INTO stock_levels (product_id, quantity) VALUES (?, 0)", (cur.lastrowid,))
    conn.commit()
    pid = cur.lastrowid
    conn.close()
    return pid


def update_product(product_id: int, data: dict):
    conn = get_connection()
    conn.execute("""
        UPDATE products SET
            sku=:sku, product_name=:product_name,
            units_per_carton=:units_per_carton, units_per_box=:units_per_box,
            unit_type=:unit_type, hard_to_sell=:hard_to_sell,
            cost_price=:cost_price, base_sell_price=:base_sell_price,
            low_stock_threshold=:low_stock_threshold,
            shopee_stock=:shopee_stock, lazada_stock=:lazada_stock
        WHERE id=:id
    """, {**data, 'id': product_id})
    conn.commit()
    conn.close()


def deactivate_product(product_id: int):
    conn = get_connection()
    conn.execute("UPDATE products SET is_active = 0 WHERE id = ?", (product_id,))
    conn.commit()
    conn.close()


# ── Alerts ───────────────────────────────────────────────────────────────────

def get_stock_alerts():
    """Return products where shopee_stock + lazada_stock > warehouse quantity."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT p.id, p.sku, p.product_name, p.unit_type,
               COALESCE(s.quantity, 0)   AS quantity,
               p.shopee_stock,
               p.lazada_stock,
               (p.shopee_stock + p.lazada_stock) AS online_total,
               (p.shopee_stock + p.lazada_stock - COALESCE(s.quantity, 0)) AS excess
        FROM products p
        LEFT JOIN stock_levels s ON s.product_id = p.id
        WHERE p.is_active = 1
          AND (p.shopee_stock + p.lazada_stock) > COALESCE(s.quantity, 0)
        ORDER BY excess DESC
    """).fetchall()
    conn.close()
    return rows


def count_stock_alerts():
    conn = get_connection()
    n = conn.execute("""
        SELECT COUNT(*) FROM products p
        LEFT JOIN stock_levels s ON s.product_id = p.id
        WHERE p.is_active = 1
          AND (p.shopee_stock + p.lazada_stock) > COALESCE(s.quantity, 0)
    """).fetchone()[0]
    conn.close()
    return n


# ── Product Locations ─────────────────────────────────────────────────────────

def get_product_locations(product_id: int):
    conn = get_connection()
    rows = conn.execute(
        "SELECT floor_no FROM product_locations WHERE product_id = ? ORDER BY floor_no",
        (product_id,)
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def save_product_locations(product_id: int, locations: list):
    conn = get_connection()
    conn.execute("DELETE FROM product_locations WHERE product_id = ?", (product_id,))
    for loc in locations:
        loc = loc.strip()
        if loc:
            conn.execute(
                "INSERT INTO product_locations (product_id, floor_no) VALUES (?, ?)",
                (product_id, loc)
            )
    conn.commit()
    conn.close()


def count_low_stock():
    conn = get_connection()
    n = conn.execute("""
        SELECT COUNT(*) FROM products p
        JOIN stock_levels s ON s.product_id = p.id
        WHERE p.is_active = 1 AND s.quantity <= p.low_stock_threshold
    """).fetchone()[0]
    conn.close()
    return n


# ── Transactions ─────────────────────────────────────────────────────────────

def add_transaction(product_id: int, txn_type: str, quantity_change: int,
                    unit_mode: str, reference_no=None, note=None):
    conn = get_connection()
    conn.execute("""
        INSERT INTO transactions (product_id, txn_type, quantity_change, unit_mode, reference_no, note)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (product_id, txn_type, quantity_change, unit_mode, reference_no, note))
    conn.commit()
    conn.close()


def get_current_stock(product_id: int) -> int:
    conn = get_connection()
    row = conn.execute("SELECT quantity FROM stock_levels WHERE product_id = ?", (product_id,)).fetchone()
    conn.close()
    return row['quantity'] if row else 0


def get_transactions(product_id=None, txn_type=None, date_from=None, date_to=None, page=1, per_page=50):
    conn = get_connection()
    conditions = ["1=1"]
    params = []
    if product_id:
        conditions.append("t.product_id = ?")
        params.append(product_id)
    if txn_type:
        conditions.append("t.txn_type = ?")
        params.append(txn_type)
    if date_from:
        conditions.append("DATE(t.created_at) >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("DATE(t.created_at) <= ?")
        params.append(date_to)

    where = " AND ".join(conditions)
    sql = f"""
        SELECT t.*, p.product_name, p.sku, p.unit_type
        FROM transactions t
        JOIN products p ON p.id = t.product_id
        WHERE {where}
        ORDER BY t.created_at DESC
        LIMIT ? OFFSET ?
    """
    rows = conn.execute(sql, params + [per_page, (page - 1) * per_page]).fetchall()
    total = conn.execute(f"SELECT COUNT(*) FROM transactions t WHERE {where}", params).fetchone()[0]
    conn.close()
    return rows, total


def get_recent_transactions(limit=10):
    conn = get_connection()
    rows = conn.execute("""
        SELECT t.*, p.product_name, p.sku, p.unit_type
        FROM transactions t
        JOIN products p ON p.id = t.product_id
        ORDER BY t.created_at DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return rows


# ── Promotions ────────────────────────────────────────────────────────────────

def get_promotions(product_id: int, active_only=False):
    conn = get_connection()
    cond = "WHERE product_id = ?"
    params = [product_id]
    if active_only:
        cond += " AND is_active = 1"
    rows = conn.execute(f"SELECT * FROM promotions {cond} ORDER BY created_at DESC", params).fetchall()
    conn.close()
    return rows


def get_active_promotion(product_id: int):
    today = date.today().isoformat()
    conn = get_connection()
    row = conn.execute("""
        SELECT * FROM promotions
        WHERE product_id = ? AND is_active = 1
          AND (date_start IS NULL OR date_start <= ?)
          AND (date_end IS NULL OR date_end >= ?)
        ORDER BY created_at DESC
        LIMIT 1
    """, (product_id, today, today)).fetchone()
    conn.close()
    return row


def effective_price(product) -> float:
    promo = get_active_promotion(product['id'])
    if promo is None:
        return product['base_sell_price']
    if promo['promo_type'] == 'percent':
        return round(product['base_sell_price'] * (1 - promo['discount_value'] / 100), 2)
    return promo['discount_value']  # fixed price


def create_promotion(data: dict) -> int:
    conn = get_connection()
    cur = conn.execute("""
        INSERT INTO promotions (product_id, promo_name, promo_type, discount_value, date_start, date_end)
        VALUES (:product_id, :promo_name, :promo_type, :discount_value, :date_start, :date_end)
    """, data)
    conn.commit()
    pid = cur.lastrowid
    conn.close()
    return pid


def deactivate_promotion(promo_id: int):
    conn = get_connection()
    conn.execute("UPDATE promotions SET is_active = 0 WHERE id = ?", (promo_id,))
    conn.commit()
    conn.close()


# ── CSV Import ────────────────────────────────────────────────────────────────

def bulk_import_products(rows: list, overwrite=False) -> tuple:
    """rows: list of dicts with CSV fields. Returns (imported, skipped)."""
    conn = get_connection()
    imported = skipped = 0
    for r in rows:
        existing = conn.execute("SELECT id FROM products WHERE sku = ?", (r['sku'],)).fetchone()
        if existing and not overwrite:
            skipped += 1
            continue
        if existing and overwrite:
            conn.execute("""
                UPDATE products SET product_name=?, units_per_carton=?, units_per_box=?,
                    unit_type=?, hard_to_sell=?
                WHERE sku=?
            """, (r['product_name'], r['units_per_carton'], r['units_per_box'],
                  r['unit_type'], r['hard_to_sell'], r['sku']))
            skipped += 1
        else:
            cur = conn.execute("""
                INSERT INTO products (sku, product_name, units_per_carton, units_per_box, unit_type, hard_to_sell)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (r['sku'], r['product_name'], r['units_per_carton'], r['units_per_box'],
                  r['unit_type'], r['hard_to_sell']))
            conn.execute("INSERT OR IGNORE INTO stock_levels (product_id, quantity) VALUES (?, 0)", (cur.lastrowid,))
            imported += 1
    conn.commit()
    conn.close()
    return imported, skipped


# ── BSN → Stock sync helpers ─────────────────────────────────────────────────

def _get_base_qty(conn, product_id: int, product_unit_type: str, bsn_unit: str, qty):
    """
    Convert BSN qty to base-unit qty.
    Returns float if conversion is known, None if the ratio is not yet defined.
    ไม่ปัดทศนิยม เพื่อรองรับ qty เช่น 0.5 หล
    """
    if bsn_unit is not None and bsn_unit.strip() == product_unit_type.strip():
        return qty
    row = conn.execute(
        "SELECT ratio FROM unit_conversions WHERE product_id = ? AND bsn_unit = ?",
        (product_id, bsn_unit)
    ).fetchone()
    if row:
        return qty * row['ratio']
    return None  # ratio not defined yet


def _sync_bsn_to_stock(conn, table: str, file_type: str):
    """
    สร้าง transaction ย้อนหลังสำหรับแถว BSN ที่มี product_id แล้ว
    แต่ยังไม่ถูก sync (synced_to_stock = 0)
    file_type: 'sales' → OUT,  'purchase' → IN
    """
    txn_type = 'IN' if file_type == 'purchase' else 'OUT'

    rows = conn.execute(
        f"SELECT * FROM {table} WHERE product_id IS NOT NULL AND synced_to_stock = 0"
    ).fetchall()

    for row in rows:
        product = conn.execute(
            "SELECT * FROM products WHERE id = ?", (row['product_id'],)
        ).fetchone()
        if not product:
            # mark synced เพื่อไม่วนซ้ำ
            conn.execute(f"UPDATE {table} SET synced_to_stock=1 WHERE id=?", (row['id'],))
            continue

        qty = row['qty'] or 0
        base_qty = _get_base_qty(conn, row['product_id'], product['unit_type'], row['unit'], qty)

        if base_qty is None:
            # Ratio not defined yet — skip until user defines it
            continue

        if base_qty > 0:
            change = base_qty if txn_type == 'IN' else -base_qty
            label  = 'ซื้อ' if file_type == 'purchase' else 'ขาย'
            conn.execute("""
                INSERT INTO transactions
                    (product_id, txn_type, quantity_change, unit_mode,
                     reference_no, note, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                row['product_id'], txn_type, change, 'unit',
                row['doc_no'],
                f'BSN {label}',
                row['date_iso'] + ' 00:00:00',
            ))

            # Deduct online stock for Shopee/Lazada store customers
            if txn_type == 'OUT':
                customer = (row['customer'] or '').strip()
                platform = None
                if customer == 'หน้าร้านL':
                    platform = 'lazada'
                    conn.execute(
                        "UPDATE products SET lazada_stock = MAX(0, lazada_stock - ?) WHERE id = ?",
                        (base_qty, row['product_id'])
                    )
                elif customer == 'หน้าร้านS':
                    platform = 'shopee'
                    conn.execute(
                        "UPDATE products SET shopee_stock = MAX(0, shopee_stock - ?) WHERE id = ?",
                        (base_qty, row['product_id'])
                    )

                # Also deduct platform_skus.stock if mapped
                if platform and row['product_id']:
                    skus = conn.execute("""
                        SELECT id, qty_per_sale, stock FROM platform_skus
                        WHERE platform = ? AND internal_product_id = ?
                          AND qty_per_sale > 0
                        ORDER BY stock DESC
                    """, (platform, row['product_id'])).fetchall()
                    remaining = float(base_qty)
                    for sku in skus:
                        if remaining <= 0:
                            break
                        qps = float(sku['qty_per_sale'])
                        platform_units = remaining / qps
                        platform_deduct = round(platform_units)
                        if platform_deduct < 1:
                            platform_deduct = 1
                        conn.execute("""
                            UPDATE platform_skus
                            SET stock = MAX(0, stock - ?)
                            WHERE id = ?
                        """, (platform_deduct, sku['id']))
                        remaining -= platform_deduct * qps

            # history_import: สร้าง IN คู่เพื่อไม่ให้กระทบสต็อค
            if row['batch_id'] == 'history_import' and txn_type == 'OUT':
                conn.execute("""
                    INSERT INTO transactions
                        (product_id, txn_type, quantity_change, unit_mode,
                         reference_no, note, created_at)
                    VALUES (?, 'IN', ?, 'unit', ?, ?, ?)
                """, (
                    row['product_id'], base_qty,
                    row['doc_no'],
                    f'ประวัติขาย (ไม่นับสต็อค): {row["product_name_raw"]}',
                    row['date_iso'] + ' 00:00:00',
                ))

        conn.execute(f"UPDATE {table} SET synced_to_stock=1 WHERE id=?", (row['id'],))


def get_pending_unit_conversions():
    conn = get_connection()
    rows = conn.execute("""
        SELECT t.product_id, t.bsn_unit, p.product_name, p.unit_type,
               t.row_count, t.example_doc
        FROM (
            SELECT product_id, unit AS bsn_unit,
                   COUNT(*) AS row_count,
                   MIN(doc_no) AS example_doc
            FROM sales_transactions
            WHERE product_id IS NOT NULL AND synced_to_stock = 0
            GROUP BY product_id, unit
            UNION ALL
            SELECT product_id, unit AS bsn_unit,
                   COUNT(*) AS row_count,
                   MIN(doc_no) AS example_doc
            FROM purchase_transactions
            WHERE product_id IS NOT NULL AND synced_to_stock = 0
            GROUP BY product_id, unit
        ) t
        JOIN products p ON p.id = t.product_id
        WHERE t.bsn_unit != p.unit_type
          AND NOT EXISTS (
              SELECT 1 FROM unit_conversions uc
              WHERE uc.product_id = t.product_id AND uc.bsn_unit = t.bsn_unit
          )
        GROUP BY t.product_id, t.bsn_unit
        ORDER BY p.product_name
    """).fetchall()
    conn.close()
    return rows


def save_unit_conversions(items: list):
    conn = get_connection()
    for item in items:
        conn.execute("""
            INSERT INTO unit_conversions (product_id, bsn_unit, ratio)
            VALUES (?, ?, ?)
            ON CONFLICT(product_id, bsn_unit) DO UPDATE SET ratio = excluded.ratio
        """, (item['product_id'], item['bsn_unit'], item['ratio']))
    # After saving, re-run sync for both tables
    _sync_bsn_to_stock(conn, 'sales_transactions', 'sales')
    _sync_bsn_to_stock(conn, 'purchase_transactions', 'purchase')
    conn.commit()
    conn.close()


def update_unit_conversion_ratio(product_id, bsn_unit, new_ratio):
    """อัปเดต ratio ที่มีอยู่แล้ว แล้ว re-sync BSN transactions ที่เกี่ยวข้อง"""
    conn = get_connection()

    # Update ratio
    conn.execute("""
        UPDATE unit_conversions SET ratio=? WHERE product_id=? AND bsn_unit=?
    """, (new_ratio, product_id, bsn_unit))

    # Delete old BSN-generated stock transactions for this product
    conn.execute("""
        DELETE FROM transactions
        WHERE product_id=? AND note LIKE 'BSN %'
          AND reference_no IN (
              SELECT doc_no FROM sales_transactions
              WHERE product_id=? AND unit=? AND synced_to_stock=1
              UNION ALL
              SELECT doc_no FROM purchase_transactions
              WHERE product_id=? AND unit=? AND synced_to_stock=1
          )
    """, (product_id, product_id, bsn_unit, product_id, bsn_unit))

    # Reset synced_to_stock for affected BSN rows
    conn.execute("""
        UPDATE sales_transactions SET synced_to_stock=0
        WHERE product_id=? AND unit=?
    """, (product_id, bsn_unit))
    conn.execute("""
        UPDATE purchase_transactions SET synced_to_stock=0
        WHERE product_id=? AND unit=?
    """, (product_id, bsn_unit))

    # Re-sync
    _sync_bsn_to_stock(conn, 'sales_transactions', 'sales')
    _sync_bsn_to_stock(conn, 'purchase_transactions', 'purchase')

    # Recalculate stock_levels
    conn.execute("DELETE FROM stock_levels WHERE product_id=?", (product_id,))
    conn.execute("""
        INSERT INTO stock_levels (product_id, quantity)
        SELECT product_id, COALESCE(SUM(quantity_change), 0)
        FROM transactions WHERE product_id=?
    """, (product_id,))

    conn.commit()
    conn.close()


def get_all_unit_conversions(search=None, page=1, per_page=50):
    conn = get_connection()
    where = ""
    params = []
    if search:
        where = "WHERE p.product_name LIKE ? OR CAST(p.sku AS TEXT) LIKE ?"
        params += [f"%{search}%", f"%{search}%"]

    sql = f"""
        SELECT uc.id, uc.product_id, uc.bsn_unit, uc.ratio,
               p.product_name, p.unit_type, p.sku,
               COALESCE(s.cnt, 0) + COALESCE(pu.cnt, 0) AS row_count
        FROM unit_conversions uc
        JOIN products p ON p.id = uc.product_id
        LEFT JOIN (
            SELECT product_id, unit, COUNT(*) AS cnt
            FROM sales_transactions
            GROUP BY product_id, unit
        ) s ON s.product_id = uc.product_id AND s.unit = uc.bsn_unit
        LEFT JOIN (
            SELECT product_id, unit, COUNT(*) AS cnt
            FROM purchase_transactions
            GROUP BY product_id, unit
        ) pu ON pu.product_id = uc.product_id AND pu.unit = uc.bsn_unit
        {where}
        ORDER BY p.product_name, uc.bsn_unit
        LIMIT ? OFFSET ?
    """
    rows = conn.execute(sql, params + [per_page, (page - 1) * per_page]).fetchall()

    count_sql = f"""
        SELECT COUNT(*) FROM unit_conversions uc
        JOIN products p ON p.id = uc.product_id
        {where}
    """
    total = conn.execute(count_sql, params).fetchone()[0]
    conn.close()
    return rows, total


def get_uncertain_no_ref_transactions():
    """ดึง transactions ที่ไม่มี reference_no จาก 2026-03-04 ที่ไม่มีคู่ซ้ำ (ที่มี ref_no)"""
    conn = get_connection()
    rows = conn.execute("""
        SELECT t.id, t.product_id, t.txn_type, t.quantity_change,
               t.unit_mode, t.created_at,
               p.product_name, p.sku, p.unit_type
        FROM transactions t
        JOIN products p ON t.product_id=p.id
        WHERE (t.reference_no IS NULL OR t.reference_no='')
          AND t.created_at >= '2026-03-04'
          AND t.txn_type = 'OUT'
          AND t.note IS NULL
          AND NOT EXISTS (
              SELECT 1 FROM transactions t2
              WHERE t2.product_id = t.product_id
                AND t2.quantity_change = t.quantity_change
                AND date(t2.created_at) = date(t.created_at)
                AND t2.txn_type = 'OUT'
                AND t2.reference_no IS NOT NULL AND t2.reference_no != ''
          )
        ORDER BY t.created_at, p.product_name
    """).fetchall()
    conn.close()
    return rows


def delete_transactions_by_ids(ids):
    if not ids:
        return
    conn = get_connection()
    try:
        placeholders = ','.join(['?']*len(ids))
        affected = [r['product_id'] for r in conn.execute(
            f"SELECT DISTINCT product_id FROM transactions WHERE id IN ({placeholders})", ids
        ).fetchall()]
        conn.execute(f"DELETE FROM transactions WHERE id IN ({placeholders})", ids)
        for pid in affected:
            conn.execute("DELETE FROM stock_levels WHERE product_id=?", (pid,))
            conn.execute("""
                INSERT INTO stock_levels (product_id, quantity)
                SELECT product_id, COALESCE(SUM(quantity_change), 0)
                FROM transactions WHERE product_id=?
                GROUP BY product_id
            """, (pid,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Product Code Mapping (BSN ↔ internal SKU) ─────────────────────────────────

def get_mapping(bsn_code: str):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM product_code_mapping WHERE bsn_code = ?", (bsn_code,)
    ).fetchone()
    conn.close()
    return row


def upsert_mapping(bsn_code: str, bsn_name: str, product_id=None, is_ignored=0):
    conn = get_connection()
    conn.execute("""
        INSERT INTO product_code_mapping (bsn_code, bsn_name, product_id, is_ignored)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(bsn_code) DO UPDATE SET
            bsn_name   = excluded.bsn_name,
            product_id = excluded.product_id,
            is_ignored = excluded.is_ignored
    """, (bsn_code, bsn_name, product_id, is_ignored))
    conn.commit()
    conn.close()


def get_pending_mappings():
    """Return all BSN codes not yet mapped and not ignored."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT * FROM product_code_mapping
        WHERE product_id IS NULL AND is_ignored = 0
        ORDER BY bsn_code
    """).fetchall()
    conn.close()
    return rows


def resolve_pending_mappings(conn):
    """
    เติม product_id ให้แถว BSN ที่ยังไม่มี แล้ว sync ไปยัง stock ทันที
    """
    for table, file_type in (
        ('sales_transactions',    'sales'),
        ('purchase_transactions', 'purchase'),
    ):
        conn.execute(f"""
            UPDATE {table}
            SET product_id = (
                SELECT m.product_id FROM product_code_mapping m
                WHERE m.bsn_code = {table}.bsn_code AND m.product_id IS NOT NULL
            )
            WHERE product_id IS NULL AND bsn_code IS NOT NULL
        """)
        # sync แถวที่เพิ่ง resolve ไปยัง transactions/stock
        _sync_bsn_to_stock(conn, table, file_type)
    conn.commit()


# ── Weekly Import ─────────────────────────────────────────────────────────────

def import_weekly(entries: list, file_type: str, filename: str) -> dict:
    """
    Insert sales or purchase entries; skip duplicates by doc_no.
    Returns stats dict.
    """
    assert file_type in ('sales', 'purchase')
    table = 'sales_transactions' if file_type == 'sales' else 'purchase_transactions'
    party_col = 'customer' if file_type == 'sales' else 'supplier'
    party_code_col = 'customer_code' if file_type == 'sales' else 'supplier_code'

    conn = get_connection()

    # Log the batch
    cur = conn.execute(
        "INSERT INTO import_log (filename, rows_imported, rows_skipped, notes) VALUES (?,0,0,?)",
        (filename, file_type)
    )
    batch_id = cur.lastrowid

    imported = skipped_dup = overwritten = 0
    new_bsn_codes = {}   # code → name for codes not yet in mapping table

    for e in entries:
        # คำนวณ doc_base ก่อน (IV6900527-1 → IV6900527, IV6900527 → IV6900527)
        doc_no   = e['doc_no']
        doc_base = doc_no.rsplit('-', 1)[0] if '-' in doc_no else doc_no
        is_weekly = (doc_no == doc_base)  # weekly format ไม่มี line suffix

        # Duplicate check แบบ 2 โหมด — ดึงแถวเก่ามาเพื่อ overwrite
        if is_weekly:
            old_rows = conn.execute(
                f"SELECT id, product_id, doc_no, synced_to_stock FROM {table}"
                f" WHERE doc_base = ? AND bsn_code = ? AND unit_price = ?",
                (doc_base, e['product_code_raw'], e['unit_price'])
            ).fetchall()
        else:
            old_rows = conn.execute(
                f"SELECT id, product_id, doc_no, synced_to_stock FROM {table}"
                f" WHERE bsn_code = ? AND (doc_no = ? OR doc_no = ?)",
                (e['product_code_raw'], doc_no, doc_base)
            ).fetchall()

        if old_rows:
            for old in old_rows:
                # ถ้า sync ไปสต็อกแล้ว ให้ลบ transaction เดิมและคำนวณสต็อกใหม่
                if old['synced_to_stock'] == 1 and old['product_id']:
                    conn.execute(
                        "DELETE FROM transactions WHERE product_id=? AND reference_no=? AND note LIKE 'BSN%'",
                        (old['product_id'], old['doc_no'])
                    )
                    conn.execute("DELETE FROM stock_levels WHERE product_id=?", (old['product_id'],))
                    conn.execute("""
                        INSERT INTO stock_levels (product_id, quantity)
                        SELECT product_id, COALESCE(SUM(quantity_change), 0)
                        FROM transactions WHERE product_id=?
                    """, (old['product_id'],))
                conn.execute(f"DELETE FROM {table} WHERE id=?", (old['id'],))
            overwritten += len(old_rows)

        # Resolve product_id via mapping table
        mapping = conn.execute(
            "SELECT product_id, is_ignored FROM product_code_mapping WHERE bsn_code = ?",
            (e['product_code_raw'],)
        ).fetchone()
        product_id = mapping['product_id'] if mapping else None
        is_ignored = mapping['is_ignored'] if mapping else 0

        if is_ignored:
            skipped_dup += 1
            continue

        # Track new BSN codes for mapping page
        if not mapping and e['product_code_raw']:
            new_bsn_codes[e['product_code_raw']] = e['product_name_raw']
        cur2 = conn.execute(f"""
            INSERT INTO {table}
                (batch_id, date_iso, doc_no, doc_base, product_id, bsn_code, product_name_raw,
                 {party_col}, {party_code_col}, qty, unit, unit_price,
                 vat_type, discount, total, net)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            batch_id, e['date_iso'], doc_no, doc_base, product_id,
            e['product_code_raw'], e['product_name_raw'],
            e['party'], e['party_code'],
            e['qty'], e['unit'], e['unit_price'],
            e['vat_type'], e['discount'], e['total'], e['net']
        ))
        imported += 1

        # sync ไปยัง stock ทันทีถ้ารู้ product_id แล้ว
        if product_id:
            _sync_bsn_to_stock(conn, table, file_type)

    # Register new BSN codes in mapping table (unmapped)
    for code, name in new_bsn_codes.items():
        conn.execute("""
            INSERT OR IGNORE INTO product_code_mapping (bsn_code, bsn_name)
            VALUES (?, ?)
        """, (code, name))

    # Update batch log
    conn.execute(
        "UPDATE import_log SET rows_imported=?, rows_skipped=? WHERE id=?",
        (imported, skipped_dup, batch_id)
    )
    conn.commit()
    conn.close()

    return {
        'imported': imported,
        'skipped_dup': skipped_dup,
        'overwritten': overwritten,
        'new_unmapped': len(new_bsn_codes),
        'batch_id': batch_id,
    }


def get_recent_imports(limit=5):
    conn = get_connection()
    rows = conn.execute(
        "SELECT filename, rows_imported, rows_skipped, imported_at, notes "
        "FROM import_log ORDER BY id DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return rows


# ── Sales Queries ─────────────────────────────────────────────────────────────

def get_sales(product_id=None, date_from=None, date_to=None,
              vat_type=None, page=1, per_page=50):
    conn = get_connection()
    conds = ['1=1']
    params = []
    if product_id:
        conds.append('s.product_id = ?'); params.append(product_id)
    if date_from:
        conds.append('s.date_iso >= ?'); params.append(date_from)
    if date_to:
        conds.append('s.date_iso <= ?'); params.append(date_to)
    if vat_type is not None:
        conds.append('s.vat_type = ?'); params.append(vat_type)
    where = ' AND '.join(conds)
    sql = f"""
        SELECT s.*,
               COALESCE(p.product_name, s.product_name_raw) AS display_name,
               p.sku
        FROM sales_transactions s
        LEFT JOIN products p ON p.id = s.product_id
        WHERE {where}
        ORDER BY s.date_iso DESC, s.doc_no
        LIMIT ? OFFSET ?
    """
    rows = conn.execute(sql, params + [per_page, (page-1)*per_page]).fetchall()
    total = conn.execute(
        f"SELECT COUNT(*) FROM sales_transactions s WHERE {where}", params
    ).fetchone()[0]
    conn.close()
    return rows, total


def get_purchases_by_doc(doc_base):
    """ดึงทุก line item ของใบสั่งซื้อ (เช่น HP6900017 → HP6900017-1, -2, ...)"""
    conn = get_connection()
    rows = conn.execute("""
        SELECT p2.*,
               COALESCE(p.product_name, p2.product_name_raw) AS display_name,
               p.sku
        FROM purchase_transactions p2
        LEFT JOIN products p ON p.id = p2.product_id
        WHERE p2.doc_no LIKE ? OR p2.doc_no = ?
        ORDER BY p2.doc_no
    """, (doc_base + '-%', doc_base)).fetchall()
    conn.close()
    return rows


def get_sales_summary(date_from=None, date_to=None):
    """Returns totals split by vat_type."""
    conn = get_connection()
    conds = ['1=1']
    params = []
    if date_from:
        conds.append('date_iso >= ?'); params.append(date_from)
    if date_to:
        conds.append('date_iso <= ?'); params.append(date_to)
    where = ' AND '.join(conds)
    rows = conn.execute(f"""
        SELECT vat_type,
               COUNT(*)       AS txn_count,
               SUM(qty)       AS total_qty,
               SUM(net)       AS total_net
        FROM sales_transactions
        WHERE {where}
        GROUP BY vat_type
    """, params).fetchall()
    conn.close()
    return rows


def get_sales_by_doc(doc_base):
    """ดึงทุก line item ของ invoice (เช่น IV6900394 → IV6900394-1, -2, ...)"""
    conn = get_connection()
    rows = conn.execute("""
        SELECT s.*,
               COALESCE(p.product_name, s.product_name_raw) AS display_name,
               p.sku
        FROM sales_transactions s
        LEFT JOIN products p ON p.id = s.product_id
        WHERE s.doc_no LIKE ? OR s.doc_no = ?
        ORDER BY CAST(SUBSTR(s.doc_no, INSTR(s.doc_no, '-') + 1) AS INTEGER)
    """, (doc_base + '-%', doc_base)).fetchall()
    conn.close()
    return rows


# ── Trade Dashboard ───────────────────────────────────────────────────────────

def get_trade_dashboard(date_from=None, date_to=None):
    """
    date_from / date_to: 'YYYY-MM-DD' strings.
    Defaults to the most recent month that has actual data.
    Returns dict with summary cards, weekly trend, top products/customers/suppliers.
    """
    import calendar as _cal

    conn = get_connection()

    if not date_from and not date_to:
        today = date.today()
        date_from = today.strftime('%Y-%m-01')
        date_to   = today.strftime(f'%Y-%m-{_cal.monthrange(today.year, today.month)[1]:02d}')
    elif date_from and not date_to:
        date_to = date.today().isoformat()
    elif date_to and not date_from:
        date_from = '2000-01-01'

    # ── Summary this month ────────────────────────────────────────────────────
    s = conn.execute("""
        SELECT COUNT(DISTINCT doc_no) AS doc_count,
               COALESCE(SUM(net), 0)  AS total_net,
               COALESCE(SUM(qty), 0)  AS total_qty
        FROM sales_transactions
        WHERE date_iso >= ? AND date_iso <= ?
    """, (date_from, date_to)).fetchone()

    p = conn.execute("""
        SELECT COUNT(DISTINCT doc_no) AS doc_count,
               COALESCE(SUM(net), 0)  AS total_net,
               COALESCE(SUM(qty), 0)  AS total_qty
        FROM purchase_transactions
        WHERE date_iso >= ? AND date_iso <= ?
    """, (date_from, date_to)).fetchone()

    # ── Weekly trend (within selected date range) ─────────────────────────────
    weekly_sales = conn.execute("""
        SELECT strftime('%Y-W%W', date_iso) AS week,
               COALESCE(SUM(net), 0) AS net
        FROM sales_transactions
        WHERE date_iso >= ? AND date_iso <= ?
        GROUP BY week ORDER BY week
    """, (date_from, date_to)).fetchall()

    weekly_pur = conn.execute("""
        SELECT strftime('%Y-W%W', date_iso) AS week,
               COALESCE(SUM(net), 0) AS net
        FROM purchase_transactions
        WHERE date_iso >= ? AND date_iso <= ?
        GROUP BY week ORDER BY week
    """, (date_from, date_to)).fetchall()

    all_weeks   = sorted(set(r['week'] for r in weekly_sales) |
                         set(r['week'] for r in weekly_pur))
    s_by_week   = {r['week']: r['net'] for r in weekly_sales}
    p_by_week   = {r['week']: r['net'] for r in weekly_pur}
    weekly_trend = [
        {'week': w, 'sales': s_by_week.get(w, 0), 'purchases': p_by_week.get(w, 0)}
        for w in all_weeks
    ]

    # ── Top 10 สินค้าขายดี (by net) ──────────────────────────────────────────
    top_products = conn.execute("""
        SELECT COALESCE(pr.product_name, s.product_name_raw) AS name,
               COALESCE(pr.sku, 0) AS sku,
               s.product_id,
               SUM(s.qty)  AS total_qty,
               SUM(s.net)  AS total_net
        FROM sales_transactions s
        LEFT JOIN products pr ON pr.id = s.product_id
        WHERE s.date_iso >= ? AND s.date_iso <= ?
        GROUP BY s.product_id, s.product_name_raw
        ORDER BY total_net DESC
        LIMIT 10
    """, (date_from, date_to)).fetchall()

    # ── Top 10 ลูกค้า ─────────────────────────────────────────────────────────
    top_customers = conn.execute("""
        SELECT customer,
               COUNT(DISTINCT doc_no) AS doc_count,
               SUM(net)               AS total_net
        FROM sales_transactions
        WHERE date_iso >= ? AND date_iso <= ?
          AND customer IS NOT NULL AND customer != ''
        GROUP BY customer
        ORDER BY total_net DESC
        LIMIT 10
    """, (date_from, date_to)).fetchall()

    # ── Top 10 ซัพพลายเออร์ ──────────────────────────────────────────────────
    top_suppliers = conn.execute("""
        SELECT supplier,
               COUNT(DISTINCT doc_no) AS doc_count,
               SUM(net)               AS total_net
        FROM purchase_transactions
        WHERE date_iso >= ? AND date_iso <= ?
          AND supplier IS NOT NULL AND supplier != ''
        GROUP BY supplier
        ORDER BY total_net DESC
        LIMIT 10
    """, (date_from, date_to)).fetchall()

    conn.close()

    return {
        'date_from': date_from,
        'date_to': date_to,
        'sales': {
            'doc_count': s['doc_count'],
            'total_net': float(s['total_net']),
            'total_qty': s['total_qty'],
        },
        'purchases': {
            'doc_count': p['doc_count'],
            'total_net': float(p['total_net']),
            'total_qty': p['total_qty'],
        },
        'gross_profit': float(s['total_net']) - float(p['total_net']),
        'weekly_trend': weekly_trend,
        'top_products':  [dict(r) for r in top_products],
        'top_customers': [dict(r) for r in top_customers],
        'top_suppliers': [dict(r) for r in top_suppliers],
    }


# ── Product Trade Summary ─────────────────────────────────────────────────────

def get_product_trade_summary(product_id, date_from=None, date_to=None):
    """
    Returns sales summary for a specific product:
    top customers, monthly trend, recent docs.
    """
    conn = get_connection()
    conds = ['s.product_id = ?']
    params = [product_id]
    if date_from:
        conds.append('s.date_iso >= ?'); params.append(date_from)
    if date_to:
        conds.append('s.date_iso <= ?'); params.append(date_to)
    where = ' AND '.join(conds)

    product = conn.execute(
        'SELECT id, sku, product_name FROM products WHERE id = ?', (product_id,)
    ).fetchone()

    summary = conn.execute(f"""
        SELECT COUNT(DISTINCT s.doc_no) AS doc_count,
               COALESCE(SUM(s.net), 0)  AS total_net,
               COALESCE(SUM(s.qty), 0)  AS total_qty,
               MIN(s.date_iso)          AS first_date,
               MAX(s.date_iso)          AS last_date
        FROM sales_transactions s
        WHERE {where}
    """, params).fetchone()

    top_customers = conn.execute(f"""
        SELECT s.customer,
               SUM(s.qty)            AS total_qty,
               SUM(s.net)            AS total_net,
               COUNT(DISTINCT s.doc_no) AS doc_count
        FROM sales_transactions s
        WHERE {where}
          AND s.customer IS NOT NULL AND s.customer != ''
        GROUP BY s.customer
        ORDER BY total_net DESC
        LIMIT 20
    """, params).fetchall()

    monthly = conn.execute(f"""
        SELECT strftime('%Y-%m', s.date_iso) AS month,
               COUNT(DISTINCT s.doc_no) AS doc_count,
               SUM(s.qty)  AS total_qty,
               SUM(s.net)  AS total_net
        FROM sales_transactions s
        WHERE {where}
        GROUP BY month
        ORDER BY month
    """, params).fetchall()

    docs = conn.execute(f"""
        SELECT s.date_iso, s.doc_no, s.customer,
               SUM(s.qty) AS total_qty,
               SUM(s.net) AS total_net
        FROM sales_transactions s
        WHERE {where}
        GROUP BY s.doc_no
        ORDER BY s.date_iso DESC, s.doc_no
        LIMIT 200
    """, params).fetchall()

    conn.close()
    return {
        'product':    dict(product) if product else {},
        'date_from':  date_from,
        'date_to':    date_to,
        'summary':    dict(summary),
        'top_customers': [dict(r) for r in top_customers],
        'monthly':    [dict(r) for r in monthly],
        'docs':       [dict(r) for r in docs],
    }


# ── Customer Summary ──────────────────────────────────────────────────────────

def get_customer_summary(customer, date_from=None, date_to=None):
    """
    Returns summary + top products + monthly trend for a specific customer.
    """
    conn = get_connection()
    conds = ['customer = ?']
    params = [customer]
    if date_from:
        conds.append('date_iso >= ?'); params.append(date_from)
    if date_to:
        conds.append('date_iso <= ?'); params.append(date_to)
    where = ' AND '.join(conds)

    summary = conn.execute(f"""
        SELECT COUNT(DISTINCT doc_no) AS doc_count,
               COALESCE(SUM(net), 0)  AS total_net,
               COALESCE(SUM(qty), 0)  AS total_qty,
               MIN(date_iso)          AS first_date,
               MAX(date_iso)          AS last_date
        FROM sales_transactions
        WHERE {where}
    """, params).fetchone()

    top_products = conn.execute(f"""
        SELECT COALESCE(p.product_name, s.product_name_raw) AS name,
               COALESCE(p.sku, 0) AS sku,
               p.id AS product_id,
               s.unit,
               SUM(s.qty)  AS total_qty,
               SUM(s.net)  AS total_net,
               COUNT(DISTINCT s.doc_no) AS doc_count
        FROM sales_transactions s
        LEFT JOIN products p ON p.id = s.product_id
        WHERE {where}
        GROUP BY s.product_id, s.product_name_raw
        ORDER BY total_net DESC
        LIMIT 20
    """, params).fetchall()

    monthly = conn.execute(f"""
        SELECT strftime('%Y-%m', date_iso) AS month,
               COUNT(DISTINCT doc_no) AS doc_count,
               SUM(net) AS total_net
        FROM sales_transactions
        WHERE {where}
        GROUP BY month
        ORDER BY month
    """, params).fetchall()

    # All invoices (paginated not needed here — keep it simple, limit 200)
    docs = conn.execute(f"""
        SELECT date_iso, doc_no,
               COUNT(*) AS line_count,
               SUM(qty) AS total_qty,
               SUM(net) AS total_net
        FROM sales_transactions
        WHERE {where}
        GROUP BY doc_no
        ORDER BY date_iso DESC, doc_no
        LIMIT 200
    """, params).fetchall()

    # Region info
    region_row = conn.execute("""
        SELECT cr.region, cr.salesperson, s.customer_code
        FROM sales_transactions s
        LEFT JOIN customer_regions cr ON cr.customer_code = s.customer_code
        WHERE s.customer = ?
        LIMIT 1
    """, [customer]).fetchone()

    # Customer master info from BSN import
    customer_info = None
    if region_row and region_row['customer_code']:
        row = conn.execute(
            "SELECT * FROM customers WHERE code=?", [region_row['customer_code']]
        ).fetchone()
        if row:
            customer_info = dict(row)

    conn.close()
    return {
        'customer': customer,
        'customer_code': region_row['customer_code'] if region_row else None,
        'region': region_row['region'] if region_row else None,
        'salesperson': region_row['salesperson'] if region_row else None,
        'customer_info': customer_info,
        'date_from': date_from,
        'date_to': date_to,
        'summary': dict(summary),
        'top_products': [dict(r) for r in top_products],
        'monthly': [dict(r) for r in monthly],
        'docs': [dict(r) for r in docs],
    }


# ── Customer List ─────────────────────────────────────────────────────────────

def get_regions():
    conn = get_connection()
    rows = conn.execute(
        "SELECT DISTINCT region FROM customer_regions WHERE region IS NOT NULL ORDER BY region"
    ).fetchall()
    conn.close()
    return [r['region'] for r in rows]


def get_customers(search=None, region=None, page=1, per_page=50):
    conn = get_connection()
    conds = []
    params = []
    if search:
        conds.append("(s.customer LIKE ? OR s.customer_code LIKE ?)")
        params += [f"%{search}%", f"%{search}%"]
    if region:
        conds.append("cr.region = ?")
        params.append(region)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""

    sql = f"""
        SELECT s.customer, s.customer_code,
               cr.region, cr.salesperson,
               COUNT(DISTINCT s.doc_no) AS doc_count,
               COALESCE(SUM(s.net), 0)  AS total_net,
               MAX(s.date_iso)          AS last_date
        FROM sales_transactions s
        LEFT JOIN customer_regions cr ON cr.customer_code = s.customer_code
        {where}
        GROUP BY s.customer_code
        ORDER BY s.customer
        LIMIT ? OFFSET ?
    """
    rows = conn.execute(sql, params + [per_page, (page - 1) * per_page]).fetchall()

    count_sql = f"""
        SELECT COUNT(DISTINCT s.customer_code)
        FROM sales_transactions s
        LEFT JOIN customer_regions cr ON cr.customer_code = s.customer_code
        {where}
    """
    total = conn.execute(count_sql, params).fetchone()[0]
    conn.close()
    return [dict(r) for r in rows], total


# ── Purchase Queries ──────────────────────────────────────────────────────────

def get_purchases(product_id=None, date_from=None, date_to=None, page=1, per_page=50):
    conn = get_connection()
    conds = ['1=1']
    params = []
    if product_id:
        conds.append('p2.product_id = ?'); params.append(product_id)
    if date_from:
        conds.append('p2.date_iso >= ?'); params.append(date_from)
    if date_to:
        conds.append('p2.date_iso <= ?'); params.append(date_to)
    where = ' AND '.join(conds)
    sql = f"""
        SELECT p2.*,
               COALESCE(p.product_name, p2.product_name_raw) AS display_name,
               p.sku
        FROM purchase_transactions p2
        LEFT JOIN products p ON p.id = p2.product_id
        WHERE {where}
        ORDER BY p2.date_iso DESC, p2.doc_no
        LIMIT ? OFFSET ?
    """
    rows = conn.execute(sql, params + [per_page, (page-1)*per_page]).fetchall()
    total = conn.execute(
        f"SELECT COUNT(*) FROM purchase_transactions p2 WHERE {where}", params
    ).fetchone()[0]
    conn.close()
    return rows, total


# ── Payment Status ─────────────────────────────────────────────────────────────

def parse_payment_csv(filepath):
    """Parse การรับชำระหนี้ CSV (cp874). Returns list of RE dicts with iv_list."""
    import re as _re
    records = []
    current = None
    with open(filepath, encoding='cp874') as f:
        for line in f:
            text = line.strip().strip('"').replace('\xa0', ' ')
            if not text:
                continue
            # RE header row
            m = _re.match(r'^(\d{2}/\d{2}/\d{2})\s+(\*?RE\S+)\s+(.+?)\s{2,}(\w+)\s', text)
            if m:
                if current:
                    records.append(current)
                d, re_no, customer, sp = m.groups()
                cancelled = re_no.startswith('*')
                re_no_clean = re_no.lstrip('*')
                dd, mm, yy = d.split('/')
                year_ce = int(yy) + 2500 - 543
                date_iso = f"{year_ce}-{mm}-{dd}"
                current = {
                    're_no': re_no_clean,
                    'cancelled': cancelled,
                    'date_iso': date_iso,
                    'customer': customer.strip(),
                    'salesperson': sp.strip(),
                    'iv_list': []
                }
                continue
            # IV sub-row
            m2 = _re.match(r'\s*(IV\S+)\s+\d{2}/\d{2}/\d{2}\s+[\d,]+\.\d{2}', text)
            if m2 and current:
                current['iv_list'].append(m2.group(1))
    if current:
        records.append(current)
    return records


def import_payments(filepath):
    """Import payment CSV into received_payments + paid_invoices tables.
    Returns dict with imported, skipped, total counts."""
    records = parse_payment_csv(filepath)
    conn = get_connection()
    imported = 0
    skipped = 0
    for r in records:
        try:
            cur = conn.execute(
                "INSERT OR IGNORE INTO received_payments (re_no, date_iso, customer, salesperson, cancelled) VALUES (?,?,?,?,?)",
                (r['re_no'], r['date_iso'], r['customer'], r['salesperson'], 1 if r['cancelled'] else 0)
            )
            if cur.lastrowid and cur.rowcount:
                re_id = cur.lastrowid
                for iv in r['iv_list']:
                    conn.execute(
                        "INSERT OR IGNORE INTO paid_invoices (re_id, iv_no) VALUES (?,?)",
                        (re_id, iv)
                    )
                imported += 1
            else:
                skipped += 1
        except Exception:
            skipped += 1
    conn.commit()
    conn.close()
    return {'imported': imported, 'skipped': skipped, 'total': len(records)}


def get_payment_status(status='all', search='', date_from='', date_to='', page=1, per_page=50):
    """Get IV invoices with payment status.
    Uses pre-computed doc_base column + index for performance.
    """
    conn = get_connection()

    conds = ["st.doc_base IS NOT NULL", "st.doc_base NOT LIKE 'SR%'", "st.doc_base NOT LIKE 'HS%'"]
    params = []

    if search:
        conds.append("(st.doc_base LIKE ? OR st.customer LIKE ?)")
        params += [f'%{search}%', f'%{search}%']
    if date_from:
        conds.append("st.date_iso >= ?"); params.append(date_from)
    if date_to:
        conds.append("st.date_iso <= ?"); params.append(date_to)

    paid_filter = ''
    if status == 'paid':
        paid_filter = 'HAVING is_paid = 1'
    elif status == 'unpaid':
        paid_filter = 'HAVING is_paid = 0 AND total_net > 0'
    else:
        paid_filter = 'HAVING total_net > 0'

    where = ' AND '.join(conds)

    sql = f"""
        SELECT
            st.doc_base,
            MIN(st.date_iso) AS bill_date,
            st.customer,
            SUM(CASE WHEN st.vat_type = 2 THEN st.net * 1.07 ELSE st.net END) AS total_net,
            MAX(CASE WHEN pi.iv_no IS NOT NULL THEN 1 ELSE 0 END) AS is_paid,
            MAX(rp.date_iso) AS paid_date,
            MAX(rp.re_no) AS re_no
        FROM sales_transactions st
        LEFT JOIN paid_invoices pi ON pi.iv_no = st.doc_base
        LEFT JOIN received_payments rp ON rp.id = pi.re_id AND rp.cancelled = 0
        WHERE {where}
        GROUP BY st.doc_base
        {paid_filter}
        ORDER BY bill_date DESC
        LIMIT ? OFFSET ?
    """
    rows = conn.execute(sql, params + [per_page, (page - 1) * per_page]).fetchall()

    count_sql = f"""
        SELECT COUNT(*) FROM (
            SELECT st.doc_base,
                MAX(CASE WHEN pi.iv_no IS NOT NULL THEN 1 ELSE 0 END) AS is_paid,
                SUM(CASE WHEN st.vat_type = 2 THEN st.net * 1.07 ELSE st.net END) AS total_net
            FROM sales_transactions st
            LEFT JOIN paid_invoices pi ON pi.iv_no = st.doc_base
            LEFT JOIN received_payments rp ON rp.id = pi.re_id AND rp.cancelled = 0
            WHERE {where}
            GROUP BY st.doc_base
            {paid_filter}
        )
    """
    total = conn.execute(count_sql, params).fetchone()[0]
    conn.close()
    return rows, total


def get_payment_summary():
    """Quick stats for payment status page."""
    conn = get_connection()
    row = conn.execute("""
        SELECT
            COUNT(DISTINCT st.doc_base) AS total_bills,
            SUM(CASE WHEN pi.iv_no IS NOT NULL THEN 1 ELSE 0 END) AS paid_count,
            SUM(CASE WHEN pi.iv_no IS NULL THEN 1 ELSE 0 END) AS unpaid_count,
            SUM(CASE WHEN pi.iv_no IS NOT NULL THEN st.net ELSE 0 END) AS paid_amount,
            SUM(CASE WHEN pi.iv_no IS NULL THEN st.net ELSE 0 END) AS unpaid_amount
        FROM (
            SELECT doc_base,
                   SUM(CASE WHEN vat_type = 2 THEN net * 1.07 ELSE net END) AS net
            FROM sales_transactions
            WHERE doc_base IS NOT NULL AND doc_base NOT LIKE 'SR%' AND doc_base NOT LIKE 'HS%'
            GROUP BY doc_base
            HAVING SUM(CASE WHEN vat_type = 2 THEN net * 1.07 ELSE net END) > 0
        ) st
        LEFT JOIN paid_invoices pi ON pi.iv_no = st.doc_base
        LEFT JOIN received_payments rp ON rp.id = pi.re_id AND rp.cancelled = 0
    """).fetchone()
    conn.close()
    return row


def get_customer_debt_summary(search=''):
    """สรุปหนี้ค้างชำระรายลูกค้า เรียงตามยอดค้างมากสุด"""
    conn = get_connection()
    cond = ""
    params = []
    if search:
        cond = "AND st.customer LIKE ?"
        params.append(f'%{search}%')

    rows = conn.execute(f"""
        SELECT
            st.customer,
            st.customer_code,
            COUNT(DISTINCT st.doc_base) AS unpaid_bills,
            SUM(CASE WHEN st.vat_type = 2 THEN st.net * 1.07 ELSE st.net END) AS outstanding_amount
        FROM sales_transactions st
        LEFT JOIN paid_invoices pi ON pi.iv_no = st.doc_base
        WHERE st.doc_base IS NOT NULL
          AND st.doc_base NOT LIKE 'SR%' AND st.doc_base NOT LIKE 'HS%'
          AND pi.iv_no IS NULL
          {cond}
        GROUP BY st.customer, st.customer_code
        HAVING outstanding_amount > 0
        ORDER BY outstanding_amount DESC
    """, params).fetchall()

    conn.close()
    return rows


def find_payment_candidates(amount, tolerance_pct=5):
    """คาดคะเนลูกค้าที่น่าจะโอนเงิน amount บาท
    ลองทุก subset ของบิลที่ค้างชำระของแต่ละลูกค้า
    คืนค่า list of dict เรียงตาม abs(diff) ASC
    """
    from itertools import combinations

    conn = get_connection()
    # ดึงบิลค้างชำระทั้งหมดแยกรายบิล (รวม vat_type ที่พบมากที่สุดในบิล)
    bill_rows = conn.execute("""
        SELECT st.customer, st.customer_code, st.doc_base,
               SUM(CASE WHEN st.vat_type=2 THEN st.net*1.07 ELSE st.net END) AS bill_net,
               MAX(st.vat_type) AS vat_type
        FROM sales_transactions st
        LEFT JOIN paid_invoices pi ON pi.iv_no = st.doc_base
        WHERE st.doc_base IS NOT NULL
          AND st.doc_base NOT LIKE 'SR%' AND st.doc_base NOT LIKE 'HS%'
          AND pi.iv_no IS NULL
        GROUP BY st.customer, st.customer_code, st.doc_base
        HAVING bill_net > 0
        ORDER BY st.customer, st.doc_base
    """).fetchall()
    conn.close()

    # จัดกลุ่มตามลูกค้า
    customers = {}
    for r in bill_rows:
        key = r['customer']
        if key not in customers:
            customers[key] = {'customer_code': r['customer_code'], 'bills': []}
        customers[key]['bills'].append({'doc_base': r['doc_base'], 'net': r['bill_net'], 'vat_type': r['vat_type']})

    tolerance = max(amount * tolerance_pct / 100, 200)
    results = []

    for customer, data in customers.items():
        bills = data['bills']
        if len(bills) > 15:
            # ถ้าบิลเยอะเกินไป ตรวจแค่ยอดรวมทั้งหมด
            total = sum(b['net'] for b in bills)
            if abs(total - amount) <= tolerance:
                results.append({
                    'customer': customer,
                    'customer_code': data['customer_code'],
                    'matched_bills': [{'doc_base': b['doc_base'], 'vat_type': b['vat_type']} for b in bills],
                    'matched_sum': total,
                    'diff': total - amount,
                    'total_unpaid_bills': len(bills),
                    'total_outstanding': total,
                })
            continue

        best_per_customer = []
        for r in range(1, len(bills) + 1):
            for combo in combinations(bills, r):
                combo_sum = sum(b['net'] for b in combo)
                diff = combo_sum - amount
                if abs(diff) <= tolerance:
                    best_per_customer.append({
                        'customer': customer,
                        'customer_code': data['customer_code'],
                        'matched_bills': [{'doc_base': b['doc_base'], 'vat_type': b['vat_type']} for b in combo],
                        'matched_sum': combo_sum,
                        'diff': diff,
                        'total_unpaid_bills': len(bills),
                        'total_outstanding': sum(b['net'] for b in bills),
                    })

        # เก็บแค่ 3 combo ที่ใกล้ที่สุดต่อลูกค้า
        best_per_customer.sort(key=lambda x: abs(x['diff']))
        results.extend(best_per_customer[:3])

    results.sort(key=lambda x: abs(x['diff']))
    return results[:20]


def get_product_pricing_summary(product_id):
    """สรุปราคา BSN สำหรับหน้า product detail (avg_list_price, avg_effective)"""
    conn = get_connection()
    row = conn.execute("""
        SELECT
            SUM(unit_price * qty) / NULLIF(SUM(qty), 0) AS avg_list_price,
            SUM(CASE WHEN vat_type = 2 THEN net * 1.07 ELSE net END)
              / NULLIF(SUM(qty), 0)                      AS avg_effective,
            COUNT(DISTINCT unit_price)                   AS price_variants
        FROM sales_transactions
        WHERE product_id = ? AND qty > 0 AND unit_price > 0
    """, [product_id]).fetchone()
    conn.close()
    return {
        'avg_list_price': row['avg_list_price'] or 0.0,
        'avg_effective':  row['avg_effective']  or 0.0,
        'price_variants': row['price_variants'] or 0,
    }


def get_product_pricing(product_id):
    """ราคาขายสินค้า: list_prices (GROUP BY unit_price,vat_type) + effective_per_customer"""
    from collections import defaultdict

    conn = get_connection()

    # ── ราคาตั้งต่อ (unit_price, vat_type) ──────────────────────────────────
    price_rows = conn.execute("""
        SELECT
            unit_price,
            vat_type,
            COUNT(DISTINCT doc_no)  AS invoice_count,
            SUM(qty)                AS total_qty,
            MAX(date_iso)           AS last_sale,
            COUNT(DISTINCT customer) AS customer_count
        FROM sales_transactions
        WHERE product_id = ?
          AND qty > 0
          AND unit_price > 0
        GROUP BY unit_price, vat_type
        ORDER BY invoice_count DESC
    """, [product_id]).fetchall()

    # ── รายร้านค้าต่อ (unit_price, vat_type, customer) ───────────────────────
    cust_rows = conn.execute("""
        SELECT
            unit_price,
            vat_type,
            customer,
            customer_code,
            COUNT(DISTINCT doc_no)          AS invoice_count,
            SUM(qty)                        AS total_qty,
            MAX(date_iso)                   AS last_sale,
            GROUP_CONCAT(DISTINCT discount) AS discounts
        FROM sales_transactions
        WHERE product_id = ?
          AND qty > 0
          AND unit_price > 0
        GROUP BY unit_price, vat_type, customer
        ORDER BY unit_price, last_sale DESC
    """, [product_id]).fetchall()

    # ── ราคาจริงเฉลี่ยต่อร้าน ────────────────────────────────────────────────
    eff_rows = conn.execute("""
        SELECT
            customer,
            customer_code,
            COUNT(DISTINCT doc_no)  AS invoice_count,
            SUM(qty)                AS total_qty,
            SUM(CASE WHEN vat_type = 2 THEN net * 1.07 ELSE net END)
              / NULLIF(SUM(qty), 0) AS avg_effective,
            MAX(date_iso)           AS last_sale
        FROM sales_transactions
        WHERE product_id = ?
          AND qty > 0
          AND unit_price > 0
        GROUP BY customer
        ORDER BY avg_effective DESC
    """, [product_id]).fetchall()

    # ── สรุปภาพรวม ────────────────────────────────────────────────────────────
    summary = conn.execute("""
        SELECT
            SUM(unit_price * qty) / NULLIF(SUM(qty), 0)                          AS avg_list_price,
            SUM(CASE WHEN vat_type = 2 THEN net * 1.07 ELSE net END)
              / NULLIF(SUM(qty), 0)                                               AS avg_effective,
            COUNT(DISTINCT doc_no)                                                AS total_invoices,
            SUM(qty)                                                              AS total_qty
        FROM sales_transactions
        WHERE product_id = ?
          AND qty > 0
          AND unit_price > 0
    """, [product_id]).fetchone()

    conn.close()

    # ── group customers เข้า list_prices ─────────────────────────────────────
    cust_map = defaultdict(list)
    for r in cust_rows:
        key = (r['unit_price'], r['vat_type'])
        cust_map[key].append({
            'customer':       r['customer'],
            'customer_code':  r['customer_code'],
            'invoice_count':  r['invoice_count'],
            'total_qty':      r['total_qty'],
            'last_sale':      r['last_sale'],
            'discounts':      r['discounts'] or '',
        })

    list_prices = []
    for r in price_rows:
        key = (r['unit_price'], r['vat_type'])
        list_prices.append({
            'unit_price':     r['unit_price'],
            'vat_type':       r['vat_type'],
            'invoice_count':  r['invoice_count'],
            'total_qty':      r['total_qty'],
            'last_sale':      r['last_sale'],
            'customer_count': r['customer_count'],
            'customers':      cust_map.get(key, []),
        })

    effective_per_customer = [
        {
            'customer':      r['customer'],
            'customer_code': r['customer_code'],
            'invoice_count': r['invoice_count'],
            'total_qty':     r['total_qty'],
            'avg_effective': r['avg_effective'],
            'last_sale':     r['last_sale'],
        }
        for r in eff_rows
    ]

    return {
        'list_prices':            list_prices,
        'effective_per_customer': effective_per_customer,
        'avg_list_price':         summary['avg_list_price'] or 0.0,
        'avg_effective':          summary['avg_effective'] or 0.0,
        'total_invoices':         summary['total_invoices'] or 0,
        'total_qty':              summary['total_qty'] or 0.0,
    }


def get_customer_unpaid_bills(customer_name):
    """รายการบิลค้างชำระของลูกค้าคนนี้"""
    conn = get_connection()
    rows = conn.execute("""
        SELECT
            st.doc_base,
            MIN(st.date_iso) AS bill_date,
            st.customer,
            st.customer_code,
            MAX(st.vat_type) AS vat_type,
            SUM(CASE WHEN st.vat_type = 2 THEN st.net * 1.07 ELSE st.net END) AS total_net
        FROM sales_transactions st
        LEFT JOIN paid_invoices pi ON pi.iv_no = st.doc_base
        LEFT JOIN received_payments rp ON rp.id = pi.re_id AND rp.cancelled = 0
        WHERE st.doc_base IS NOT NULL
          AND st.doc_base NOT LIKE 'SR%' AND st.doc_base NOT LIKE 'HS%'
          AND st.customer = ?
          AND pi.iv_no IS NULL
        GROUP BY st.doc_base
        HAVING total_net > 0
        ORDER BY bill_date DESC
    """, [customer_name]).fetchall()
    conn.close()
    return rows


# ── E-commerce Platform SKUs ──────────────────────────────────────────────────

def import_platform_skus(platform, records):
    """Replace all SKUs for a platform with new records. Returns count inserted."""
    conn = get_connection()
    conn.execute("DELETE FROM platform_skus WHERE platform = ?", (platform,))
    count = 0
    for r in records:
        conn.execute("""
            INSERT INTO platform_skus
              (platform, product_id_str, product_name, variation_id, variation_name,
               parent_sku, seller_sku, price, special_price, stock, qty_per_sale, raw_json)
            VALUES (?,?,?,?,?,?,?,?,?,?,1,?)
            ON CONFLICT(platform, variation_id) DO UPDATE SET
              product_name  = excluded.product_name,
              product_id_str= excluded.product_id_str,
              variation_name= excluded.variation_name,
              parent_sku    = excluded.parent_sku,
              seller_sku    = excluded.seller_sku,
              price         = excluded.price,
              special_price = excluded.special_price,
              stock         = excluded.stock,
              raw_json      = excluded.raw_json,
              imported_at   = datetime('now','localtime')
        """, (
            platform,
            r.get('product_id_str'), r.get('product_name', ''),
            r.get('variation_id'),   r.get('variation_name'),
            r.get('parent_sku'),     r.get('seller_sku'),
            r.get('price'),          r.get('special_price'),
            r.get('stock'),          r.get('raw_json'),
        ))
        count += 1
    conn.commit()
    conn.close()
    return count


def get_platform_skus(platform, search=None, page=1, per_page=50):
    conn = get_connection()
    params = [platform]
    where = "WHERE platform = ?"
    if search:
        where += " AND (product_name LIKE ? OR variation_name LIKE ? OR seller_sku LIKE ?)"
        params += [f"%{search}%", f"%{search}%", f"%{search}%"]
    total = conn.execute(
        f"SELECT COUNT(*) FROM platform_skus {where}", params
    ).fetchone()[0]
    offset = (page - 1) * per_page
    rows = conn.execute(
        f"""SELECT * FROM platform_skus {where}
            ORDER BY product_name, variation_name
            LIMIT ? OFFSET ?""",
        params + [per_page, offset]
    ).fetchall()
    conn.close()
    return rows, total


def get_platform_skus_all(platform):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM platform_skus WHERE platform = ? ORDER BY product_name, variation_name",
        (platform,)
    ).fetchall()
    conn.close()
    return rows


def get_platform_summary():
    conn = get_connection()
    rows = conn.execute("""
        SELECT platform,
               COUNT(*) AS sku_count,
               SUM(stock) AS total_stock,
               MAX(imported_at) AS last_import
        FROM platform_skus
        GROUP BY platform
    """).fetchall()
    conn.close()
    return {r['platform']: dict(r) for r in rows}


def update_platform_sku(sku_id, price, special_price, stock, qty_per_sale):
    conn = get_connection()
    conn.execute("""
        UPDATE platform_skus
        SET price=?, special_price=?, stock=?, qty_per_sale=?,
            imported_at=datetime('now','localtime')
        WHERE id=?
    """, (price, special_price, stock, qty_per_sale, sku_id))
    conn.commit()
    conn.close()


def get_platform_mapping_data():
    """
    Return all platform_skus joined with internal product info (if mapped).
    Used for mapping export/import.
    """
    conn = get_connection()
    rows = conn.execute("""
        SELECT
            ps.id, ps.platform, ps.product_id_str, ps.product_name,
            ps.variation_id, ps.variation_name, ps.seller_sku,
            ps.price, ps.special_price, ps.stock, ps.qty_per_sale,
            ps.internal_product_id,
            p.sku AS internal_sku, p.product_name AS internal_product_name,
            p.unit_type
        FROM platform_skus ps
        LEFT JOIN products p ON p.id = ps.internal_product_id
        ORDER BY ps.platform, ps.product_name, ps.variation_name
    """).fetchall()
    conn.close()
    return rows


def apply_platform_mapping(rows):
    """
    rows: list of dicts with keys: platform_sku_id, internal_sku, qty_per_sale
    Returns (updated, not_found) counts.
    """
    conn = get_connection()
    updated, not_found = 0, 0
    for r in rows:
        sku_id      = r.get('platform_sku_id')
        int_sku     = r.get('internal_sku')
        qty_per_sale = r.get('qty_per_sale')

        if not sku_id:
            continue

        if int_sku:
            product = conn.execute(
                "SELECT id FROM products WHERE sku = ? AND is_active = 1",
                (int_sku,)
            ).fetchone()
            if not product:
                not_found += 1
                continue
            product_id = product['id']
        else:
            product_id = None

        conn.execute("""
            UPDATE platform_skus
            SET internal_product_id = ?,
                qty_per_sale = COALESCE(?, qty_per_sale)
            WHERE id = ?
        """, (product_id, qty_per_sale, sku_id))
        updated += 1

    conn.commit()
    conn.close()
    return updated, not_found


def suggest_platform_mapping():
    """
    For every platform_sku, suggest the best-matching internal product.
    Returns dict: { platform_sku_id -> {suggested_sku, suggested_name, confidence} }
    """
    import re
    import numpy as np
    from rapidfuzz import fuzz
    from rapidfuzz.process import cdist

    conn = get_connection()
    product_list = list(conn.execute(
        "SELECT id, sku, product_name FROM products WHERE is_active = 1"
    ).fetchall())
    psku_list = list(conn.execute(
        "SELECT id, product_name, variation_name, seller_sku, internal_product_id "
        "FROM platform_skus"
    ).fetchall())
    conn.close()

    corpus  = [_clean_for_match(p['product_name']) for p in product_list]
    queries = [
        _clean_for_match(
            f"{s['product_name']} {s['variation_name'] or ''} {s['seller_sku'] or ''}"
        )
        for s in psku_list
    ]

    # Batch fuzzy match (workers=-1 = all CPU cores)
    matrix = cdist(queries, corpus, scorer=fuzz.token_set_ratio, workers=-1)
    best_idx   = matrix.argmax(axis=1)
    best_score = matrix.max(axis=1)

    results = {}
    for i, sku in enumerate(psku_list):
        sku_id = sku['id']

        # Already mapped → confidence 100, keep existing
        if sku['internal_product_id']:
            matched = next(
                (p for p in product_list if p['id'] == sku['internal_product_id']), None
            )
            if matched:
                results[sku_id] = {
                    'suggested_sku':  matched['sku'],
                    'suggested_name': matched['product_name'],
                    'confidence':     100,
                }
                continue

        score = int(best_score[i])
        if score < 25:
            continue
        product = product_list[best_idx[i]]
        results[sku_id] = {
            'suggested_sku':  product['sku'],
            'suggested_name': product['product_name'],
            'confidence':     score,
        }

    return results


import re as _re_mod
# Noise words to strip before matching (brands, filler marketing words)
_NOISE_WORDS = _re_mod.compile(
    r'\b(sendai|golden\s*lion|ม้าลอดห่วง|สิงห์|คุณภาพดี|อย่างดี|ราคาถูก'
    r'|ของแท้|สินค้าดี|มีให้เลือก|เกรดa|เกรด\s*a|ฟรี|ส่งฟรี|แพ็ค|pack'
    r'|แถมฟรี|โปรโมชั่น|ราคาพิเศษ)\b',
    _re_mod.IGNORECASE
)
_QTY_PREFIX = _re_mod.compile(r'[\(\[【]\s*[\d,./]+\s*[^\)\]】]*[\)\]】]')


def _clean_for_match(text):
    """Strip brand noise & qty-prefixes, return lowercase normalized string."""
    text = _QTY_PREFIX.sub(' ', text or '')
    text = _NOISE_WORDS.sub(' ', text)
    text = text.lower()
    text = _re_mod.sub(r'[()（）【】\[\]\'""]', ' ', text)
    text = _re_mod.sub(r'\s+', ' ', text).strip()
    return text


# ── Product Conversion Formulas (สูตรแปลงสินค้า) ────────────────────────────

def get_conversion_formulas():
    conn = get_connection()
    rows = conn.execute("""
        SELECT cf.id, cf.name, cf.output_product_id, cf.output_qty,
               cf.note, cf.is_active, cf.created_at,
               p.product_name AS output_product_name,
               p.unit_type    AS output_unit_type,
               COUNT(cfi.id)  AS input_count
          FROM conversion_formulas cf
          JOIN products p ON p.id = cf.output_product_id
          LEFT JOIN conversion_formula_inputs cfi ON cfi.formula_id = cf.id
         GROUP BY cf.id
         ORDER BY cf.is_active DESC, cf.name
    """).fetchall()
    conn.close()
    return rows


def get_conversion_formula(formula_id):
    conn = get_connection()
    formula = conn.execute("""
        SELECT cf.*, p.product_name AS output_product_name,
               p.unit_type AS output_unit_type,
               COALESCE(sl.quantity, 0) AS output_stock
          FROM conversion_formulas cf
          JOIN products p ON p.id = cf.output_product_id
          LEFT JOIN stock_levels sl ON sl.product_id = cf.output_product_id
         WHERE cf.id = ?
    """, (formula_id,)).fetchone()
    if not formula:
        conn.close()
        return None, []
    inputs = conn.execute("""
        SELECT cfi.id, cfi.product_id, cfi.quantity,
               p.product_name, p.unit_type,
               COALESCE(sl.quantity, 0) AS current_stock
          FROM conversion_formula_inputs cfi
          JOIN products p ON p.id = cfi.product_id
          LEFT JOIN stock_levels sl ON sl.product_id = cfi.product_id
         WHERE cfi.formula_id = ?
         ORDER BY cfi.id
    """, (formula_id,)).fetchall()
    conn.close()
    return formula, inputs


def create_conversion_formula(name, output_product_id, output_qty, inputs, note=''):
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO conversion_formulas(name, output_product_id, output_qty, note) VALUES (?,?,?,?)",
        (name, output_product_id, output_qty, note or None)
    )
    formula_id = cur.lastrowid
    for inp in inputs:
        conn.execute(
            "INSERT INTO conversion_formula_inputs(formula_id, product_id, quantity) VALUES (?,?,?)",
            (formula_id, inp['product_id'], inp['quantity'])
        )
    conn.commit()
    conn.close()
    return formula_id


def update_conversion_formula(formula_id, name, output_product_id, output_qty, inputs, note=''):
    conn = get_connection()
    conn.execute(
        "UPDATE conversion_formulas SET name=?, output_product_id=?, output_qty=?, note=? WHERE id=?",
        (name, output_product_id, output_qty, note or None, formula_id)
    )
    conn.execute("DELETE FROM conversion_formula_inputs WHERE formula_id=?", (formula_id,))
    for inp in inputs:
        conn.execute(
            "INSERT INTO conversion_formula_inputs(formula_id, product_id, quantity) VALUES (?,?,?)",
            (formula_id, inp['product_id'], inp['quantity'])
        )
    conn.commit()
    conn.close()


def delete_conversion_formula(formula_id):
    conn = get_connection()
    conn.execute("DELETE FROM conversion_formula_inputs WHERE formula_id=?", (formula_id,))
    conn.execute("DELETE FROM conversion_formulas WHERE id=?", (formula_id,))
    conn.commit()
    conn.close()


def run_conversion(formula_id, multiplier, reference_no='', extra_note=''):
    conn = get_connection()
    formula = conn.execute("""
        SELECT cf.*, p.product_name AS output_product_name
          FROM conversion_formulas cf
          JOIN products p ON p.id = cf.output_product_id
         WHERE cf.id = ?
    """, (formula_id,)).fetchone()
    if not formula:
        conn.close()
        return False, 'ไม่พบสูตรการแปลง', {}

    inputs = conn.execute("""
        SELECT cfi.*, p.product_name, p.unit_type,
               COALESCE(sl.quantity, 0) AS current_stock
          FROM conversion_formula_inputs cfi
          JOIN products p ON p.id = cfi.product_id
          LEFT JOIN stock_levels sl ON sl.product_id = cfi.product_id
         WHERE cfi.formula_id = ?
    """, (formula_id,)).fetchall()

    shortage = []
    for inp in inputs:
        needed = inp['quantity'] * multiplier
        if inp['current_stock'] < needed:
            shortage.append(
                f'{inp["product_name"]}: ต้องการ {needed:,} แต่มีแค่ {inp["current_stock"]:,} {inp["unit_type"]}'
            )
    if shortage:
        conn.close()
        return False, 'สต็อกไม่พอ: ' + ' | '.join(shortage), {}

    note_text = f'แปลง: {formula["name"]}'
    if extra_note:
        note_text += f' | {extra_note}'

    for inp in inputs:
        needed = inp['quantity'] * multiplier
        conn.execute(
            "INSERT INTO transactions(product_id, txn_type, quantity_change, unit_mode, reference_no, note)"
            " VALUES (?,?,?,?,?,?)",
            (inp['product_id'], 'OUT', -needed, 'unit', reference_no or None, note_text)
        )

    output_qty = formula['output_qty'] * multiplier
    conn.execute(
        "INSERT INTO transactions(product_id, txn_type, quantity_change, unit_mode, reference_no, note)"
        " VALUES (?,?,?,?,?,?)",
        (formula['output_product_id'], 'IN', output_qty, 'unit', reference_no or None, note_text)
    )

    conn.commit()
    conn.close()
    return True, f'แปลงสำเร็จ: ได้ {output_qty:,} {formula["output_product_name"]}', {
        'output_qty': output_qty,
        'output_name': formula['output_product_name'],
    }


# ── Customer Master (BSN import) ───────────────────────────────────────────────

def import_customers_from_bsn(customers):
    conn = get_connection()
    inserted = updated = 0
    for c in customers:
        existing = conn.execute("SELECT code FROM customers WHERE code=?", (c['code'],)).fetchone()
        if existing:
            conn.execute("""
                UPDATE customers SET name=?, salesperson=?, zone=?, customer_type=?,
                    address=?, phone=?, tax_id=?, credit_days=?, contact=?,
                    imported_at=datetime('now','localtime')
                WHERE code=?
            """, (c['name'], c['salesperson'], c['zone'], c['customer_type'],
                  c['address'], c['phone'], c['tax_id'], c['credit_days'],
                  c['contact'], c['code']))
            updated += 1
        else:
            conn.execute("""
                INSERT INTO customers(code, name, salesperson, zone, customer_type,
                    address, phone, tax_id, credit_days, contact)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (c['code'], c['name'], c['salesperson'], c['zone'], c['customer_type'],
                  c['address'], c['phone'], c['tax_id'], c['credit_days'], c['contact']))
            inserted += 1
    conn.commit()
    conn.close()
    return inserted, updated


def get_customers_for_map(zone=None, customer_type=None, geocoded_only=False):
    conn = get_connection()
    conds = ['1=1']
    params = []
    if zone:
        conds.append('zone=?'); params.append(zone)
    if customer_type:
        conds.append('customer_type=?'); params.append(customer_type)
    if geocoded_only:
        conds.append('lat IS NOT NULL')
    where = ' AND '.join(conds)
    rows = conn.execute(
        f"SELECT * FROM customers WHERE {where} ORDER BY zone, code",
        params
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_customer_geocode(code, lat, lng):
    conn = get_connection()
    conn.execute(
        "UPDATE customers SET lat=?, lng=?, geocoded_at=datetime('now','localtime') WHERE code=?",
        (lat, lng, code)
    )
    conn.commit()
    conn.close()


def get_customer_zones():
    conn = get_connection()
    rows = conn.execute(
        "SELECT DISTINCT zone FROM customers WHERE zone IS NOT NULL ORDER BY zone"
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_customer_types():
    conn = get_connection()
    rows = conn.execute(
        "SELECT DISTINCT customer_type FROM customers WHERE customer_type IS NOT NULL ORDER BY customer_type"
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_geocode_progress():
    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
    geocoded = conn.execute("SELECT COUNT(*) FROM customers WHERE lat IS NOT NULL").fetchone()[0]
    conn.close()
    return total, geocoded


# ── Supplier List & Summary ───────────────────────────────────────────────────

def get_suppliers(search=None, page=1, per_page=50):
    conn = get_connection()
    conds = ["supplier IS NOT NULL AND supplier != ''"]
    params = []
    if search:
        conds.append("(supplier LIKE ? OR supplier_code LIKE ?)")
        params += [f"%{search}%", f"%{search}%"]
    where = "WHERE " + " AND ".join(conds)

    total = conn.execute(
        f"SELECT COUNT(DISTINCT supplier) FROM purchase_transactions {where}", params
    ).fetchone()[0]

    offset = (page - 1) * per_page
    rows = conn.execute(f"""
        SELECT supplier, supplier_code,
               COUNT(DISTINCT doc_no) AS doc_count,
               COALESCE(SUM(net), 0)  AS total_net,
               MAX(date_iso)          AS last_date
        FROM purchase_transactions
        {where}
        GROUP BY supplier, supplier_code
        ORDER BY total_net DESC
        LIMIT ? OFFSET ?
    """, params + [per_page, offset]).fetchall()

    conn.close()
    return [dict(r) for r in rows], total


def get_supplier_summary(supplier, date_from=None, date_to=None):
    conn = get_connection()
    conds = ['supplier = ?']
    params = [supplier]
    if date_from:
        conds.append('date_iso >= ?'); params.append(date_from)
    if date_to:
        conds.append('date_iso <= ?'); params.append(date_to)
    where = ' AND '.join(conds)

    summary = conn.execute(f"""
        SELECT COUNT(DISTINCT doc_no) AS doc_count,
               COALESCE(SUM(net), 0)  AS total_net,
               COALESCE(SUM(qty), 0)  AS total_qty,
               MIN(date_iso)          AS first_date,
               MAX(date_iso)          AS last_date
        FROM purchase_transactions
        WHERE {where}
    """, params).fetchone()

    top_products = conn.execute(f"""
        SELECT COALESCE(p.product_name, pt.product_name_raw) AS name,
               COALESCE(p.sku, 0) AS sku,
               p.id AS product_id,
               pt.unit,
               SUM(pt.qty)  AS total_qty,
               SUM(pt.net)  AS total_net,
               COUNT(DISTINCT pt.doc_no) AS doc_count
        FROM purchase_transactions pt
        LEFT JOIN products p ON p.id = pt.product_id
        WHERE {where}
        GROUP BY pt.product_id, pt.product_name_raw
        ORDER BY total_net DESC
        LIMIT 20
    """, params).fetchall()

    monthly = conn.execute(f"""
        SELECT strftime('%Y-%m', date_iso) AS month,
               COUNT(DISTINCT doc_no) AS doc_count,
               SUM(net) AS total_net
        FROM purchase_transactions
        WHERE {where}
        GROUP BY month
        ORDER BY month
    """, params).fetchall()

    docs = conn.execute(f"""
        SELECT date_iso, doc_no,
               COUNT(*) AS line_count,
               SUM(qty) AS total_qty,
               SUM(net) AS total_net
        FROM purchase_transactions
        WHERE {where}
        GROUP BY doc_no
        ORDER BY date_iso DESC, doc_no
        LIMIT 200
    """, params).fetchall()

    supplier_code = conn.execute(
        "SELECT supplier_code FROM purchase_transactions WHERE supplier=? LIMIT 1", [supplier]
    ).fetchone()

    conn.close()
    return {
        'supplier': supplier,
        'supplier_code': supplier_code['supplier_code'] if supplier_code else None,
        'date_from': date_from,
        'date_to': date_to,
        'summary': dict(summary),
        'top_products': [dict(r) for r in top_products],
        'monthly': [dict(r) for r in monthly],
        'docs': [dict(r) for r in docs],
    }
