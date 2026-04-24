import sqlite3
import os
from config import DATABASE_PATH
from werkzeug.security import generate_password_hash

SCHEMA = """
PRAGMA encoding = 'UTF-8';
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS products (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    sku                 INTEGER UNIQUE NOT NULL,
    product_name        TEXT    NOT NULL,
    units_per_carton    INTEGER,
    units_per_box       INTEGER,
    unit_type           TEXT    NOT NULL DEFAULT 'ตัว',
    hard_to_sell        INTEGER NOT NULL DEFAULT 0,
    cost_price          REAL    NOT NULL DEFAULT 0.0,
    base_sell_price     REAL    NOT NULL DEFAULT 0.0,
    low_stock_threshold INTEGER NOT NULL DEFAULT 10,
    is_active           INTEGER NOT NULL DEFAULT 1,
    created_at          TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at          TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS stock_levels (
    product_id  INTEGER PRIMARY KEY REFERENCES products(id),
    quantity    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS transactions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id      INTEGER NOT NULL REFERENCES products(id),
    txn_type        TEXT    NOT NULL CHECK(txn_type IN ('IN','OUT','ADJUST')),
    quantity_change INTEGER NOT NULL,
    unit_mode       TEXT    NOT NULL CHECK(unit_mode IN ('unit','box','carton')),
    reference_no    TEXT,
    note            TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS promotions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id      INTEGER NOT NULL REFERENCES products(id),
    promo_name      TEXT    NOT NULL,
    promo_type      TEXT    NOT NULL CHECK(promo_type IN ('percent','fixed')),
    discount_value  REAL    NOT NULL,
    date_start      TEXT,
    date_end        TEXT,
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS import_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    filename        TEXT    NOT NULL,
    rows_imported   INTEGER NOT NULL,
    rows_skipped    INTEGER NOT NULL,
    imported_at     TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    notes           TEXT
);

-- BSN system product code → internal product mapping
CREATE TABLE IF NOT EXISTS product_code_mapping (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    bsn_code    TEXT UNIQUE NOT NULL,
    bsn_name    TEXT NOT NULL,
    product_id  INTEGER REFERENCES products(id),
    is_ignored  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- Sales transactions (from ขาย files)
CREATE TABLE IF NOT EXISTS sales_transactions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id            INTEGER REFERENCES import_log(id),
    date_iso            TEXT NOT NULL,
    doc_no              TEXT NOT NULL,
    product_id          INTEGER REFERENCES products(id),
    bsn_code            TEXT,
    product_name_raw    TEXT,
    customer            TEXT,
    customer_code       TEXT,
    qty                 REAL,
    unit                TEXT,
    unit_price          REAL,
    vat_type            INTEGER,
    discount            TEXT,
    total               REAL,
    net                 REAL,
    created_at          TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- Purchase transactions (from ซื้อ files)
CREATE TABLE IF NOT EXISTS purchase_transactions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id            INTEGER REFERENCES import_log(id),
    date_iso            TEXT NOT NULL,
    doc_no              TEXT NOT NULL,
    product_id          INTEGER REFERENCES products(id),
    bsn_code            TEXT,
    product_name_raw    TEXT,
    supplier            TEXT,
    supplier_code       TEXT,
    qty                 REAL,
    unit                TEXT,
    unit_price          REAL,
    vat_type            INTEGER,
    discount            TEXT,
    total               REAL,
    net                 REAL,
    created_at          TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS unit_conversions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id  INTEGER NOT NULL REFERENCES products(id),
    bsn_unit    TEXT    NOT NULL,
    ratio       REAL    NOT NULL DEFAULT 1.0,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    UNIQUE(product_id, bsn_unit)
);

CREATE TABLE IF NOT EXISTS product_locations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id  INTEGER NOT NULL REFERENCES products(id),
    floor_no    TEXT    NOT NULL,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS received_payments (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    re_no        TEXT    NOT NULL UNIQUE,
    date_iso     TEXT    NOT NULL,
    customer     TEXT    NOT NULL,
    salesperson  TEXT,
    cancelled    INTEGER NOT NULL DEFAULT 0,
    imported_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS paid_invoices (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    re_id      INTEGER NOT NULL REFERENCES received_payments(id),
    iv_no      TEXT    NOT NULL,
    UNIQUE(re_id, iv_no)
);

-- E-commerce platform SKUs (Shopee / Lazada)
-- Users & roles
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    UNIQUE NOT NULL,
    password_hash TEXT    NOT NULL,
    display_name  TEXT,
    role          TEXT    NOT NULL DEFAULT 'staff'
                          CHECK(role IN ('admin','manager','staff')),
    is_active     INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS platform_skus (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    platform             TEXT    NOT NULL CHECK(platform IN ('shopee','lazada')),
    product_id_str       TEXT,
    product_name         TEXT    NOT NULL,
    variation_id         TEXT,
    variation_name       TEXT,
    parent_sku           TEXT,
    seller_sku           TEXT,
    price                REAL,
    special_price        REAL,
    stock                INTEGER,
    internal_product_id  INTEGER REFERENCES products(id),
    qty_per_sale         REAL    NOT NULL DEFAULT 1,
    raw_json             TEXT,
    imported_at          TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    UNIQUE(platform, variation_id)
);

-- Product conversion formulas (สูตรแปลงสินค้า)
CREATE TABLE IF NOT EXISTS conversion_formulas (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    name              TEXT    NOT NULL,
    output_product_id INTEGER NOT NULL REFERENCES products(id),
    output_qty        INTEGER NOT NULL DEFAULT 1,
    note              TEXT,
    is_active         INTEGER NOT NULL DEFAULT 1,
    created_at        TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS conversion_formula_inputs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    formula_id  INTEGER NOT NULL REFERENCES conversion_formulas(id) ON DELETE CASCADE,
    product_id  INTEGER NOT NULL REFERENCES products(id),
    quantity    INTEGER NOT NULL
);

-- Customer master (imported from BSN customer info CSV)
CREATE TABLE IF NOT EXISTS customers (
    code          TEXT    PRIMARY KEY,
    name          TEXT    NOT NULL,
    salesperson   TEXT,
    zone          TEXT,
    customer_type TEXT,
    address       TEXT,
    phone         TEXT,
    tax_id        TEXT,
    credit_days   INTEGER NOT NULL DEFAULT 0,
    contact       TEXT,
    lat           REAL,
    lng           REAL,
    geocoded_at   TEXT,
    imported_at   TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TRIGGER IF NOT EXISTS update_product_timestamp
    AFTER UPDATE ON products
    BEGIN
        UPDATE products SET updated_at = datetime('now','localtime') WHERE id = NEW.id;
    END;

CREATE TRIGGER IF NOT EXISTS after_transaction_insert
    AFTER INSERT ON transactions
    BEGIN
        INSERT INTO stock_levels(product_id, quantity) VALUES (NEW.product_id, 0)
            ON CONFLICT(product_id) DO NOTHING;
        UPDATE stock_levels
           SET quantity = quantity + NEW.quantity_change
         WHERE product_id = NEW.product_id;
    END;
"""


def get_connection():
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_connection()
    conn.executescript(SCHEMA)
    # Migration: add synced_to_stock column to BSN transaction tables if missing
    for tbl in ('sales_transactions', 'purchase_transactions'):
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({tbl})").fetchall()]
        if 'synced_to_stock' not in cols:
            conn.execute(
                f"ALTER TABLE {tbl} ADD COLUMN synced_to_stock INTEGER NOT NULL DEFAULT 0"
            )
    # Migration: add shopee_stock and lazada_stock if missing
    cols = [r[1] for r in conn.execute("PRAGMA table_info(products)").fetchall()]
    if 'shopee_stock' not in cols:
        conn.execute("ALTER TABLE products ADD COLUMN shopee_stock INTEGER NOT NULL DEFAULT 0")
    if 'lazada_stock' not in cols:
        conn.execute("ALTER TABLE products ADD COLUMN lazada_stock INTEGER NOT NULL DEFAULT 0")
    # Migration: add doc_base column + indexes for payment status performance
    cols = [r[1] for r in conn.execute("PRAGMA table_info(sales_transactions)").fetchall()]
    if 'doc_base' not in cols:
        conn.execute("ALTER TABLE sales_transactions ADD COLUMN doc_base TEXT")
        conn.execute("""
            UPDATE sales_transactions
            SET doc_base = SUBSTR(doc_no, 1, INSTR(doc_no || '-', '-') - 1)
        """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_st_doc_base ON sales_transactions(doc_base)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pi_iv_no ON paid_invoices(iv_no)")
    # Migration: create conversion tables if missing
    existing_tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    if 'conversion_formulas' not in existing_tables:
        conn.executescript("""
            CREATE TABLE conversion_formulas (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                name              TEXT    NOT NULL,
                output_product_id INTEGER NOT NULL REFERENCES products(id),
                output_qty        INTEGER NOT NULL DEFAULT 1,
                note              TEXT,
                is_active         INTEGER NOT NULL DEFAULT 1,
                created_at        TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
            );
            CREATE TABLE conversion_formula_inputs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                formula_id  INTEGER NOT NULL REFERENCES conversion_formulas(id) ON DELETE CASCADE,
                product_id  INTEGER NOT NULL REFERENCES products(id),
                quantity    INTEGER NOT NULL
            );
        """)
    # Migration: create customers table if missing
    if 'customers' not in existing_tables:
        conn.executescript("""
            CREATE TABLE customers (
                code          TEXT    PRIMARY KEY,
                name          TEXT    NOT NULL,
                salesperson   TEXT,
                zone          TEXT,
                customer_type TEXT,
                address       TEXT,
                phone         TEXT,
                tax_id        TEXT,
                credit_days   INTEGER NOT NULL DEFAULT 0,
                contact       TEXT,
                lat           REAL,
                lng           REAL,
                geocoded_at   TEXT,
                imported_at   TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
            );
        """)
    # Migration: create product_cost_ledger and conversion_cost_log if missing
    if 'product_cost_ledger' not in existing_tables:
        conn.executescript("""
            CREATE TABLE product_cost_ledger (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id   INTEGER NOT NULL REFERENCES products(id),
                event_type   TEXT    NOT NULL,
                event_date   TEXT    NOT NULL,
                qty_change   REAL    NOT NULL,
                unit_cost    REAL    NOT NULL,
                stock_after  REAL    NOT NULL,
                wacc_after   REAL    NOT NULL,
                reference_no TEXT,
                note         TEXT,
                created_at   TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
            );
            CREATE INDEX idx_pcl_product ON product_cost_ledger(product_id, event_date, id);
        """)
    if 'conversion_cost_log' not in existing_tables:
        conn.executescript("""
            CREATE TABLE conversion_cost_log (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                output_product_id INTEGER NOT NULL REFERENCES products(id),
                reference_no      TEXT,
                event_date        TEXT    NOT NULL,
                output_qty        REAL    NOT NULL,
                total_input_cost  REAL    NOT NULL,
                unit_cost         REAL    NOT NULL,
                created_at        TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
            );
        """)
    # Migration: create default admin user if users table is empty
    if not conn.execute("SELECT 1 FROM users LIMIT 1").fetchone():
        import config as _cfg
        conn.execute(
            "INSERT INTO users(username, password_hash, display_name, role) VALUES (?,?,?,?)",
            ('admin', generate_password_hash(_cfg.ADMIN_PASSWORD), 'Administrator', 'admin')
        )
    conn.commit()
    conn.close()
