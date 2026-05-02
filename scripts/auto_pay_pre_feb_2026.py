"""One-shot: mark every commission earned BEFORE 2026-02 as already paid.

Per Put 2026-05-02: "commission ที่จ่ายแล้วที่เป็นเลขที่เอกสารตั้งแต่ก่อน
เดือน 2 ปี 69 ให้ถือว่าจ่ายแล้วทั้งหมด".

For every (salesperson, year_month) where year_month < 2026-02:
  - Walk every invoice the engine attributes to that sp + month
  - If commission_due > 0 and remaining > 0 (= unpaid), insert one
    payout row per invoice with the full remaining amount.

Idempotent: if the script is rerun, the engine will report
remaining=0 for already-paid invoices and skip them.

Marker: paid_method='auto', note='pre-Feb 2026 auto-paid', paid_by=
'system', paid_date='2026-02-01'.
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / 'inventory_app'))

import sqlite3
import commission

DB = '/Users/putty/Documents/Sendai-Boonsawat/sendy_erp/inventory_app/instance/inventory.db'
CUTOFF_MONTH = '2026-02'   # all months strictly LESS than this auto-paid

PAID_DATE = '2026-02-01'
PAID_METHOD = 'auto'
NOTE = 'pre-Feb 2026 auto-paid'
PAID_BY = 'system'


def _list_months_before(cutoff):
    conn = sqlite3.connect(DB)
    rows = conn.execute("""
        SELECT DISTINCT substr(date_iso, 1, 7) AS ym
          FROM express_payments_in
         WHERE is_void = 0 AND substr(date_iso, 1, 7) < ?
         ORDER BY ym
    """, (cutoff,)).fetchall()
    conn.close()
    return [r[0] for r in rows]


def _list_salespersons():
    conn = sqlite3.connect(DB)
    rows = conn.execute("""
        SELECT DISTINCT salesperson_code FROM express_payments_in
         WHERE is_void = 0 AND salesperson_code <> ''
    """).fetchall()
    conn.close()
    return [r[0] for r in rows]


def main():
    months = _list_months_before(CUTOFF_MONTH)
    sps = _list_salespersons()
    print(f'Cutoff: {CUTOFF_MONTH}  ({len(months)} months × {len(sps)} sps)')

    inserted = 0
    skipped = 0
    total_amount = 0.0

    for ym in months:
        for sp in sps:
            invs = commission.get_invoice_commission_for_sp(ym, sp)
            for inv in invs:
                if inv['remaining'] <= 0.005:
                    skipped += 1
                    continue
                commission.record_payout(
                    year_month=ym,
                    salesperson_code=sp,
                    amount_paid=inv['remaining'],
                    paid_date=PAID_DATE,
                    paid_method=PAID_METHOD,
                    note=NOTE,
                    paid_by=PAID_BY,
                    invoice_no=inv['invoice_no'],
                )
                inserted += 1
                total_amount += inv['remaining']
        if inserted and inserted % 200 == 0:
            print(f'  ... {ym} → inserted {inserted} so far (฿{total_amount:,.2f})')

    print(f'\nDone:')
    print(f'  inserted     : {inserted}')
    print(f'  skipped      : {skipped} (already paid)')
    print(f'  total amount : ฿{total_amount:,.2f}')


if __name__ == '__main__':
    main()
