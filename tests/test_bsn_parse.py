"""
Smoke tests for parse_weekly.py — the BSN cp874 parser.

Targets the real public API:
- parse_purchases(filepath) -> list of dicts
- parse_sales(filepath)     -> list of dicts
- _be_to_iso(d)             -> 'YYYY-MM-DD'  (พ.ศ. → ค.ศ.)
- detect_file_type(filepath)
"""
import parse_weekly


# ── _be_to_iso ───────────────────────────────────────────────────────────────

def test_be_to_iso_basic():
    # 04/04/69 (พ.ศ. 2569) → 2026-04-04
    assert parse_weekly._be_to_iso("04/04/69") == "2026-04-04"


def test_be_to_iso_2568():
    # 23/04/68 (พ.ศ. 2568) → 2025-04-23
    assert parse_weekly._be_to_iso("23/04/68") == "2025-04-23"


def test_be_to_iso_zero_padded():
    # Day/month already zero-padded in source — verify output is too
    assert parse_weekly._be_to_iso("01/01/69") == "2026-01-01"


# ── cp874 decoding ───────────────────────────────────────────────────────────

def test_cp874_decoding_thai_chars(sample_purchase_file):
    """Reading via cp874 should produce real Thai characters (not mojibake)."""
    with open(sample_purchase_file, encoding="cp874") as f:
        text = f.read()
    # If decoding were wrong, we'd see latin-1-style garbage instead of these.
    assert "รายงานประวัติการซื้อ" in text
    assert "บจก.บุญสวัสดิ์นำชัย" in text


# ── parse_purchases ──────────────────────────────────────────────────────────

def test_parse_purchases_extracts_required_columns(sample_purchase_file):
    entries = parse_weekly.parse_purchases(sample_purchase_file)
    assert len(entries) >= 1
    e = entries[0]

    # Every entry must carry these fields with the right types.
    required = {
        'date_iso', 'doc_no', 'qty', 'unit', 'unit_price',
        'vat_type', 'discount', 'total', 'net',
        'product_name_raw', 'product_code_raw', 'party', 'party_code',
    }
    assert required.issubset(e.keys())

    # First row of synthesized sample is HP6900023 / Pกล่อง3 / 22965 กล @ 0.69, vat=0
    assert e['date_iso']         == "2026-04-24"
    assert e['doc_no']           == "HP6900023"
    assert e['qty']              == 22965.0
    assert e['unit']             == "กล"
    assert e['unit_price']       == 0.69
    assert e['vat_type']         == 0
    assert e['net']              == 15845.85
    assert e['product_code_raw'] == "Pกล่อง3"
    assert e['party_code']       == "ย้ง"


def test_parse_purchases_be_year_2568(sample_purchase_file):
    """Second purchase row uses 23/04/68 (พ.ศ. 2568) → must yield 2025."""
    entries = parse_weekly.parse_purchases(sample_purchase_file)
    dates = [e['date_iso'] for e in entries]
    assert "2025-04-23" in dates


# ── parse_sales ──────────────────────────────────────────────────────────────

def test_parse_sales_doc_no_normalised(sample_sales_file):
    """Sales doc_no like 'IV6900503-  1' must collapse internal whitespace."""
    entries = parse_weekly.parse_sales(sample_sales_file)
    assert len(entries) >= 1
    doc_nos = [e['doc_no'] for e in entries]
    # Embedded spaces stripped: "IV6900503-  1" → "IV6900503-1"
    assert "IV6900503-1" in doc_nos
    assert "IV6900501-1" in doc_nos


def test_parse_sales_vat_type_parsed(sample_sales_file):
    entries = parse_weekly.parse_sales(sample_sales_file)
    by_doc = {e['doc_no']: e for e in entries}
    # IV6900503-1 has vat_type=1, IV6900501-1 has vat_type=2 in the sample
    assert by_doc["IV6900503-1"]['vat_type'] == 1
    assert by_doc["IV6900501-1"]['vat_type'] == 2


def test_parse_sales_carries_party_and_product_context(sample_sales_file):
    entries = parse_weekly.parse_sales(sample_sales_file)
    by_doc = {e['doc_no']: e for e in entries}

    e1 = by_doc["IV6900503-1"]
    assert e1['party_code'] == "01พ02"
    assert e1['product_code_raw'] == "031บ4120"

    e2 = by_doc["IV6900501-1"]
    assert e2['party_code'] == "01อ35"
    assert e2['product_code_raw'] == "001ก3435"


def test_parse_sales_decimal_baht_discount(sample_sales_file):
    """BSN sometimes emits line discount as decimal baht (e.g. '32.00') instead of percent.
    Old regex misaligned columns: total absorbed the discount, leaving the real total in
    the ignored column. This test guards against that regression."""
    entries = parse_weekly.parse_sales(sample_sales_file)
    by_doc = {e['doc_no']: e for e in entries}

    e = by_doc["IV6900498-2"]
    assert e['unit_price'] == 50.00
    assert e['discount']   == "32.00"
    assert e['total']      == 18.00
    assert e['net']        == 18.00


def test_parse_sales_doc_level_discount_percent(sample_sales_file):
    """Doc-level discount column ('ส่วนลดรวม') uses percent format like '2%'.
    Old regex captured only '2' (digit before %) as net, dropping the real net entirely.
    For IV6900370-2 the real net is 1728.72 (= 1764 × 0.98), not 2."""
    entries = parse_weekly.parse_sales(sample_sales_file)
    by_doc = {e['doc_no']: e for e in entries}

    e = by_doc["IV6900370-2"]
    assert e['discount'] == "10%"
    assert e['total']    == 1764.00
    assert e['net']      == 1728.72


def test_parse_sales_qty_unit_bang_separator(sample_sales_file):
    """BSN occasionally glues qty and unit with '!' instead of whitespace (e.g. '2.00!หล').
    Old regex used \\s+ between qty and unit groups, so the whole row failed to match and
    was silently dropped. ~137 such rows existed in the 2024-2026 sales export. The fix
    extends the qty/unit separator to allow '!' and strips it from captured groups."""
    entries = parse_weekly.parse_sales(sample_sales_file)
    by_doc = {e['doc_no']: e for e in entries}

    e = by_doc["IV6801044-4"]
    assert e['qty']        == 2.00
    assert e['unit']       == "หล"
    assert e['unit_price'] == 1317.79
    assert e['vat_type']   == 2
    assert e['discount']   == "10%"
    assert e['total']      == 2372.02
    assert e['net']        == 2372.02


# ── detect_file_type ─────────────────────────────────────────────────────────

def test_detect_file_type_purchase(sample_purchase_file):
    assert parse_weekly.detect_file_type(sample_purchase_file) == "purchase"


def test_detect_file_type_sales(sample_sales_file):
    assert parse_weekly.detect_file_type(sample_sales_file) == "sales"
