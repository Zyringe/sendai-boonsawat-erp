"""Parse Express ขาย (sales-history-by-customer) report.

Hierarchical layout — three indentation levels nest a sales line item
inside its product, inside its customer:

    customer-name /customer-code             # 2-space indent
       product-name /product-code            # 3-space indent
          DD/MM/YY  IV.....-  N  qty unit ... # 6-space indent (sales row)
          ...
          รวมตาม ใบกำกับ                       # invoice subtotal (skip)
       รวม customer-code                      # customer total (skip)

Each emitted record is one sales line item carrying the surrounding
customer + product context.

CLI:
    python scripts/parse_express_sales.py PATH_TO_CSV [--json|--limit N]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path


# ── Date conversion ──────────────────────────────────────────────────────────
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
    r'|^\s*รายงาน'
    r'|^\s*รหัสลูกค้า'
    r'|^\s*วันที่จาก'
    r'|^\s*รหัสสินค้า'
    r'|^\s*พนักงานขาย'
    r'|^\s*[-=_]{10,}'
    r'|^\s*สินค้า\s+วันที่\s+เลขที่เอกสาร'
    r'|^\s+รวมตาม\s+ใบกำกับ'
    r'|^\s+รวมตาม\s+ใบลดหนี้'
    r'|^\s+รวมตาม\s+บิลเงินสด'                  # cash-invoice subtotal
    r'|^\s+รวม\s+\S+\s+\d'                     # customer-total: "รวม 01ก11   60.00 ใบ ..."
    r'|^\s+รวมทั้งสิ้น'
    r'|^หมายเหตุ:|^\s*รายการขาย|^\s*\!\s+อยู่หน้า'
    r'|^>{3,}|^<{3,}'
)

# Header rows that end with " /<code>" — both customer and product use this format.
# We disambiguate by indent: 2-3 spaces = customer; 3+ spaces with the line
# already-having-customer = product. Indent thresholds taken from real data.
_HDR_RE = re.compile(r'^(?P<indent>\s+)(?P<name>\S(?:.*?\S)?)\s+/(?P<code>\S+)\s*$')

# Sales line item.
# Examples:
#   "      04/07/68   IV6801757-  1        50.00 ใบ          149.54  2                  7477.00                  7477.00"
#   "      08/03/67   IV6700610-  1       100.00 กล            8.00  1         5%        760.00                   760.00 SO0007002-  1"
#   "      04/07/68   IV6801757-  2        10.00 ใบ            0.00  2                     0.00                     0.00               ***"
#   "      10/05/68   SR6700135-  1         1.00 อน Y        150.00  1      26.00        124.00                   124.00 IV6801171-  1"
_SALE_RE = re.compile(
    r'^\s{4,}'
    r'(?P<date_thai>\d{2}/\d{2}/\d{2})\s+'
    r'(?P<doc_no>(?:IV|SR|HS|HP)\d{6,9})-\s*'
    r'(?P<line_no>\d+)\s+'
    r'(?P<qty>-?[\d,]+\.\d{2})'
    r'(?P<unit_flag>!?)\s*'                                # non-standard unit ratio marker
    r'(?P<unit>\S+)\s+'
    r'(?:(?P<return_flag>[YN])\s+)?'                       # rare 'Y' before unit_price (return rows)
    r'(?P<unit_price>-?[\d,]+\.\d{2})\s+'
    r'(?P<vat_type>\d+)'
    r'(?P<rest>.*)$'
)


# ── Data class ───────────────────────────────────────────────────────────────
@dataclass
class SaleLine:
    customer_code: str
    customer_name: str
    product_code: str
    product_name: str
    date_iso: str
    doc_no: str
    line_no: int
    qty: float
    unit: str
    return_flag: str
    unit_price: float
    vat_type: int
    discount: str
    total: float
    total_discount: float
    net: float
    ref_doc: str
    is_warning: bool


# ── Helpers ──────────────────────────────────────────────────────────────────
def _to_float(s):
    if s is None:
        return None
    s = s.replace(',', '').strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _strip_quotes(line):
    line = line.rstrip('\r\n')
    if len(line) >= 2 and line[0] == '"' and line[-1] == '"':
        line = line[1:-1]
    return line.replace('""', '"')


# Right-edge positions (in the full line) of the four trailing money columns.
# Calibrated on real rows:
#   ส่วนลด          end ~78  (numeric discount column; '%' strings live here too)
#   รวมเงิน          end ~90
#   ส่วนลดรวม       end ~105
#   ยอดขายสุทธิ      end ~115
_TAIL_ANCHORS = (
    ('discount_num',    78),
    ('total',           90),
    ('total_discount', 105),
    ('net',            115),
)


def _parse_sale_tail(rest, rest_offset):
    """Extract (discount_str, total, total_discount, net, ref_doc, is_warning).

    rest_offset is the character position in the full line where `rest`
    starts — used to map money tokens back to their column anchors.
    """
    is_warning = False
    if rest.rstrip().endswith('***'):
        is_warning = True
        rest = rest.rstrip()[:-3]

    ref_doc = ''
    ref_match = re.search(r'\b((?:SO|IV|HS|HP|SR)\d{6,9}-\s*\d+)\s*$', rest)
    if ref_match:
        ref_doc = re.sub(r'-\s+', '-', ref_match.group(1))
        rest = rest[:ref_match.start()]

    discount_str = ''
    by_col = {}

    for m in re.finditer(r'(?<!\S)(-?[\d,]+\.\d{2}|\d+(?:\+\d+)?%|\d+\.\d+%)(?!\S)', rest):
        token = m.group(1)
        end_pos = rest_offset + m.end()
        is_pct = token.endswith('%')

        if is_pct:
            discount_str = token  # always the discount column
            continue

        # Map numeric token to nearest column anchor not already filled
        best = None
        best_dist = 10**9
        for name, anchor in _TAIL_ANCHORS:
            if name in by_col:
                continue
            dist = abs(end_pos - anchor)
            if dist < best_dist:
                best_dist = dist
                best = name
        if best is not None:
            by_col[best] = _to_float(token)

    if 'discount_num' in by_col and not discount_str:
        d = by_col['discount_num']
        discount_str = f'{d:.2f}' if d is not None else ''

    total = by_col.get('total')
    total_discount = by_col.get('total_discount')
    net = by_col.get('net')

    # Some single-token rows park the value at the net column only — copy to
    # total so the row contributes to grand sum consistently.
    if total is None and net is not None:
        total = net

    return discount_str, total, total_discount, net, ref_doc, is_warning


# ── Parser ───────────────────────────────────────────────────────────────────
# Indent thresholds. Customer headers sit at indent exactly 2; product
# headers sit at indent 3 (one deeper). Anything else is treated as
# product (defensive — we'd rather attach to the wrong product than to
# the wrong customer).
_CUSTOMER_INDENT_MAX = 2


def parse_sales(path):
    """Yield SaleLine records from Express ขาย report."""
    cur_customer_code = ''
    cur_customer_name = ''
    cur_product_code = ''
    cur_product_name = ''
    customer_indent = -1

    with open(path, 'r', encoding='cp874') as f:
        for raw in f:
            line = _strip_quotes(raw)

            if _SKIP_RE.match(line):
                continue

            m = _SALE_RE.match(line)
            if m:
                rest = m.group('rest') or ''
                rest_offset = m.start('rest')
                discount_str, total, td, net, ref_doc, is_warn = _parse_sale_tail(rest, rest_offset)
                yield SaleLine(
                    customer_code=cur_customer_code,
                    customer_name=cur_customer_name,
                    product_code=cur_product_code,
                    product_name=cur_product_name,
                    date_iso=thai_date_to_iso(m.group('date_thai')),
                    doc_no=m.group('doc_no'),
                    line_no=int(m.group('line_no')),
                    qty=_to_float(m.group('qty')),
                    unit=m.group('unit'),
                    return_flag=m.group('return_flag') or '',
                    unit_price=_to_float(m.group('unit_price')),
                    vat_type=int(m.group('vat_type')),
                    discount=discount_str,
                    total=total or 0.0,
                    total_discount=td or 0.0,
                    net=net or 0.0,
                    ref_doc=ref_doc,
                    is_warning=is_warn,
                )
                continue

            m = _HDR_RE.match(line)
            if m:
                indent = len(m.group('indent'))
                name = m.group('name').strip()
                code = m.group('code').strip()
                if indent <= _CUSTOMER_INDENT_MAX:
                    cur_customer_code = code
                    cur_customer_name = name
                    customer_indent = indent
                    cur_product_code = ''
                    cur_product_name = ''
                else:
                    cur_product_code = code
                    cur_product_name = name
                continue

            print(f'[parser] skipped: {line!r}', file=sys.stderr)


# ── CLI ──────────────────────────────────────────────────────────────────────
def _summarise(records):
    n = len(records)
    customers = {r.customer_code for r in records if r.customer_code}
    products = {r.product_code for r in records if r.product_code}
    docs = {r.doc_no for r in records}
    by_doc_type = {}
    for r in records:
        prefix = re.match(r'[A-Z]+', r.doc_no).group()
        by_doc_type.setdefault(prefix, []).append(r)

    iv_t = sum(r.total for r in by_doc_type.get('IV', []))
    iv_n = sum(r.net for r in by_doc_type.get('IV', []))
    hs_t = sum(r.total for r in by_doc_type.get('HS', []))
    hs_n = sum(r.net for r in by_doc_type.get('HS', []))
    sr_t = sum(r.total for r in by_doc_type.get('SR', []))
    sr_n = sum(r.net for r in by_doc_type.get('SR', []))
    grand_t = iv_t + hs_t - sr_t
    grand_n = iv_n + hs_n - sr_n

    print(f'Sale lines        : {n}')
    print(f'Distinct docs     : {len(docs)}')
    print(f'Distinct customers: {len(customers)}')
    print(f'Distinct products : {len(products)}')
    print('Doc-type breakdown:')
    for k, rs in by_doc_type.items():
        print(f'  {k:<4s}  n={len(rs):<6d}  total={sum(r.total for r in rs):>14,.2f}  net={sum(r.net for r in rs):>14,.2f}')
    print()
    print(f'Grand total (IV+HS-SR) : {grand_t:>16,.2f}    ← matches Express รวมทั้งสิ้น')
    print(f'Grand net   (IV+HS-SR) : {grand_n:>16,.2f}    ← matches Express net total')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('path', type=Path)
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--limit', type=int, default=None)
    args = ap.parse_args()

    records = list(parse_sales(args.path))

    if args.json:
        slice_ = records[:args.limit] if args.limit else records
        out = [asdict(r) for r in slice_]
        json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
        return

    _summarise(records)


if __name__ == '__main__':
    main()
