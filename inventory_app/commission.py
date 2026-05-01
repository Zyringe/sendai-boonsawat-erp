"""Commission engine — computes per-salesperson commission for a given month.

Inputs (read from DB):
  express_payments_in     — receipts that arrived in the target month
  express_payment_in_invoice_refs — links receipt → invoice (IV doc_no)
  express_sales           — line items per invoice (carries product_name)
  commission_tiers        — rate definitions (own/third + threshold)
  commission_assignments  — which tier each salesperson uses

Algorithm:
  1. For target year_month, load receipts (excluding void) joined to their
     invoice refs and on to express_sales lines that share doc_no.
  2. Each sales line is classified as own-brand or third-party from its
     product_name (regex similar to migration 004 brand backfill).
  3. Aggregate net amount by (salesperson_code, brand_kind).
  4. Apply tier rules:
       - No threshold → commission = own × rate_own + third × rate_third
       - With threshold (Tier B):
           below = min(total, threshold) × below-rate (5% flat)
           above_excess = max(total - threshold, 0)
           own_share / third_share = proportional to own/third totals
           above = own_share × above_rate_own + third_share × above_rate_third

Output: list of dicts per salesperson with total / own / third splits and
commission breakdown so the dashboard can show "below + above" detail.

Real-time: NO snapshot table — query runs on demand.
"""
from __future__ import annotations

import os
import re
import sqlite3
from collections import defaultdict


_DB_PATH = os.environ.get(
    'SENDY_DB_PATH',
    '/Users/putty/Documents/Sendai-Boonsawat/sendy_erp/inventory_app/instance/inventory.db',
)


# ── Brand classifier ────────────────────────────────────────────────────────
# Used as fallback when express_sales.brand_kind is NULL — for example a
# brand-new product imported after the brand_map was last refreshed. The
# canonical source is product_brand_map (loaded from brand.csv) plus the
# brand_kind column it backfills onto express_sales.
_OWN_BRAND_RE = re.compile(
    r'(?:Sendai|SENDAI|\bSD\b|\bS/D\b|S\.D\.|'
    r'สิงห์|Golden\s*Lion|GOLDEN\s*LION|GOLDENLION|GL-|'
    r'A-?SPEC|ASPEC)',
    re.IGNORECASE,
)


def classify_brand_kind(product_name):
    """Return 'own' or 'third_party' from product_name keyword regex."""
    if product_name and _OWN_BRAND_RE.search(product_name):
        return 'own'
    return 'third_party'


# ── DB helpers ──────────────────────────────────────────────────────────────
def _connect(db_path=None):
    conn = sqlite3.connect(db_path or _DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = OFF')
    return conn


def _load_tiers(conn):
    """Load tiers indexed by salesperson_code."""
    rows = conn.execute("""
        SELECT a.salesperson_code,
               t.code              AS tier_code,
               t.name_th           AS tier_name,
               t.rate_own_pct,
               t.rate_third_pct,
               t.threshold_amount,
               t.above_rate_own_pct,
               t.above_rate_third_pct
          FROM commission_assignments a
          JOIN commission_tiers t ON t.id = a.tier_id
    """).fetchall()
    return {r['salesperson_code']: dict(r) for r in rows}


# ── Core query: per-line attribution of receipts ─────────────────────────────
# For each (paid receipt, invoice ref, sales line of that invoice) we get the
# salesperson_code from the receipt and the product_name from the line. Net
# attributed = sales-line.net allocated within the matching invoice.
#
# Strategy: split the receipt's allocated invoice payment proportional to the
# sales lines' net for that invoice. This way commission base = net actually
# collected per product (subset of total invoice if partially paid).
_BASE_QUERY = """
    SELECT pin.salesperson_code,
           pin.doc_no            AS receipt_no,
           pin.date_iso          AS receipt_date,
           pin.customer_name     AS customer_name,
           ref.invoice_no,
           ref.amount            AS ref_amount,
           es.product_code,
           es.product_name_raw,
           es.brand_kind         AS brand_kind,
           es.net                AS line_net,
           es.total              AS line_total,
           es.qty                AS qty
      FROM express_payments_in    pin
      JOIN express_payment_in_invoice_refs ref ON ref.payment_in_id = pin.id
      JOIN express_sales          es  ON es.doc_no = ref.invoice_no
     WHERE pin.is_void = 0
       AND pin.date_iso BETWEEN ? AND ?
       AND pin.salesperson_code <> ''
"""


def _month_bounds(year_month):
    """Return (start_iso, end_iso) for a YYYY-MM string."""
    y, m = year_month.split('-')
    y, m = int(y), int(m)
    start = f'{y:04d}-{m:02d}-01'
    if m == 12:
        end = f'{y + 1:04d}-01-01'
    else:
        end = f'{y:04d}-{m + 1:02d}-01'
    # Use exclusive end-date trick: BETWEEN ? AND ? with end-1day
    # But date_iso is YYYY-MM-DD; SQLite string BETWEEN works lexicographically.
    last_day = f'{y:04d}-{m:02d}-31'
    return start, last_day


def get_commission_for_month(year_month, salesperson_code=None, db_path=None):
    """Compute commission for a given YYYY-MM.

    Returns list of dicts (one per salesperson with activity), sorted by
    salesperson_code. Each dict has:
        salesperson_code, tier_code, tier_name,
        own_net, third_net, total_net,
        threshold_amount,
        commission_below, commission_above_own, commission_above_third,
        total_commission,
        receipts_count, invoices_seen, lines_attributed
    """
    conn = _connect(db_path)
    tiers = _load_tiers(conn)
    start, end = _month_bounds(year_month)

    rows = conn.execute(_BASE_QUERY, (start, end)).fetchall()
    if salesperson_code:
        rows = [r for r in rows if r['salesperson_code'] == salesperson_code]

    # Aggregate net per (sp, brand_kind, invoice). Per-invoice grouping is
    # needed so that the monthly base-commission total matches the sum of
    # per-invoice rounded commissions (otherwise rounding accumulates and
    # the dashboard "remaining" shows ±0.02 even when every invoice has
    # been paid in full).
    own = defaultdict(float)
    third = defaultdict(float)
    own_inv = defaultdict(lambda: defaultdict(float))     # own_inv[sp][invoice_no]
    third_inv = defaultdict(lambda: defaultdict(float))
    receipts = defaultdict(set)
    invoices = defaultdict(set)
    line_count = defaultdict(int)

    for r in rows:
        sp = r['salesperson_code']
        inv_no = r['invoice_no']
        kind = r['brand_kind'] or classify_brand_kind(r['product_name_raw'] or '')
        net = r['line_net'] or 0.0
        if kind == 'own':
            own[sp] += net
            own_inv[sp][inv_no] += net
        else:
            third[sp] += net
            third_inv[sp][inv_no] += net
        receipts[sp].add(r['receipt_no'])
        invoices[sp].add(inv_no)
        line_count[sp] += 1

    # Compute commission per salesperson
    out = []
    sps = sorted(set(own) | set(third))
    for sp in sps:
        tier = tiers.get(sp)
        own_net = round(own[sp], 2)
        third_net = round(third[sp], 2)
        total_net = round(own_net + third_net, 2)

        if tier is None:
            tier_code = '?'
            tier_name = '(no assignment)'
            commission_below = commission_above_own = commission_above_third = 0.0
            threshold = None
        else:
            tier_code = tier['tier_code']
            tier_name = tier['tier_name']
            threshold = tier['threshold_amount']
            r_own = tier['rate_own_pct'] / 100.0
            r_third = tier['rate_third_pct'] / 100.0

            # Per-invoice base commission — sum of (own_inv × r_own +
            # third_inv × r_third) rounded each. This is the canonical
            # base value: it always equals what the user pays when ticking
            # every invoice on the drill-down.
            invoice_keys = set(own_inv[sp].keys()) | set(third_inv[sp].keys())
            base_per_invoice = 0.0
            for inv_key in invoice_keys:
                base_per_invoice += round(
                    own_inv[sp][inv_key] * r_own + third_inv[sp][inv_key] * r_third, 2,
                )

            if threshold is None or total_net <= threshold or threshold == 0:
                commission_below = round(base_per_invoice, 2)
                commission_above_own = 0.0
                commission_above_third = 0.0
            else:
                # Tier B threshold breach: base_per_invoice covers the
                # below+above as if everything used the BASE rates;
                # we add the difference (above-portion bonus) on top.
                excess = total_net - threshold
                own_share = own_net / total_net if total_net else 0.0
                third_share = third_net / total_net if total_net else 0.0
                ar_own = (tier['above_rate_own_pct'] or 0) / 100.0
                ar_third = (tier['above_rate_third_pct'] or 0) / 100.0
                # bonus = above-rate − base-rate, applied to the excess portion
                bonus_own = excess * own_share * (ar_own - r_own)
                bonus_third = excess * third_share * (ar_third - r_third)
                commission_below = round(base_per_invoice, 2)
                commission_above_own = round(max(bonus_own, 0), 2)
                commission_above_third = round(max(bonus_third, 0), 2)

        total_commission = round(
            commission_below + commission_above_own + commission_above_third, 2,
        )

        out.append({
            'salesperson_code': sp,
            'tier_code': tier_code,
            'tier_name': tier_name,
            'own_net': own_net,
            'third_net': third_net,
            'total_net': total_net,
            'threshold_amount': threshold,
            'commission_below': commission_below,
            'commission_above_own': commission_above_own,
            'commission_above_third': commission_above_third,
            'total_commission': total_commission,
            'receipts_count': len(receipts[sp]),
            'invoices_seen': len(invoices[sp]),
            'lines_attributed': line_count[sp],
        })

    conn.close()
    return out


# ── Payouts ─────────────────────────────────────────────────────────────────
def get_payouts_for_month(year_month, db_path=None):
    """Map of {salesperson_code: total_paid_amount} for the given month."""
    conn = _connect(db_path)
    rows = conn.execute("""
        SELECT salesperson_code, ROUND(SUM(amount_paid), 2) AS paid
          FROM commission_payouts
         WHERE year_month = ?
         GROUP BY salesperson_code
    """, (year_month,)).fetchall()
    conn.close()
    return {r['salesperson_code']: r['paid'] for r in rows}


def get_invoice_payouts_for_sp(year_month, salesperson_code, db_path=None):
    """Map of {invoice_no: total_paid_amount} for one salesperson in a month.

    Sum of all commission_payouts rows that carry invoice_no for this
    (sp, month). Rows without invoice_no (legacy month-level payouts) are
    NOT included here — those are handled separately at the month level.
    """
    conn = _connect(db_path)
    rows = conn.execute("""
        SELECT invoice_no, ROUND(SUM(amount_paid), 2) AS paid
          FROM commission_payouts
         WHERE year_month = ?
           AND salesperson_code = ?
           AND invoice_no IS NOT NULL
         GROUP BY invoice_no
    """, (year_month, salesperson_code)).fetchall()
    conn.close()
    return {r['invoice_no']: r['paid'] for r in rows}


def get_payout_history(year_month=None, salesperson_code=None, db_path=None):
    """Return raw commission_payouts rows, sorted newest-first."""
    conn = _connect(db_path)
    where = []
    params = []
    if year_month:
        where.append('year_month = ?')
        params.append(year_month)
    if salesperson_code:
        where.append('salesperson_code = ?')
        params.append(salesperson_code)
    where_sql = ('WHERE ' + ' AND '.join(where)) if where else ''
    rows = conn.execute(f"""
        SELECT id, year_month, salesperson_code, amount_paid,
               paid_date, paid_method, note, paid_by, created_at
          FROM commission_payouts
          {where_sql}
         ORDER BY paid_date DESC, id DESC
    """, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def record_payout(year_month, salesperson_code, amount_paid,
                  paid_date, paid_method='', note='', paid_by='',
                  invoice_no=None, db_path=None):
    """Insert one commission_payouts row. Returns the new row id."""
    conn = _connect(db_path)
    cur = conn.execute("""
        INSERT INTO commission_payouts
            (year_month, salesperson_code, amount_paid, paid_date,
             paid_method, note, paid_by, invoice_no)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (year_month, salesperson_code, amount_paid, paid_date,
          paid_method or None, note or None, paid_by or None, invoice_no))
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def delete_payout(payout_id, db_path=None):
    conn = _connect(db_path)
    conn.execute('DELETE FROM commission_payouts WHERE id = ?', (payout_id,))
    conn.commit()
    conn.close()


# ── All-invoices view (paid + unpaid) for one salesperson ───────────────────
def get_invoices_for_salesperson(year_month, salesperson_code, db_path=None):
    """Return invoices issued in target month "owned by" this salesperson.

    Ownership = the receipt that paid this invoice was collected by sp,
                OR the open AR row tagged to sp.
    Each row carries paid_status: 'paid' / 'unpaid' / 'partial'.
    """
    conn = _connect(db_path)
    start, end = _month_bounds(year_month)

    # Aggregate sales lines per invoice in target month
    invoice_rows = conn.execute("""
        SELECT s.doc_no,
               s.doc_type,
               s.date_iso,
               s.customer_code,
               s.customer_name,
               ROUND(SUM(s.net), 2)   AS total_net,
               ROUND(SUM(s.total), 2) AS total_gross,
               COUNT(*)               AS lines
          FROM express_sales s
         WHERE s.date_iso BETWEEN ? AND ?
           AND s.doc_type IN ('IV','HS')
         GROUP BY s.doc_no
    """, (start, end)).fetchall()

    # Map invoice_no → who paid it (receipt collector)
    paid_by_sp = {r['invoice_no']: (r['salesperson_code'], r['receipt_no'], r['amount'])
                  for r in conn.execute("""
        SELECT ref.invoice_no, pin.salesperson_code, pin.doc_no AS receipt_no, ref.amount
          FROM express_payment_in_invoice_refs ref
          JOIN express_payments_in pin ON pin.id = ref.payment_in_id
         WHERE pin.is_void = 0
    """).fetchall()}

    # Map invoice_no → outstanding info (currently unpaid)
    open_ar = {r['doc_no']: dict(r) for r in conn.execute("""
        SELECT doc_no, salesperson_code, outstanding_amount
          FROM express_ar_outstanding
         WHERE snapshot_date_iso = (SELECT MAX(snapshot_date_iso) FROM express_ar_outstanding)
    """).fetchall()}

    out = []
    for r in invoice_rows:
        inv = r['doc_no']
        owning_sp = ''
        paid_status = 'paid'  # default — paid in full; reduce if AR open
        receipt_no = ''
        outstanding = 0.0

        if inv in paid_by_sp:
            owning_sp, receipt_no, _ = paid_by_sp[inv]
        if inv in open_ar:
            outstanding = open_ar[inv]['outstanding_amount'] or 0
            if not owning_sp:
                owning_sp = open_ar[inv]['salesperson_code'] or ''
            if outstanding >= (r['total_net'] or 0) * 0.99:
                paid_status = 'unpaid'
            elif outstanding > 0:
                paid_status = 'partial'

        if not owning_sp:
            # Fall back to customer's salesperson if known
            cust_sp = conn.execute(
                'SELECT salesperson FROM customers WHERE code = ?',
                (r['customer_code'] or '',)
            ).fetchone()
            if cust_sp and cust_sp['salesperson']:
                owning_sp = cust_sp['salesperson']

        if owning_sp != salesperson_code:
            continue

        out.append({
            'doc_no': inv,
            'doc_type': r['doc_type'],
            'date_iso': r['date_iso'],
            'customer_code': r['customer_code'],
            'customer_name': r['customer_name'],
            'total_net': r['total_net'] or 0.0,
            'total_gross': r['total_gross'] or 0.0,
            'lines': r['lines'],
            'paid_status': paid_status,
            'outstanding_amount': outstanding,
            'receipt_no': receipt_no,
        })

    conn.close()
    out.sort(key=lambda r: (r['date_iso'] or '', r['doc_no']), reverse=True)
    return out


def get_invoice_line_breakdown(year_month, salesperson_code, invoice_no, db_path=None):
    """Per-line breakdown for one invoice — used by the invoice drill-down
    "see exactly which product earned which %" view.

    Returns list of dicts with:
        product_code, product_name_raw, qty, unit, line_net,
        brand_kind, rate_pct, commission, sendy_product_id
    plus a header dict describing the invoice + tier rate context.
    """
    conn = _connect(db_path)
    # NB: do NOT filter express_sales by month — the invoice doc_no is
    # globally unique, and an invoice paid in month X may have been
    # issued months earlier. The receipt's date is the month-bound
    # axis; the invoice's lines are wherever they live in time.
    # Look up Sendy product_id via product_code_mapping (BSN/Express share
    # the same product code system — 99.9% of Express codes are already
    # mapped). Falls back to NULL only for genuinely unmapped codes.
    rows = conn.execute("""
        SELECT es.product_code,
               es.product_name_raw,
               es.qty,
               es.unit,
               es.unit_price,
               es.net               AS line_net,
               es.brand_kind,
               m.product_id         AS sendy_product_id
          FROM express_sales es
          LEFT JOIN product_code_mapping m ON m.bsn_code = es.product_code
         WHERE es.doc_no = ?
         ORDER BY es.line_no
    """, (invoice_no,)).fetchall()

    # Tier rates
    tier = conn.execute("""
        SELECT t.code AS tier_code, t.rate_own_pct, t.rate_third_pct,
               t.threshold_amount, t.above_rate_own_pct, t.above_rate_third_pct
          FROM commission_assignments a
          JOIN commission_tiers t ON t.id = a.tier_id
         WHERE a.salesperson_code = ?
    """, (salesperson_code,)).fetchone()

    # Receipt info
    rcpt = conn.execute("""
        SELECT pin.doc_no, pin.date_iso, pin.customer_name, pin.cash_amount,
               pin.cheque_amount, pin.discount_amount
          FROM express_payment_in_invoice_refs ref
          JOIN express_payments_in pin ON pin.id = ref.payment_in_id
         WHERE pin.salesperson_code = ? AND ref.invoice_no = ?
         LIMIT 1
    """, (salesperson_code, invoice_no)).fetchone()

    if tier:
        rate_own = tier['rate_own_pct'] or 0
        rate_third = tier['rate_third_pct'] or 0
        tier_code = tier['tier_code']
    else:
        rate_own = rate_third = 0
        tier_code = '?'

    out_rows = []
    for r in rows:
        kind = r['brand_kind'] or classify_brand_kind(r['product_name_raw'] or '')
        rate_pct = rate_own if kind == 'own' else rate_third
        commission = round((r['line_net'] or 0) * rate_pct / 100.0, 2)
        out_rows.append({
            'product_code':     r['product_code'],
            'product_name_raw': r['product_name_raw'],
            'qty':              r['qty'],
            'unit':             r['unit'],
            'unit_price':       r['unit_price'],
            'line_net':         r['line_net'],
            'brand_kind':       kind,
            'rate_pct':         rate_pct,
            'commission':       commission,
            'sendy_product_id': r['sendy_product_id'],
        })

    header = {
        'invoice_no': invoice_no,
        'tier_code': tier_code,
        'rate_own_pct': rate_own,
        'rate_third_pct': rate_third,
        'receipt_no':   rcpt['doc_no'] if rcpt else '',
        'receipt_date': rcpt['date_iso'] if rcpt else '',
        'customer_name': rcpt['customer_name'] if rcpt else '',
        'total_net':    round(sum((r['line_net'] or 0) for r in out_rows), 2),
        'total_commission': round(sum(r['commission'] for r in out_rows), 2),
    }
    conn.close()
    return header, out_rows


def get_invoice_commission_for_sp(year_month, salesperson_code, db_path=None):
    """Per-invoice commission for one salesperson in a month.

    For each invoice the salesperson collected this month:
        commission_due  = own_net × tier.rate_own_pct + third_net × tier.rate_third_pct
        (BASE rates only — Tier B's above-threshold bonus is handled at
         month level, not allocated per invoice.)

    Returns list of dicts sorted by date desc:
      invoice_no, invoice_date, receipt_no, receipt_date, customer_name,
      own_net, third_net, total_net,
      commission_due, paid_amount, remaining, paid_status
    """
    lines = get_lines_for_salesperson(year_month, salesperson_code, db_path)

    # Group by invoice_no, aggregating own/third nets
    inv = {}
    for ln in lines:
        v = inv.setdefault(ln['invoice_no'], {
            'invoice_no':   ln['invoice_no'],
            'invoice_date': '',          # filled below
            'receipt_no':   ln['receipt_no'],
            'receipt_date': ln['receipt_date'],
            'customer_name': ln['customer_name'],
            'own_net':      0.0,
            'third_net':    0.0,
        })
        if ln['brand_kind'] == 'own':
            v['own_net'] += ln['line_net'] or 0
        else:
            v['third_net'] += ln['line_net'] or 0

    # Fetch invoice issue dates from express_sales (any line of the invoice carries date_iso)
    if inv:
        conn = _connect(db_path)
        placeholders = ','.join('?' * len(inv))
        date_rows = conn.execute(f"""
            SELECT doc_no, MIN(date_iso) AS d
              FROM express_sales
             WHERE doc_no IN ({placeholders})
             GROUP BY doc_no
        """, list(inv.keys())).fetchall()
        for r in date_rows:
            if r['doc_no'] in inv:
                inv[r['doc_no']]['invoice_date'] = r['d']
        conn.close()

    # Tier rates (use base rates for per-invoice — bonus handled at month level)
    conn = _connect(db_path)
    tier_rates = conn.execute("""
        SELECT t.rate_own_pct, t.rate_third_pct, t.threshold_amount,
               t.above_rate_own_pct, t.above_rate_third_pct
          FROM commission_assignments a
          JOIN commission_tiers t ON t.id = a.tier_id
         WHERE a.salesperson_code = ?
    """, (salesperson_code,)).fetchone()
    if tier_rates:
        rate_own = (tier_rates['rate_own_pct'] or 0) / 100.0
        rate_third = (tier_rates['rate_third_pct'] or 0) / 100.0
    else:
        rate_own = rate_third = 0.0
    conn.close()

    paid_map = get_invoice_payouts_for_sp(year_month, salesperson_code, db_path)

    out = []
    for v in inv.values():
        commission_due = round(v['own_net'] * rate_own + v['third_net'] * rate_third, 2)
        total_net = round(v['own_net'] + v['third_net'], 2)
        paid = paid_map.get(v['invoice_no'], 0.0)
        remaining = round(commission_due - paid, 2)
        if commission_due == 0:
            status = 'no_rate'
        elif paid >= commission_due - 0.01:
            status = 'paid'
        elif paid > 0:
            status = 'partial'
        else:
            status = 'pending'
        out.append({
            **v,
            'own_net':        round(v['own_net'], 2),
            'third_net':      round(v['third_net'], 2),
            'total_net':      total_net,
            'commission_due': commission_due,
            'paid_amount':    paid,
            'remaining':      remaining,
            'paid_status':    status,
        })
    out.sort(key=lambda r: (r['receipt_date'] or '', r['invoice_no']), reverse=True)
    return out


def get_lines_for_salesperson(year_month, salesperson_code, db_path=None):
    """Return per-line detail for one salesperson in a month.

    Each row represents one (receipt, invoice, sales-line) tuple — useful
    for the drill-down "what invoices is this salesperson getting paid
    on?" view. Sorted by invoice date desc, then invoice doc_no.
    """
    conn = _connect(db_path)
    start, end = _month_bounds(year_month)
    rows = conn.execute(_BASE_QUERY + " AND pin.salesperson_code = ?",
                        (start, end, salesperson_code)).fetchall()
    out = [dict(r) for r in rows]
    # Resolve fallback brand_kind for any NULL rows so the template doesn't
    # have to handle Nones.
    for r in out:
        if not r['brand_kind']:
            r['brand_kind'] = classify_brand_kind(r['product_name_raw'] or '')
    out.sort(key=lambda r: (r['receipt_date'] or '', r['invoice_no']), reverse=True)
    conn.close()
    return out
