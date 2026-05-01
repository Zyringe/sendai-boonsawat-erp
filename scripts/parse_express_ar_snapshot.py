"""Parse Express ลูกหนี้คงค้างแบบละเอียด (AR outstanding snapshot).

The report groups outstanding invoices by customer (and by customer
type) — each customer has a `name /code` header, then per-invoice rows,
then a `รวมลูกค้า` subtotal. We flatten that into one row per
outstanding document, with the customer code/name carried as context.

Doc-no quirks observed in the source:
- `IV...`     normal invoice (still owed)
- `!RE...`    legacy "improper" receipts (old anomalies, mostly small)
- ` *** ` at row end = Express's own warning that the receipt amount
                       does not balance.

CLI:
    python scripts/parse_express_ar_snapshot.py PATH_TO_CSV [--json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path


# ── Date conversion (พ.ศ. → ค.ศ.) ─────────────────────────────────────────────
_DATE_RE = re.compile(r'^(\d{2})/(\d{2})/(\d{2})$')


def thai_date_to_iso(s):
    m = _DATE_RE.match(s.strip())
    if not m:
        return None
    dd, mm, yy = m.groups()
    year = 1957 + int(yy)
    return f'{year:04d}-{int(mm):02d}-{int(dd):02d}'


# ── Patterns ─────────────────────────────────────────────────────────────────
_SKIP_RE = re.compile(
    r'^\s*$'
    r'|^\(.*?\)บจก\.|^\s*\(BSN\)'
    r'|^\s*ลูกหนี้คงค้าง'
    r'|^\s*ณ\s+วันที่'
    r'|^\s*รหัสลูกค้า\s+ถึง'
    r'|^\s*ประเภทลูกค้าจาก'
    r'|^\s*พนักงานขาย\s+ถึง'
    r'|^\s*[-=_]{10,}'
    r'|^\s*วันที่\s+เอกสาร'
    r'|^\s*ตัดยอดโดย'
    r'|^\s*รวมลูกค้า'
    r'|^\s*รวมตามประเภทลูกค้า'
    r'|^\s*รวมทั้งสิ้น'
    r'|^\s*หมายเหตุ'
    r'|^\s*มีใบเสร็จบางใบ'
    r'|^\s*เพื่อให้พิมพ์'
    r'|^\s*เอกสารที่มี'
    r'|^>{3,}|^<{3,}'
    r'|^\s{20,}(?:RE|HP|PS|IV)\d+\s+\d{2}/\d{2}/\d{2}\s+[\d,.\-]+\s*$'  # ตัดยอดโดย sub-rows
)

# Customer-type group header: "  ประเภทลูกค้า : ลูกค้าประจำ" (also matches the empty-type header)
_TYPE_HDR_RE = re.compile(r'^\s*ประเภทลูกค้า\s*:\s*(?P<type>.*?)\s*$')

# Customer header: "    เจริญกิจ บางโพ /01จ06"  OR  "     /038ก01"
# Captures everything up to the trailing /code.
_CUSTOMER_HDR_RE = re.compile(r'^\s+(?P<name>(?:\S(?:.*?\S)?)?)\s*/(?P<code>\S+)\s*$')

# Detail row: date + (optional !) + doc_no + sp + 3 amounts + optional ***
# Doc-no usually `[A-Z]{2}\d+` (e.g. IV6900025) but Express also writes
# special tokens like `RE**NEW**` for legacy anomalies.
_DETAIL_RE = re.compile(
    r'^\s+(?P<date_thai>\d{2}/\d{2}/\d{2})\s+'
    r'(?P<flag>!?)(?P<doc_no>[A-Z]{2}[A-Z*\d]+)\s+'
    r'(?P<salesperson>\S+)\s+'
    r'(?P<bill>-?[\d,]+\.\d{2})\s+'
    r'(?P<paid>-?[\d,]+\.\d{2})\s+'
    r'(?P<outstanding>-?[\d,]+\.\d{2})'
    r'(?P<warn>\s+\*+)?\s*$'
)


# ── Data class ───────────────────────────────────────────────────────────────
@dataclass
class AROutstanding:
    customer_code: str
    customer_name: str
    customer_type: str
    doc_date_iso: str
    doc_no: str
    is_anomalous: bool
    salesperson_code: str
    bill_amount: float
    paid_amount: float
    outstanding_amount: float
    has_warning: bool


# ── Helpers ──────────────────────────────────────────────────────────────────
def _to_float(s):
    if s is None:
        return None
    s = s.replace(',', '').strip()
    try:
        return float(s)
    except (ValueError, AttributeError):
        return None


def _strip_quotes(line):
    line = line.rstrip('\r\n')
    if len(line) >= 2 and line[0] == '"' and line[-1] == '"':
        line = line[1:-1]
    return line.replace('""', '"')


# ── Parser ───────────────────────────────────────────────────────────────────
def parse_ar_snapshot(path):
    """Yield AROutstanding records from the Express AR snapshot file."""
    current_type = ''
    current_customer_code = ''
    current_customer_name = ''

    with open(path, 'r', encoding='cp874') as f:
        for raw in f:
            line = _strip_quotes(raw)

            if _SKIP_RE.match(line):
                continue

            m = _TYPE_HDR_RE.match(line)
            if m:
                current_type = m.group('type').strip()
                continue

            m = _DETAIL_RE.match(line)
            if m:
                yield AROutstanding(
                    customer_code=current_customer_code,
                    customer_name=current_customer_name,
                    customer_type=current_type,
                    doc_date_iso=thai_date_to_iso(m.group('date_thai')),
                    doc_no=m.group('doc_no'),
                    is_anomalous=m.group('flag') == '!',
                    salesperson_code=m.group('salesperson'),
                    bill_amount=_to_float(m.group('bill')) or 0.0,
                    paid_amount=_to_float(m.group('paid')) or 0.0,
                    outstanding_amount=_to_float(m.group('outstanding')) or 0.0,
                    has_warning=bool(m.group('warn')),
                )
                continue

            m = _CUSTOMER_HDR_RE.match(line)
            if m:
                current_customer_name = m.group('name').strip()
                current_customer_code = m.group('code').strip()
                continue

            print(f'[parser] skipped: {line!r}', file=sys.stderr)


# ── CLI ──────────────────────────────────────────────────────────────────────
def _summarise(records):
    n = len(records)
    customers = {r.customer_code for r in records if r.customer_code}
    n_anomalous = sum(1 for r in records if r.is_anomalous)
    n_warning = sum(1 for r in records if r.has_warning)
    total_outstanding = sum(r.outstanding_amount for r in records)
    print(f'Documents          : {n}')
    print(f'Distinct customers : {len(customers)}')
    print(f'Anomalous (! flag) : {n_anomalous}')
    print(f'Warning (***)      : {n_warning}')
    print(f'Total outstanding  : {total_outstanding:,.2f}')
    types = {}
    for r in records:
        types.setdefault(r.customer_type, []).append(r)
    print(f'Customer types     : {len(types)}')
    for t, rs in types.items():
        amt = sum(r.outstanding_amount for r in rs)
        print(f'  {t or "(none)":<20s}  n={len(rs):<4d}  amt={amt:>14,.2f}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('path', type=Path)
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--limit', type=int, default=None)
    args = ap.parse_args()

    records = list(parse_ar_snapshot(args.path))

    if args.json:
        slice_ = records[:args.limit] if args.limit else records
        out = [asdict(r) for r in slice_]
        json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
        return

    _summarise(records)


if __name__ == '__main__':
    main()
