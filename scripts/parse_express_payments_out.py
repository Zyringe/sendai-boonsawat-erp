"""Parse Express จ่ายชำระหนี้ (outgoing supplier-payment) report.

Same architecture as parse_express_payments_in: state-machine over a
fixed-width report with main rows + indented sub-rows + page breaks.

Differences from the incoming-payment parser:
- doc-no prefix is `PS` (Payment to Supplier) instead of `RE`.
- counterparty is supplier (no salesperson column).
- sub-rows reference goods-received vouchers (RR / HP / HS / GR), not
  customer invoices.
- the trailing free-text region carries bank / payer notes (e.g.
  "BBL ต๋อโอน", "สด", "พุธ392 โอน") rather than a structured cheque
  block in most rows. Cheque trailers (when present) follow the same
  template as the incoming-payment file.

CLI:
    python scripts/parse_express_payments_out.py PATH_TO_CSV [--json|--limit N]
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
    r'|^\s*วันที่จาก'
    r'|^\s*[-=_]{10,}'
    r'|^\s*วันที่จ่าย'                          # column header row 1
    r'|^\s*เลขที่ใบรับ\s+วันที่'                # column header row 2
    r'|^\s*รวมทั้งสิ้น\s+\d+\s+ใบ'
    r'|^หมายเหตุ:\s*$|^\s*ใบจ่ายเงินที่มี'
    r'|^>{3,}|^<{3,}'
)

# Main payment row header. Cheque trailer (if present) sits on the same
# physical line, separated by an embedded escaped quote — same trick as
# parse_express_payments_in.
_MAIN_HEAD_RE = re.compile(
    r'^\s*'
    r'(?P<void_pre>\*)?\s*'
    r'(?P<date_thai>\d{2}/\d{2}/\d{2})\s+'
    r'(?P<void_mid>\*)?\s*'
    r'(?P<doc_no>PS[A-Z0-9]{6,9})\s+'                  # allow legacy doc_no with embedded letters (PS0000E02)
    r'(?P<after_doc>.+?)\s{2,}'
    r'(?P<rest>-?[\d,]+\.\d{2}.*)$'
)

# Cheque trailer — same shape as in payments_in, kept independent in case
# the AP file wires it slightly differently later.
_CHEQUE_TRAILER_RE = re.compile(
    r'\b(?P<cheque_no>[A-Za-z0-9][A-Za-z0-9\-]{3,})\s+'
    r'(?P<cheque_date>\d{2}/\d{2}/\d{2})\s+'
    r'(?P<bank>\S+(?:\s\S+)?)\s+'
    r'(?P<cheque_amt>[\d,]+\.\d{2})\s+'
    r'(?P<cheque_status>\S.*?)\s*$'
)

# Sub-row: receive-voucher reference applied to this payment.
#   "                          RR6600291  01/08/66        40848                 3005.00"
#   "                          GR6600016  03/11/66                             -3253.75"
#   "                          RR6600423  15/11/66        1166/08734  V          308.16"
_SUBROW_RE = re.compile(
    r'^\s+'
    r'(?P<receive_doc>(?:RR|HP|HS|GR)\d{6,9})\s+'
    r'(?P<receive_date>\d{2}/\d{2}/\d{2})'
    r'(?P<middle>.*?)'                          # optional invoice_ref + V flag
    r'(?P<amount>-?[\d,]+\.\d{2})'
    r'(?P<trailer>\s+\S.*?)?\s*$'                # optional trailing memo (e.g. 'Vat รวม')
)


# ── Right-edge positions of money columns in the main row.
# Calibrated on real rows (slightly different from payments_in):
#   ยอดตามใบรับ end ~100
#   จ่ายเป็น ง/ส end ~115
#   เช็คจ่าย      end ~130 (estimated, between cash and interest)
#   ด/บ จ่าย     end ~140
#   ส่วนลด        end ~152
#   ภาษี          end ~164
_MONEY_COLUMN_ANCHORS = (
    ('deposit_applied',  85),
    ('invoice_amount',  100),
    ('cash_amount',     115),
    ('cheque_amount',   130),
    ('interest_amount', 140),
    ('discount_amount', 152),
    ('vat_amount',      164),
)


# ── Data classes ─────────────────────────────────────────────────────────────
@dataclass
class ReceiveRef:
    receive_doc: str
    receive_date_iso: str
    invoice_ref: str
    amount: float


@dataclass
class APPayment:
    doc_no: str
    date_iso: str
    supplier_name: str
    is_void: bool
    deposit_applied: float = 0.0
    invoice_amount: float = 0.0
    cash_amount: float = 0.0
    cheque_amount: float = 0.0
    interest_amount: float = 0.0
    discount_amount: float = 0.0
    vat_amount: float = 0.0
    cheque_no: str = ''
    cheque_date_iso: str = ''
    bank: str = ''
    cheque_status: str = ''
    note: str = ''
    receive_refs: list = field(default_factory=list)


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


def _split_money_tokens(rest, line_offset):
    out = {}
    for m in re.finditer(r'(?<!\S)(-?[\d,]+\.\d{2})(?!\S)', rest):
        end_pos = line_offset + m.end()
        token = m.group(1)
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


_NOTE_HDR_RE = re.compile(r'^\s+หมายเหตุ:\s*$')
_INFORMAL_INDENT_RE = re.compile(r'^\s{6,}\S')


# ── Parser ───────────────────────────────────────────────────────────────────
def parse_payments_out(path):
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

            m = _MAIN_HEAD_RE.match(line)
            if m:
                _flush_notes()
                if current is not None:
                    yield current
                # AP main rows have NO salesperson column — entire after_doc
                # is the supplier name.
                supplier = m.group('after_doc').rstrip()
                rest = m.group('rest') or ''
                rest_offset = m.start('rest')

                cheque = _CHEQUE_TRAILER_RE.search(rest)
                cheque_info = {}
                money_part = rest
                note_text = ''
                if cheque:
                    cheque_info = {
                        'cheque_no':       cheque.group('cheque_no'),
                        'cheque_date_iso': thai_date_to_iso(cheque.group('cheque_date')) or '',
                        'bank':            cheque.group('bank'),
                        'cheque_status':   cheque.group('cheque_status').strip().rstrip('"').strip(),
                    }
                    money_part = rest[:cheque.start()]
                else:
                    # Trailing free-text (e.g. "BBL ต๋อโอน", "สด", "พุธ392 โอน")
                    # appears after the last money token.
                    money_matches = list(re.finditer(r'-?[\d,]+\.\d{2}', rest))
                    if money_matches:
                        tail = rest[money_matches[-1].end():].strip()
                        # Any non-numeric tail is the note
                        if tail and not re.match(r'^[\d,.\-]+$', tail):
                            note_text = tail
                            money_part = rest[:money_matches[-1].end()]

                money_part = money_part.replace('"', ' ')
                money = _split_money_tokens(money_part, rest_offset)
                current = APPayment(
                    doc_no=m.group('doc_no'),
                    date_iso=thai_date_to_iso(m.group('date_thai')),
                    supplier_name=supplier,
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
                    note=note_text,
                )
                continue

            if _NOTE_HDR_RE.match(line):
                in_note_block = True
                note_lines = []
                continue

            if in_note_block:
                note_lines.append(line.strip())
                continue

            m = _SUBROW_RE.match(line)
            if m and current is not None:
                current.receive_refs.append(ReceiveRef(
                    receive_doc=m.group('receive_doc'),
                    receive_date_iso=thai_date_to_iso(m.group('receive_date')),
                    invoice_ref=(m.group('middle') or '').strip().rstrip('V').strip(),
                    amount=_to_float(m.group('amount')),
                ))
                continue

            if _INFORMAL_INDENT_RE.match(line) and current is not None:
                add = line.strip()
                current.note = (current.note + '\n' + add).strip() if current.note else add
                continue

            print(f'[parser] skipped: {line!r}', file=sys.stderr)

    _flush_notes()
    if current is not None:
        yield current


# ── CLI ──────────────────────────────────────────────────────────────────────
def _summarise(records):
    n = len(records)
    n_refs = sum(len(r.receive_refs) for r in records)
    sums = {
        'deposit_applied':  sum(r.deposit_applied for r in records),
        'invoice_amount':   sum(r.invoice_amount for r in records),
        'cash_amount':      sum(r.cash_amount for r in records),
        'cheque_amount':    sum(r.cheque_amount for r in records),
        'interest_amount':  sum(r.interest_amount for r in records),
        'discount_amount':  sum(r.discount_amount for r in records),
        'vat_amount':       sum(r.vat_amount for r in records),
    }
    cheque_n = sum(1 for r in records if r.cheque_amount > 0 or r.cheque_no)
    void = sum(1 for r in records if r.is_void)
    suppliers = sorted({r.supplier_name for r in records})
    print(f'Records           : {n}')
    print(f'Receive refs      : {n_refs}')
    print(f'Cheque payments   : {cheque_n}')
    print(f'Void              : {void}')
    print('Column sums (THB):')
    for k, v in sums.items():
        print(f'  {k:<16s} {v:>16,.2f}')
    print(f'Suppliers         : {len(suppliers)}')
    by_supplier = {}
    for r in records:
        by_supplier.setdefault(r.supplier_name, 0.0)
        by_supplier[r.supplier_name] += r.cash_amount + r.cheque_amount
    for s, amt in sorted(by_supplier.items(), key=lambda x: -x[1])[:10]:
        n_ = sum(1 for r in records if r.supplier_name == s)
        print(f'  {s:<32s} n={n_:<3d}  paid={amt:>14,.2f}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('path', type=Path)
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--limit', type=int, default=None)
    args = ap.parse_args()

    records = list(parse_payments_out(args.path))

    if args.json:
        slice_ = records[:args.limit] if args.limit else records
        out = [asdict(r) for r in slice_]
        json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
        return

    _summarise(records)


if __name__ == '__main__':
    main()
