"""
Tests for models.parse_payment_csv — การรับชำระหนี้ (AR) cp874 parser.
"""
import models


PAYMENT_SAMPLE_LINES = [
    '"(BSN)บจก.บุญสวัสดิ์นำชัย                                                                                          หน้า   :        1"',
    '"  รายงานการรับชำระหนี้ เรียงตามวันที่ของใบเสร็จ"',
    '"---------------------------------------------------------------------------------------------------------------------------------"',
    '"  วันที่  เลขที่ใบเสร็จ  ชื่อลูกค้า                          พนักงานขาย     ตัดเงินมัดจำ ยอดตามใบกำกับ   ชำระเป็น ง/ส       เช็ครับ"',
    '"---------------------------------------------------------------------------------------------------------------------------------"',
    # Standard salesperson code (digits only) — works with original regex
    '"03/01/67  RE6700001    สหภัณฑ์เคหะกิจ (V)                       06                               7524.99        7524.99"',
    '"                             IV6602085    12/09/66          4368.49"',
    '"                             IV6602095    13/09/66          3156.50"',
    '"                     หมายเหตุ:"',
    '"                        โอน BSN 27/12/66"',
    '',
    # Hyphenated salesperson code "06-L" — was the bug; should now parse
    '"22/01/67  RE6700064    มหาชัยวัสดุ (MAHAXAY TRADING)            06-L                            25972.00       25972.00"',
    '"                             IV6700123    20/01/67         25972.00"',
    '',
    # Cancelled record (asterisk prefix on RE no)
    '"05/02/67  *RE6700100    เลิกสัญญา                                06                                 100.00         100.00"',
    '"                             IV6700200    01/02/67           100.00"',
    '',
]


import pytest


@pytest.fixture
def sample_payment_file(tmp_path):
    p = tmp_path / "การรับชำระหนี้_sample.csv"
    p.write_text("\n".join(PAYMENT_SAMPLE_LINES) + "\n", encoding="cp874")
    return str(p)


def test_parse_payment_basic(sample_payment_file):
    records = models.parse_payment_csv(sample_payment_file)
    re_nos = [r["re_no"] for r in records]
    assert "RE6700001" in re_nos
    assert "RE6700064" in re_nos  # hyphenated salesperson — was the bug
    assert "RE6700100" in re_nos


def test_parse_payment_hyphenated_salesperson(sample_payment_file):
    """Salesperson code can be '06-L' (hyphen). Old regex required \\w+, missed it."""
    records = models.parse_payment_csv(sample_payment_file)
    by_re = {r["re_no"]: r for r in records}
    assert by_re["RE6700064"]["salesperson"] == "06-L"
    assert by_re["RE6700064"]["customer"] == "มหาชัยวัสดุ (MAHAXAY TRADING)"
    assert by_re["RE6700064"]["date_iso"] == "2024-01-22"


def test_parse_payment_cancelled_flag(sample_payment_file):
    """RE no with leading * marks cancelled receipts."""
    records = models.parse_payment_csv(sample_payment_file)
    by_re = {r["re_no"]: r for r in records}
    assert by_re["RE6700100"]["cancelled"] is True
    assert by_re["RE6700001"]["cancelled"] is False


def test_parse_payment_iv_list(sample_payment_file):
    records = models.parse_payment_csv(sample_payment_file)
    by_re = {r["re_no"]: r for r in records}
    assert by_re["RE6700001"]["iv_list"] == ["IV6602085", "IV6602095"]
    assert by_re["RE6700064"]["iv_list"] == ["IV6700123"]
