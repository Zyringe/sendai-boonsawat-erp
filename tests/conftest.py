"""
Shared pytest fixtures.

GOLDEN RULE: tests NEVER touch the live DB.
Every fixture that needs a database copies inventory.db to a tmp_path
and monkeypatches config.DATABASE_PATH so models/database use the copy.

The inventory_app modules use bare imports (`from database import ...`).
pytest.ini adds inventory_app/ to pythonpath so those imports work.
"""
import os
import shutil
import sqlite3

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
LIVE_DB   = os.path.join(REPO_ROOT, 'inventory_app', 'instance', 'inventory.db')


# ── DB fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """
    Copy the live inventory.db into tmp_path and point config.DATABASE_PATH at it.

    Yields the absolute path to the temp DB.
    Any module that re-reads config.DATABASE_PATH (database.get_connection does)
    will hit the temp file, not the live one.
    """
    if not os.path.exists(LIVE_DB):
        pytest.skip(f"Live DB not found at {LIVE_DB} — skipping integration test")

    dst = tmp_path / "inventory.db"
    shutil.copy2(LIVE_DB, dst)

    # Some sessions also leave -wal/-shm sidecars; copy if present so the snapshot is consistent.
    for suffix in ('-wal', '-shm'):
        side = LIVE_DB + suffix
        if os.path.exists(side):
            shutil.copy2(side, str(dst) + suffix)

    import config
    monkeypatch.setattr(config, 'DATABASE_PATH', str(dst))
    # database.py imports DATABASE_PATH at module load time — patch there too.
    import database
    monkeypatch.setattr(database, 'DATABASE_PATH', str(dst))

    return str(dst)


@pytest.fixture
def tmp_db_conn(tmp_db):
    """sqlite3 connection on the temp DB (autocommit-style usage; tests may commit)."""
    conn = sqlite3.connect(tmp_db, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def empty_db(tmp_path, monkeypatch):
    """
    A fresh schema-only DB built via database.init_db().
    Use when a test wants no real data.
    """
    db_path = tmp_path / "fresh.db"
    import config
    monkeypatch.setattr(config, 'DATABASE_PATH', str(db_path))
    import database
    monkeypatch.setattr(database, 'DATABASE_PATH', str(db_path))

    database.init_db()
    return str(db_path)


@pytest.fixture
def empty_db_conn(empty_db):
    conn = sqlite3.connect(empty_db, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


# ── Synthesized BSN sample data ──────────────────────────────────────────────

# Keep these in sync with the real format observed in
# inventory_app/imports/ซื้อ_24.4.69.csv and ยอดขาย_แยกตามลูกค้า_15.4.69.csv.
# Lines are CSV-quoted, encoded cp874, use \xa0 as in-line padding.

PURCHASE_SAMPLE_LINES = [
    '"(BSN)บจก.บุญสวัสดิ์นำชัย                                                                                            หน้า   :        1"',
    '"  รายงานประวัติการซื้อ\xa0แยกตามผู้จำหน่าย"',
    '"-------------------------------------------------------------------------------------------------------------------------------------"',
    '"   สินค้า  วันที่  เลขที่เอกสาร       จำนวน   คืน  ราคาต่อหน่วย\xa0VAT\xa0\xa0 ส่วนลด       รวมเงิน  ส่วนลดรวม     ยอดซื้อสุทธิ อ้างถึง"',
    '"-------------------------------------------------------------------------------------------------------------------------------------"',
    '"  ย้งเจริญการพิมพ์\xa0/ย้ง"',
    '"   กล่องในปุ๊ก#7\xa0/Pกล่อง3"',
    '"        24/04/69   HP6900023       22965.00 กล            0.69  0                 15845.85                 15845.85 PO0000227-  1"',
    '"   ใบตัดเพชร\xa04\\"\xa0/031บ4120"',
    '"        23/04/68   RR6900061          12.00 อน           70.00  2      25+5%        598.50                   598.50"',
]

SALES_SAMPLE_LINES = [
    '"(BSN)บจก.บุญสวัสดิ์นำชัย                                                                                             หน้า   :        1"',
    '"  รายงานประวัติการขาย\xa0แยกตามลูกค้า"',
    '"--------------------------------------------------------------------------------------------------------------------------------------"',
    '"  สินค้า วันที่ เลขที่เอกสาร          จำนวน   คืน   ราคาต่อหน่วย\xa0VAT   ส่วนลด       รวมเงิน  ส่วนลดรวม  ยอดขายสุทธิ  อ้างอิง  หมายเหตุ"',
    '"--------------------------------------------------------------------------------------------------------------------------------------"',
    '"  ไพศาลโลหะภัณฑ์(ตลาดพลู)\xa0/01พ02"',
    '"   ใบตัดเพชร\xa04\xa0#GL-888(แดง)\xa0/031บ4120"',
    '"      04/04/69   IV6900503-  1        24.00 ใบ          160.00  1                  3840.00                  3840.00"',
    '"      04/04/69   IV6900503-  2         3.00 ใบ            0.00  1                     0.00                     0.00               ***"',
    '"  วรสวัสดิ์\xa0ฮาร์ดแวร์\xa0/01อ35"',
    '"   กลอนห้องน้ำกลาง\xa0STL#430\xa0(P)\xa0/001ก3435"',
    '"      04/04/69   IV6900501-  1        48.00 ผง           30.00  2        20%       1152.00                  1152.00"',
    # Decimal-baht line discount (ส่วนลดเป็นบาท): 50.00 - 32.00 discount = 18.00 total
    '"  ทดสอบส่วนลดทศนิยม\xa0/01ท99"',
    '"   ดจ./ปูนโรตารี่\xa08x110\xa0มิล\'GL\'\xa0/010ด7130"',
    '"      03/04/69   IV6900498-  2         1.00 ดก           50.00  1      32.00         18.00                    18.00"',
    # Doc-level discount column (ส่วนลดรวม) as percent: 1764 × 0.98 = 1728.72
    # Old regex captured only "2" (the digit before %) as net, dropping 1728.72 entirely.
    '"      04/03/69   IV6900370-  2         1.00 ลง         1960.00  1        10%       1764.00         2%       1728.72"',
    # qty!unit collision: BSN occasionally emits qty and unit glued by '!' instead of whitespace
    # (e.g. "2.00!หล"). Old regex used \s+ between qty and unit groups, so the whole row failed
    # to match and was silently dropped. ~137 such rows existed in the 2024–2026 sales export.
    '"  ทดสอบbangseparator\xa0/01บ99"',
    '"   ดจ./ปูนโรตารี่bang\xa0/010ด7131"',
    '"      19/04/68   IV6801044-  4         2.00!หล         1317.79  2        10%       2372.02                  2372.02 SO0"',
]


@pytest.fixture
def sample_purchase_file(tmp_path):
    p = tmp_path / "ซื้อ_sample.csv"
    p.write_text("\n".join(PURCHASE_SAMPLE_LINES) + "\n", encoding="cp874")
    return str(p)


@pytest.fixture
def sample_sales_file(tmp_path):
    p = tmp_path / "ขาย_sample.csv"
    p.write_text("\n".join(SALES_SAMPLE_LINES) + "\n", encoding="cp874")
    return str(p)
