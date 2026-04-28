"""
Tests for parse_weekly.parse_credit_notes — Express ใบลดหนี้ (SR) parser.

Source format reference: /Volumes/ZYRINGE/express_data/ใบลดหนี้-27.4.69.csv (cp874).
Two-tier hierarchy: master (1 line) + 0..N detail lines. Each detail row → one entry.
"""
import pytest

import parse_weekly


# ── Synthesized cp874 sample ─────────────────────────────────────────────────

# Mirrors the real format observed in the source file. Lines are CSV-quoted,
# encoded cp874, use \xa0 as in-line padding. Designed to cover:
#   - basic single-detail master
#   - cancelled (*SR…) master
#   - salesperson with hyphen suffix ("06-L")
#   - multi-detail master (3 details under one SR)
#   - master with no details (placeholder emit)
#   - detail with empty unit_price/discount/amount
#   - detail with bsn_code containing '-' (e.g. "026ต2210-1")

CREDIT_NOTE_SAMPLE_LINES = [
    '"(BSN)บจก.บุญสวัสดิ์นำชัย                                                                                                                      หน้า   :        1"',
    '"  รายงานใบลดหนี้/รับคืนสินค้า\xa0เรียงตามเลขที่"',
    '"---------------------------------------------------------------------------------------------------------------------------------------------------------------"',
    '"   เลขที่       วันที่   ลูกค้า                               พนักงานขาย\xa0\xa0อ้างถึงใบกำกับ\xa0\xa0V  ส่วนลด     มูลค่าสินค้า     VAT.       รวมทั้งสิ้น ตัดหนี้แล้ว\xa0ประเภท"',
    '"---------------------------------------------------------------------------------------------------------------------------------------------------------------"',
    # Master 1: basic, single detail
    '"  SR6700003    10/01/67  ประไพศรีโลหะกิจ                      06         IV6602766    1                  3375.00         0.00       3375.00        Y      2"',
    '"     Y   1 553ด5118\xa0\xa0ดจ.แสตนเลส\xa07/16"\xa0SMIC              30.00ดอก             150.00        25%       3375.00                                IV6602766-  1"',
    '',
    # Master 2: cancelled (*SR), no details
    '" *SR6700017    04/03/67  หน้าร้านL                            97         IV6700489    1                     0.00         0.00          0.00        Y      2"',
    '',
    # Master 3: salesperson with hyphen "06-L", single detail
    '"  SR6700019    05/03/67  นางทิดสะไหม\xa0(ลูกสาว)                 06-L       IV6602855    1                 16550.00         0.00      16550.00        Y      2"',
    '"     Y   1 044ล0700\xa0\xa0ลูกบิด\xa0#700(P)\xa0SS\xa0\'SENDAI\'          1.00แผง             125.00         5%        118.75                                IV6602855-  2"',
    '',
    # Master 4: multi-detail (3 detail rows, all with "5+5%" discount, hyphenated bsn_code)
    '"  SR6700009    17/02/67  ขุนแผน\xa059                            06         IV4660048    1        10%       1364.58         0.00       1364.58        Y      3"',
    '"     Y   1 026ต2210-1\xa0\xa0รีเวท\xa04-2\xa0Dome\xa0Nature(P)          7.00แผง             120.00       5+5%        758.10                                IV4660048-  4"',
    '"     Y   2 026ต2510-1\xa0\xa0รีเวท\xa04-4\xa0Dome\xa0Nature(P)          1.00แผง             120.00       5+5%        108.30                                IV4660048-  5"',
    '"     Y   3 026ต2710-1\xa0\xa0รีเวท\xa04-6\xa0Dome\xa0Nature(P)          6.00แผง             120.00       5+5%        649.80                                IV4660048-  6"',
    '',
    # Master 5: detail with empty unit_price/discount/amount (qty+unit only + ref)
    '"  SR6700001    08/01/67  กระจกหรู\xa0ประตูสวย                    31         IV6602028    1                     0.00         0.00          0.00        Y      2"',
    '"     Y   1 041ม5560\xa0\xa0มือจับ(P)#555-350มิล.AC\xa0\'S/D\'       2.00แผง                                                                            IV6602028-  3"',
    '',
    # Master 6: detail rows with N marker (record-only, ยังไม่ตัดหนี้). Some N rows
    # have NO qty (just unit follows the product name). Both forms must parse.
    '"  SR6700028    05/04/67  โฮมมอลล์ จำกัด                       06         IV6700819    2                   306.00        21.42        327.42        Y      2"',
    '"     N   1 528ก2215\xa0\xa0กระดาษทรายม้วน#80\'HORSE SHOE\'           ม้วน            120.00        15%        102.00                                IV6700819-  1"',
    '"     N   2 528ก2214\xa0\xa0กระดาษทรายม้วน#100\'HORSE SHOE           ม้วน            240.00        15%        204.00                                IV6700819-  2"',
    '',
    # Master 7: N detail with qty present (mix of with/without qty across SRs)
    '"  SR6700033    21/05/67  ขุนแผน 59                            06         IV6701251    2                   352.02        24.64        376.66        Y      2"',
    '"     N   1 532ร1039\xa0\xa0ระดับน้ำมีแม่เหล็ก9"\xa0\'META\'         6.00อัน              58.67                   352.02                                IV6701251-  6"',
    '',
]


@pytest.fixture
def sample_credit_note_file(tmp_path):
    p = tmp_path / "ใบลดหนี้_sample.csv"
    p.write_text("\n".join(CREDIT_NOTE_SAMPLE_LINES) + "\n", encoding="cp874")
    return str(p)


# ── Tests ────────────────────────────────────────────────────────────────────

def test_date_be_to_iso_master(sample_credit_note_file):
    """Master date in BE (DD/MM/YY พ.ศ.) → Gregorian ISO."""
    entries = parse_weekly.parse_credit_notes(sample_credit_note_file)
    by_doc = {e['doc_no']: e for e in entries}
    # SR6700003 dated 10/01/67 → 2024-01-10
    assert by_doc['SR6700003-1']['date_iso'] == '2024-01-10'
    # SR6700019 dated 05/03/67 → 2024-03-05
    assert by_doc['SR6700019-1']['date_iso'] == '2024-03-05'


def test_doc_no_normalization_sr_with_seq(sample_credit_note_file):
    """doc_no = SR_no + '-' + detail seq; doc_base = SR_no alone."""
    entries = parse_weekly.parse_credit_notes(sample_credit_note_file)
    by_doc = {e['doc_no']: e for e in entries}
    # Multi-detail master yields seq 1, 2, 3 — all sharing doc_base
    assert 'SR6700009-1' in by_doc
    assert 'SR6700009-2' in by_doc
    assert 'SR6700009-3' in by_doc
    assert by_doc['SR6700009-1']['doc_base'] == 'SR6700009'
    assert by_doc['SR6700009-2']['doc_base'] == 'SR6700009'
    assert by_doc['SR6700009-3']['doc_base'] == 'SR6700009'


def test_qty_unit_glued_split(sample_credit_note_file):
    """qty and unit are glued in source ('30.00ดอก') — split correctly."""
    entries = parse_weekly.parse_credit_notes(sample_credit_note_file)
    by_doc = {e['doc_no']: e for e in entries}
    e = by_doc['SR6700003-1']
    assert e['qty'] == 30.0
    assert e['unit'] == 'ดอก'
    assert e['unit_price'] == 150.00
    assert e['discount'] == '25%'
    assert e['total'] == 3375.00


def test_salesperson_with_hyphen(sample_credit_note_file):
    """Salesperson can be '06-L' (Laos) — must capture full token."""
    entries = parse_weekly.parse_credit_notes(sample_credit_note_file)
    by_doc = {e['doc_no']: e for e in entries}
    e = by_doc['SR6700019-1']
    assert e['salesperson'] == '06-L'
    assert e['customer'] == 'นางทิดสะไหม (ลูกสาว)'


def test_cancelled_master(sample_credit_note_file):
    """*SR… is a cancelled credit note — flag carried, master emitted as placeholder."""
    entries = parse_weekly.parse_credit_notes(sample_credit_note_file)
    by_doc = {e['doc_no']: e for e in entries}
    # Master with no details still gets one entry (seq=1)
    assert 'SR6700017-1' in by_doc
    e = by_doc['SR6700017-1']
    assert e['cancelled'] is True
    assert e['bsn_code'] is None
    assert e['qty'] == 0.0


def test_multi_detail_master_rolls_up_to_same_doc_base(sample_credit_note_file):
    """A master with 3 detail rows produces 3 entries sharing doc_base + master fields."""
    entries = parse_weekly.parse_credit_notes(sample_credit_note_file)
    sr9 = [e for e in entries if e['doc_base'] == 'SR6700009']
    assert len(sr9) == 3
    # All share master-level fields
    assert {e['customer'] for e in sr9} == {'ขุนแผน 59'}
    assert {e['ref_invoice'] for e in sr9} == {'IV4660048'}
    assert {e['vat_type'] for e in sr9} == {1}
    # bsn_codes contain '-' (hyphenated) and must round-trip
    bsn = sorted(e['bsn_code'] for e in sr9)
    assert bsn == ['026ต2210-1', '026ต2510-1', '026ต2710-1']
    # Each detail has the line discount '5+5%'
    assert all(e['discount'] == '5+5%' for e in sr9)
    # Sum of detail amounts = 1516.20 (758.10 + 108.30 + 649.80)
    assert sum(e['total'] for e in sr9) == pytest.approx(758.10 + 108.30 + 649.80)


def test_empty_unit_price_and_discount_fields(sample_credit_note_file):
    """A detail with only qty+unit+ref (zero unit_price/discount/amount) → zeros, not parse failure."""
    entries = parse_weekly.parse_credit_notes(sample_credit_note_file)
    by_doc = {e['doc_no']: e for e in entries}
    e = by_doc['SR6700001-1']
    assert e['bsn_code']    == '041ม5560'
    assert e['qty']         == 2.00
    assert e['unit']        == 'แผง'
    assert e['unit_price']  == 0.0
    assert e['discount']    == ''
    assert e['total']       == 0.0
    assert e['ref_invoice_line'] == 'IV6602028-3'


def test_detect_file_type_credit_note(sample_credit_note_file):
    """detect_file_type recognises ใบลดหนี้ files."""
    assert parse_weekly.detect_file_type(sample_credit_note_file) == 'credit_note'


def test_required_fields_present(sample_credit_note_file):
    """Every entry has the full output schema."""
    required = {
        'date_iso', 'doc_no', 'doc_base', 'bsn_code', 'product_name_raw',
        'customer', 'salesperson', 'ref_invoice', 'ref_invoice_line',
        'vat_type', 'qty', 'unit', 'unit_price', 'discount',
        'total', 'net', 'cancelled',
    }
    entries = parse_weekly.parse_credit_notes(sample_credit_note_file)
    for e in entries:
        assert required.issubset(e.keys()), f"missing fields in {e}"


def test_n_marker_detail_without_qty(sample_credit_note_file):
    """N (record-only) detail line where qty is missing — unit follows name directly.
    Old parser only matched 'Y' marker, so SRs like SR6700028 emitted as placeholder."""
    entries = parse_weekly.parse_credit_notes(sample_credit_note_file)
    by_doc = {e['doc_no']: e for e in entries}
    e1 = by_doc['SR6700028-1']
    assert e1['bsn_code']    == '528ก2215'
    assert e1['qty']         == 0.0           # qty omitted in source
    assert e1['unit']        == 'ม้วน'
    assert e1['unit_price']  == 120.00
    assert e1['discount']    == '15%'
    assert e1['total']       == 102.00
    e2 = by_doc['SR6700028-2']
    assert e2['bsn_code']    == '528ก2214'
    assert e2['qty']         == 0.0
    assert e2['total']       == 204.00


def test_n_marker_detail_with_qty(sample_credit_note_file):
    """N marker with qty present — same shape as Y, just record-only flag."""
    entries = parse_weekly.parse_credit_notes(sample_credit_note_file)
    by_doc = {e['doc_no']: e for e in entries}
    e = by_doc['SR6700033-1']
    assert e['bsn_code']    == '532ร1039'
    assert e['qty']         == 6.0
    assert e['unit']        == 'อัน'
    assert e['unit_price']  == 58.67
    assert e['total']       == 352.02
