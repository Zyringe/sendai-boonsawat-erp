"""Parse Express การรับชำระหนี้ (incoming payment) report.

This is the file commission calculation hangs on: every receipt has the
salesperson code (`02`, `06-L`, ...) attached, and we use that to know
"which salesperson collected which money".

Format quirks compared to ใบลดหนี้:
  - Multi-line records are common: one main RE row + N invoice IV sub-rows
    + optional หมายเหตุ block.
  - When the receipt was paid by cheque, Express tacks the cheque-info
    columns (cheque_no, cheque_date, bank, amount, status) onto the SAME
    physical line as the main row, separated by an embedded quote.

CLI:
    python scripts/parse_express_payments_in.py PATH_TO_CSV [--json | --limit N]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path


# ── Date conversion (พ.ศ. → ค.ศ.) ─────────────────────────────────────────────
_DATE_RE = re.compile(r'^(\d{2})/(\d{2})/(\d{2})$')


def thai_date_to_iso(s):
    """'17/01/67' (BE 2567) → '2024-01-17'. None on bad input."""
    m = _DATE_RE.match(s.strip())
    if not m:
        return None
    dd, mm, yy = m.groups()
    year = 1957 + int(yy)
    return f'{year:04d}-{int(mm):02d}-{int(dd):02d}'


# ── Line classifiers ─────────────────────────────────────────────────────────
_SKIP_RE = re.compile(
    r'^\s*$'
    r'|^\(.*?\)บจก\.|^\s*\(BSN\)'
    r'|^\s*รายงาน'
    r'|^\s*วันที่จาก'
    r'|^\s*พนักงานขาย\s+ถึง'
    r'|^\s*[-=_]{10,}'
    r'|^\s+[-=_]{5,}\s+[-=_]{5,}'
    r'|^\s*วันที่\s+เลขที่ใบเสร็จ'           # column header
    r'|^\s*รวม\s+\*+\s+ใบ'                # final summary row
    r'|^\s*ใบเสร็จที่มีเครื่องหมาย'         # legend rows
    r'|^>{3,}|^<{3,}'
)

# Main receipt row. Optional cheque-trailer on the same physical line.
# Examples (after _strip_quotes):
#   "03/01/67  RE6700001  สหภัณฑ์เคหะกิจ (V)  06   7524.99   7524.99"
#   "03/01/67  RE6700003  บุญเลิศ  02   58111.68  58111.00   0.68"
#   "09/01/67  RE6700009  ฐานิตก่อสร้าง  02  6278.14   6278.14\"   QR13220394  05/01/67  BBL  6278.14 เช็คในมือ"
_MAIN_RE = re.compile(
    r'^\s*'
    r'(?P<void_pre>\*)?\s*'                            # void marker before date (rare)
    r'(?P<date_thai>\d{2}/\d{2}/\d{2})\s+'
    r'(?P<void_mid>\*)?\s*'                            # void marker before doc_no (Express style)
    r'(?P<doc_no>RE\d{6,9})\s+'
    r'(?P<customer>\S(?:.*?\S)?)\s{2,}'
    r'(?P<salesperson>\S+)'
    r'(?P<rest>.*?)\s*$'
)

# Cheque-trailer pattern (search within the right-hand portion of a main row).
#   QR13220394   05/01/67  BBL          6278.14 เช็คในมือ
# Sometimes the cheque_no may not start with QR — accept any non-space token.
_CHEQUE_TRAILER_RE = re.compile(
    r'\b(?P<cheque_no>[A-Za-z0-9][A-Za-z0-9\-]{3,})\s+'
    r'(?P<cheque_date>\d{2}/\d{2}/\d{2})\s+'
    r'(?P<bank>\S+(?:\s\S+)?)\s+'           # bank can have Thai chars or short space (e.g. 'ธกส', 'LH BAN')
    r'(?P<cheque_amt>[\d,]+\.\d{2})\s+'
    r'(?P<cheque_status>\S.*?)\s*$'
)

# Invoice sub-row. e.g.
#   "                             IV6601903    10/08/66          3145.61"
_INVOICE_RE = re.compile(
    r'^\s+'
    r'(?P<invoice_no>(?:IV|HS|SR|HP)\d{6,9})\s+'
    r'(?P<invoice_date>\d{2}/\d{2}/\d{2})\s+'
    r'(?P<amount>[\d,]+\.\d{2})\s*$'
)

_NOTE_HDR_RE = re.compile(r'^\s+หมายเหตุ:\s*$')
_INFORMAL_INDENT_RE = re.compile(r'^\s{6,}\S')


# ── Data classes ─────────────────────────────────────────────────────────────
@dataclass
class InvoiceRef:
    invoice_no: str
    invoice_date_iso: str
    amount: float


@dataclass
class Payment:
    doc_no: str
    date_iso: str
    customer_name: str
    salesperson_code: str
    is_void: bool
    # Money breakdown — column order from Express header:
    # ตัดเงินมัดจำ / ยอดตามใบกำกับ / ชำระเป็น ง/ส / เช็ครับ / ด/บ รับ / ส่วนลด / ภาษี
    deposit_applied: float = 0.0
    invoice_amount: float = 0.0
    cash_amount: float = 0.0
    cheque_amount: float = 0.0
    interest_amount: float = 0.0
    discount_amount: float = 0.0
    vat_amount: float = 0.0
    # Cheque trailer (optional)
    cheque_no: str = ''
    cheque_date_iso: str = ''
    bank: str = ''
    cheque_status: str = ''
    # Notes / refs
    note: str = ''
    invoice_refs: list = field(default_factory=list)


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
    # Express CSV-escapes embedded quotes as ""
    return line.replace('""', '"')


# Right-edge positions of each money column, calibrated from real rows.
# Position math counts characters (not bytes); Thai chars are 1 char each.
#   ยอดตามใบกำกับ end ~104   (e.g. '7524.99' at 97-104)
#   ชำระเป็น ง/ส  end ~119   (cash, e.g. '7524.99' at 112-119)
#   เช็ครับ        end ~134   (cheque, e.g. '6278.14' at 127-134)
#   ด/บ รับ        end ~144   (interest, very rare)
#   ส่วนลด          end ~156   (e.g. '0.68' at 152-156)
#   ภาษี            end ~168
#   ตัดเงินมัดจำ   end ~88    (deposit, very rare — never seen filled in samples)
_MONEY_COLUMN_ANCHORS = (
    ('deposit_applied',  88),
    ('invoice_amount',  104),
    ('cash_amount',     119),
    ('cheque_amount',   134),
    ('interest_amount', 144),
    ('discount_amount', 156),
    ('vat_amount',      168),
)


def _split_money_tokens(rest, line_offset):
    """Yield (column_name, value) pairs by mapping numeric tokens to nearest column anchor.

    rest        — substring AFTER the salesperson token
    line_offset — character position where `rest` starts in the original line
    """
    out = {}
    for m in re.finditer(r'(?<!\S)([\d,]+\.\d{2})(?!\S)', rest):
        end_pos = line_offset + m.end()
        token = m.group(1)
        # find nearest anchor not yet filled
        best = None
        best_dist = 10**9
        for name, anchor in _MONEY_COLUMN_ANCHORS:
            if name in out:
                continue
            dist = abs(end_pos - anchor)
            if dist < best_dist:
                best_dist = dist
                best = name
        if best is not None:
            out[best] = _to_float(token)
    return out


# ── Parser ───────────────────────────────────────────────────────────────────
def parse_payments_in(path):
    """Yield Payment objects from Express การรับชำระหนี้ report."""
    current = None
    in_note_block = False
    note_lines = []

    def _flush_notes():
        nonlocal in_note_block, note_lines
        if in_note_block and current is not None and note_lines:
            existing = current.note
            joined = '\n'.join(note_lines).strip()
            current.note = (existing + '\n' + joined).strip() if existing else joined
        in_note_block = False
        note_lines = []

    with open(path, 'r', encoding='cp874') as f:
        for raw in f:
            line = _strip_quotes(raw)

            if not line.strip():
                _flush_notes()
                continue

            if _SKIP_RE.match(line):
                _flush_notes()
                continue

            m = _MAIN_RE.match(line)
            if m:
                _flush_notes()
                if current is not None:
                    yield current
                rest = m.group('rest') or ''
                rest_offset = m.start('rest')
                # Try to peel off cheque trailer first
                cheque = _CHEQUE_TRAILER_RE.search(rest)
                cheque_info = {}
                money_part = rest
                if cheque:
                    cheque_info = {
                        'cheque_no':       cheque.group('cheque_no'),
                        'cheque_date_iso': thai_date_to_iso(cheque.group('cheque_date')) or '',
                        'bank':            cheque.group('bank'),
                        'cheque_status':   cheque.group('cheque_status').strip().rstrip('"').strip(),
                    }
                    money_part = rest[:cheque.start()]
                # Strip lone trailing/embedded quote artefacts in the money region
                money_part = money_part.replace('"', ' ')
                money = _split_money_tokens(money_part, rest_offset)
                current = Payment(
                    doc_no=m.group('doc_no'),
                    date_iso=thai_date_to_iso(m.group('date_thai')),
                    customer_name=m.group('customer').strip(),
                    salesperson_code=m.group('salesperson').strip(),
                    is_void=bool(m.group('void_pre') or m.group('void_mid')),
                    deposit_applied=money.get('deposit_applied', 0.0) or 0.0,
                    invoice_amount=money.get('invoice_amount', 0.0) or 0.0,
                    cash_amount=money.get('cash_amount', 0.0) or 0.0,
                    cheque_amount=money.get('cheque_amount', 0.0) or 0.0,
                    interest_amount=money.get('interest_amount', 0.0) or 0.0,
                    discount_amount=money.get('discount_amount', 0.0) or 0.0,
                    vat_amount=money.get('vat_amount', 0.0) or 0.0,
                    cheque_no=cheque_info.get('cheque_no', ''),
                    cheque_date_iso=cheque_info.get('cheque_date_iso', ''),
                    bank=cheque_info.get('bank', ''),
                    cheque_status=cheque_info.get('cheque_status', ''),
                )
                continue

            if _NOTE_HDR_RE.match(line):
                in_note_block = True
                note_lines = []
                continue

            if in_note_block:
                note_lines.append(line.strip())
                continue

            m = _INVOICE_RE.match(line)
            if m and current is not None:
                current.invoice_refs.append(InvoiceRef(
                    invoice_no=m.group('invoice_no'),
                    invoice_date_iso=thai_date_to_iso(m.group('invoice_date')),
                    amount=_to_float(m.group('amount')),
                ))
                continue

            if _INFORMAL_INDENT_RE.match(line) and current is not None:
                # Treat as note continuation
                add = line.strip()
                current.note = (current.note + '\n' + add).strip() if current.note else add
                continue

            print(f'[parser] skipped unrecognised line: {line!r}', file=sys.stderr)

    _flush_notes()
    if current is not None:
        yield current


# ── CLI ──────────────────────────────────────────────────────────────────────
def _summarise(records):
    n = len(records)
    n_inv = sum(len(r.invoice_refs) for r in records)
    sums = {
        'deposit_applied':  sum(r.deposit_applied  for r in records),
        'invoice_amount':   sum(r.invoice_amount   for r in records),
        'cash_amount':      sum(r.cash_amount      for r in records),
        'cheque_amount':    sum(r.cheque_amount    for r in records),
        'interest_amount':  sum(r.interest_amount  for r in records),
        'discount_amount':  sum(r.discount_amount  for r in records),
        'vat_amount':       sum(r.vat_amount       for r in records),
    }
    cheque_n = sum(1 for r in records if r.cheque_amount > 0 or r.cheque_no)
    void = sum(1 for r in records if r.is_void)
    sps = sorted({r.salesperson_code for r in records})
    print(f'Records           : {n}')
    print(f'Invoice refs      : {n_inv}')
    print(f'Cheque receipts   : {cheque_n}')
    print(f'Void              : {void}')
    print('Column sums (THB):')
    for k, v in sums.items():
        print(f'  {k:<16s} {v:>16,.2f}')
    print(f'Salespersons      : {len(sps)}')
    for sp in sps:
        cnt = sum(1 for r in records if r.salesperson_code == sp)
        amt = sum(r.cash_amount + r.cheque_amount for r in records if r.salesperson_code == sp)
        print(f'  {sp:<8s} n={cnt:<5d}  collected={amt:>14,.2f}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('path', type=Path)
    ap.add_argument('--json', action='store_true', help='emit JSON')
    ap.add_argument('--limit', type=int, default=None)
    args = ap.parse_args()

    records = list(parse_payments_in(args.path))

    if args.json:
        slice_ = records[:args.limit] if args.limit else records
        out = [asdict(r) for r in slice_]
        json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
        return

    _summarise(records)


if __name__ == '__main__':
    main()
