"""Mobile-first flows blueprint (Phase 4 of mobile-friendly project).

Routes under /m are intentionally narrow, thumb-friendly, and one-task-per-screen.
They co-exist with the full responsive routes (e.g. /products) — bottom nav points
the most frequent mobile tasks here. Desktop users typically don't visit /m/* but
the routes work there too.
"""
from flask import Blueprint, render_template, request, jsonify, abort

import models
from database import get_connection

bp_mobile = Blueprint('mobile', __name__, url_prefix='/m',
                      template_folder='../templates/m')


# ── Stock check (live search) ─────────────────────────────────────────────────

@bp_mobile.route('/stock')
def stock_search():
    """Render the search page. Empty initial state; results come from
    /m/stock/api as the user types."""
    return render_template('m/stock.html')


@bp_mobile.route('/stock/api')
def stock_search_api():
    """JSON live-search across products. Returns name/sku/qty/price/unit so
    the card list can render without further fetches."""
    q = (request.args.get('q') or '').strip()
    if len(q) < 1:
        return jsonify({'items': []})
    pat_starts = f'{q}%'
    pat_anywhere = f'%{q}%'
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT p.id, p.sku, p.product_name, p.unit_type, p.base_sell_price,
               COALESCE(sl.quantity, 0) AS qty,
               p.low_stock_threshold,
               (SELECT floor_no FROM product_locations
                  WHERE product_id = p.id ORDER BY id LIMIT 1) AS location
          FROM products p
     LEFT JOIN stock_levels sl ON sl.product_id = p.id
         WHERE p.is_active = 1
           AND (p.product_name LIKE :anywhere
                OR CAST(p.sku AS TEXT) LIKE :anywhere
                OR EXISTS (SELECT 1 FROM product_barcodes pb
                            WHERE pb.product_id = p.id AND pb.barcode LIKE :anywhere))
         ORDER BY
             CASE WHEN CAST(p.sku AS TEXT) = :exact THEN 0
                  WHEN p.product_name LIKE :starts THEN 1
                  ELSE 2 END,
             p.product_name
         LIMIT 30
        """,
        {'anywhere': pat_anywhere, 'starts': pat_starts, 'exact': q}
    ).fetchall()
    conn.close()
    items = [
        {
            'id':       r['id'],
            'sku':      r['sku'],
            'name':     r['product_name'],
            'unit':     r['unit_type'],
            'price':    r['base_sell_price'] or 0,
            'qty':      r['qty'],
            'low':      (r['qty'] or 0) <= (r['low_stock_threshold'] or 0),
            'location': r['location'] or '',
        }
        for r in rows
    ]
    return jsonify({'items': items, 'q': q})


# ── Customer detail (mobile) ──────────────────────────────────────────────────

@bp_mobile.route('/customer/<path:customer_name>')
def customer_detail(customer_name):
    """Mobile-optimised customer card: header + contact + outstanding + last bills/sales."""
    conn = get_connection()
    # Customer master row (joined via name; existing schema keys customers by code
    # but invoices reference name, so we look up via name to match).
    customer = conn.execute(
        "SELECT * FROM customers WHERE name = ? LIMIT 1", (customer_name,)
    ).fetchone()

    # Region / salesperson (separate table for editable region label)
    region_row = None
    if customer:
        region_row = conn.execute(
            "SELECT region, salesperson FROM customer_regions WHERE customer_code = ?",
            (customer['code'],),
        ).fetchone()

    conn.close()
    # Use existing model fn — handles VAT, SR/HS doc filtering, paid-status correctly
    unpaid_full = models.get_customer_unpaid_bills(customer_name)
    unpaid = unpaid_full[:5]
    unpaid_total = sum((b['total_net'] or 0) for b in unpaid_full)
    conn = get_connection()

    # Last 5 sales docs (any status) — quick reference of recent activity
    last_sales = conn.execute(
        """
        SELECT date_iso, doc_no, ROUND(SUM(net), 2) AS total, COUNT(*) AS lines
          FROM sales_transactions
         WHERE customer = ?
         GROUP BY doc_no
         ORDER BY date_iso DESC
         LIMIT 5
        """,
        (customer_name,),
    ).fetchall()

    # Aggregate stats
    stats = conn.execute(
        """
        SELECT COUNT(DISTINCT doc_no) AS doc_count,
               ROUND(SUM(net), 2) AS total_net,
               MIN(date_iso) AS first_seen,
               MAX(date_iso) AS last_seen
          FROM sales_transactions WHERE customer = ?
        """,
        (customer_name,),
    ).fetchone()

    conn.close()
    return render_template(
        'm/customer.html',
        customer_name=customer_name,
        customer=customer,
        region=region_row,
        unpaid=unpaid,
        unpaid_total=unpaid_total,
        last_sales=last_sales,
        stats=stats,
    )


# ── Sales trip (zone-grouped) ─────────────────────────────────────────────────

@bp_mobile.route('/sales-trip')
def sales_trip():
    """Customers grouped by region → quick view for sales-rep field trip planning."""
    region_filter = (request.args.get('region') or '').strip() or None

    conn = get_connection()
    # All known regions (for filter chips)
    all_regions = [r['region'] for r in conn.execute(
        "SELECT DISTINCT region FROM customer_regions WHERE region IS NOT NULL ORDER BY region"
    ).fetchall()]

    # Customers + outstanding total + last sale, optionally filtered by region
    # Outstanding = sum(net) of sales rows whose doc_base has no paid_invoice match.
    # (paid_invoices.iv_no joins to sales_transactions.doc_base; SR/HS docs are
    # credit notes and historic which we exclude — same rule as models.get_customer_unpaid_bills.)
    sql = """
        SELECT c.code, c.name, c.zone, c.phone, c.address,
               cr.region, cr.salesperson,
               (SELECT MAX(date_iso) FROM sales_transactions s WHERE s.customer = c.name) AS last_sale,
               (SELECT ROUND(SUM(CASE WHEN s.vat_type = 2 THEN s.net * 1.07 ELSE s.net END), 2)
                  FROM sales_transactions s
                  LEFT JOIN paid_invoices pi ON pi.iv_no = s.doc_base
                  WHERE s.customer = c.name
                    AND s.doc_base IS NOT NULL
                    AND s.doc_base NOT LIKE 'SR%'
                    AND s.doc_base NOT LIKE 'HS%'
                    AND pi.iv_no IS NULL
               ) AS outstanding
          FROM customers c
     LEFT JOIN customer_regions cr ON cr.customer_code = c.code
    """
    params = []
    if region_filter:
        sql += " WHERE cr.region = ? "
        params.append(region_filter)
    sql += """
         ORDER BY COALESCE(cr.region, 'zzz'), c.name
         LIMIT 300
    """
    rows = conn.execute(sql, params).fetchall()
    conn.close()

    # Group by region in Python (cheaper than fancy SQL here)
    grouped = {}
    total_outstanding = 0.0
    for r in rows:
        key = r['region'] or '— ไม่ระบุเขต —'
        grouped.setdefault(key, []).append(r)
        if r['outstanding']:
            total_outstanding += r['outstanding']

    return render_template('m/sales_trip.html',
                           grouped=grouped,
                           all_regions=all_regions,
                           region_filter=region_filter,
                           total_outstanding=total_outstanding)
