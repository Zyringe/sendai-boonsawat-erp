"""
Parser for BSN weekly sales (ขาย) and purchase (ซื้อ) fixed-width report files.
Encoding: cp874  |  Lines are CSV-quoted  |  Non-breaking spaces (\xa0) used as padding
"""
import re


def _clean(line: str) -> str:
    return line.strip().strip('"').replace('\xa0', ' ')


def _be_to_iso(d: str) -> str:
    """DD/MM/YY Buddhist Era short year → YYYY-MM-DD Gregorian"""
    parts = d.strip().split('/')
    day, month, by = int(parts[0]), int(parts[1]), int(parts[2])
    return f"{(2500 + by) - 543:04d}-{month:02d}-{day:02d}"


# Sales doc no has embedded spaces: "IV6900478-  1"  → normalise to "IV6900478-1"
_TX_SALES = re.compile(
    r'(\d{2}/\d{2}/\d{2})\s+(\w+\-\s*\d+)\s+'          # date  doc_no
    r'([\d,]+\.?\d*)\s+(\S+)\s+'                         # qty  unit
    r'([\d,]+\.?\d*)\s+(\d)\s*'                          # unit_price  vat_type
    r'([\d+%]*)\s+([\d,]+\.?\d*)\s+'                     # discount  total
    r'[\d,]*\.?\d*\s+([\d,]+\.?\d*)'                     # ignored_col  net
)

# Purchase doc no is a single token: "HP6900017"
_TX_PURCH = re.compile(
    r'(\d{2}/\d{2}/\d{2})\s+(\S+)\s+'
    r'([\d,]+\.?\d*)\s+(\S+)\s+'
    r'([\d,]+\.?\d*)\s+(\d)\s*'
    r'([\d+%]*)\s+([\d,]+\.?\d*)\s+'
    r'[\d,]*\.?\d*\s+([\d,]+\.?\d*)'
)

_SKIP_PREFIXES = (
    '(BSN)', 'รายงาน', 'รหัส', 'วันที่', 'พนักงาน',
    'เลือก', 'สินค้า วัน', 'รวมตาม', '-----------', '===========',
)


def _is_skip(s: str) -> bool:
    return any(s.startswith(p) for p in _SKIP_PREFIXES) or \
           bool(re.match(r'^[-=\s]+$', s))


def parse_sales(filepath: str) -> list:
    return _parse(filepath, _TX_SALES, 'sales')


def parse_purchases(filepath: str) -> list:
    return _parse(filepath, _TX_PURCH, 'purchase')


def _parse(filepath: str, tx_pat, file_type: str) -> list:
    entries = []
    current_party = current_party_code = None
    current_prod_name = current_prod_code = None

    with open(filepath, encoding='cp874') as f:
        lines = [_clean(l) for l in f.readlines()]

    for line in lines:
        if not line.strip():
            continue
        stripped = line.strip()
        lead = len(line) - len(line.lstrip())

        if _is_skip(stripped):
            continue

        # Party line (customer / supplier): 2 leading spaces, has /code
        if lead == 2 and '/' in stripped and not stripped.startswith('รวม'):
            m = re.match(r'^(.+?)\s*/(\S+)\s*$', stripped)
            if m:
                current_party = m.group(1).strip()
                current_party_code = m.group(2).strip()
            continue

        # Product line: 3 leading spaces, has /code, not a total
        if lead == 3 and '/' in stripped and not stripped.startswith('รวม'):
            m = re.match(r'^(.+?)\s*/(\S+)\s*$', stripped)
            if m:
                current_prod_name = m.group(1).strip()
                current_prod_code = m.group(2).strip()
            continue

        # Transaction line: contains a date
        if re.search(r'\d{2}/\d{2}/\d{2}', line) and current_prod_name:
            m = tx_pat.search(line)
            if m:
                try:
                    entry = {
                        'date_iso':         _be_to_iso(m.group(1)),
                        'doc_no':           re.sub(r'\s+', '', m.group(2)),
                        'qty':              float(m.group(3).replace(',', '').replace('!', '')),
                        'unit':             m.group(4).replace('!', ''),
                        'unit_price':       float(m.group(5).replace(',', '')),
                        'vat_type':         int(m.group(6)),
                        'discount':         m.group(7).strip(),
                        'total':            float(m.group(8).replace(',', '')),
                        'net':              float(m.group(9).replace(',', '')),
                        'product_name_raw': current_prod_name,
                        'product_code_raw': current_prod_code,
                        'party':            current_party,
                        'party_code':       current_party_code,
                    }
                    entries.append(entry)
                except (ValueError, IndexError):
                    pass

    return entries


def detect_file_type(filepath: str) -> str:
    """Return 'sales' or 'purchase' based on file content."""
    with open(filepath, encoding='cp874') as f:
        for line in f:
            c = _clean(line)
            if 'ขาย' in c:
                return 'sales'
            if 'ซื้อ' in c:
                return 'purchase'
    return 'unknown'
