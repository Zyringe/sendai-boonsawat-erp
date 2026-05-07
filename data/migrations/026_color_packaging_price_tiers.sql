-- 026_color_packaging_price_tiers.sql
-- Catalog-supporting schema additions:
--   1) color_finish_codes  — lookup of finish/color codes ↔ Thai display names
--   2) products.color_code — structured FK to color_finish_codes
--   3) products.packaging  — 'แผง' / 'ตัว' (Thai canonical, nullable)
--   4) product_price_tiers — volume-discount pricing for SAME SKU
--                            (e.g. 1 กิโล=฿100, 1 ลัง=฿900). Family grouping
--                            handles the case where แผง/ตัว are SEPARATE SKUs.
--
-- Apply:    sqlite3 .../inventory.db < .../026_color_packaging_price_tiers.sql
-- Rollback: 026_color_packaging_price_tiers.rollback.sql

BEGIN;

-- 1) color_finish_codes ------------------------------------------------------

CREATE TABLE color_finish_codes (
    code        TEXT PRIMARY KEY,         -- 'AC', 'PAB', 'SS', ...
    name_th     TEXT NOT NULL,             -- canonical Thai name shown to customers
    sort_order  INTEGER NOT NULL DEFAULT 100,
    note        TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TRIGGER update_color_finish_codes_timestamp
    AFTER UPDATE ON color_finish_codes
    BEGIN
        UPDATE color_finish_codes SET updated_at = datetime('now','localtime')
        WHERE code = NEW.code;
    END;

-- Seed 10 codes confirmed 2026-05-05 (counts from product_name scan).
-- sort_order groups visually: copper/black tones → brass → silver → others.
INSERT INTO color_finish_codes(code, name_th, sort_order) VALUES
    ('AC',  'สีรมดำ',           10),
    ('AB',  'สีทองแดงรมดำ',     20),
    ('PAB', 'สีทองดำเงา',        30),
    ('PB',  'สีทองเงา',          40),
    ('SB',  'สีทองด้าน',         50),
    ('CR',  'สีโครเมียม',        60),
    ('SS',  'สีเงิน-สแตนเลส',    70),
    ('SN',  'สีเงินด้าน',         80),
    ('NK',  'สีนิกเกิล',          90),
    ('BN',  'สีน้ำตาลเข้ม',      100);

-- 2) products.color_code -----------------------------------------------------

ALTER TABLE products ADD COLUMN color_code TEXT
    REFERENCES color_finish_codes(code);

CREATE INDEX idx_products_color_code ON products(color_code);

-- 3) products.packaging ------------------------------------------------------
-- SQLite ALTER TABLE doesn't support CHECK in ADD COLUMN; enforce via trigger.

ALTER TABLE products ADD COLUMN packaging TEXT;

CREATE TRIGGER products_packaging_check_insert
    BEFORE INSERT ON products
    WHEN NEW.packaging IS NOT NULL AND NEW.packaging NOT IN ('แผง','ตัว')
    BEGIN
        SELECT RAISE(ABORT, 'packaging must be NULL, ''แผง'', or ''ตัว''');
    END;

CREATE TRIGGER products_packaging_check_update
    BEFORE UPDATE ON products
    WHEN NEW.packaging IS NOT NULL AND NEW.packaging NOT IN ('แผง','ตัว')
    BEGIN
        SELECT RAISE(ABORT, 'packaging must be NULL, ''แผง'', or ''ตัว''');
    END;

CREATE INDEX idx_products_packaging ON products(packaging);

-- 4) product_price_tiers -----------------------------------------------------

CREATE TABLE product_price_tiers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id  INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    qty_label   TEXT    NOT NULL,        -- e.g. '1 กิโล', '1 ลัง', '1 ตัว', '1 แผง'
    price       REAL    NOT NULL CHECK (price >= 0),
    note        TEXT,
    sort_order  INTEGER NOT NULL DEFAULT 100,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    UNIQUE(product_id, qty_label)
);

CREATE INDEX idx_product_price_tiers_product ON product_price_tiers(product_id);

CREATE TRIGGER update_product_price_tiers_timestamp
    AFTER UPDATE ON product_price_tiers
    BEGIN
        UPDATE product_price_tiers SET updated_at = datetime('now','localtime')
        WHERE id = NEW.id;
    END;

CREATE TRIGGER audit_product_price_tiers_insert
AFTER INSERT ON product_price_tiers
BEGIN
    INSERT INTO audit_log (table_name, row_id, action, changed_fields)
    VALUES ('product_price_tiers', NEW.id, 'INSERT',
        json_object(
            'product_id', NEW.product_id,
            'qty_label',  NEW.qty_label,
            'price',      NEW.price,
            'sort_order', NEW.sort_order,
            'note',       NEW.note
        ));
END;

CREATE TRIGGER audit_product_price_tiers_update
AFTER UPDATE ON product_price_tiers
WHEN (
       OLD.product_id IS NOT NEW.product_id
    OR OLD.qty_label  IS NOT NEW.qty_label
    OR OLD.price      IS NOT NEW.price
    OR OLD.sort_order IS NOT NEW.sort_order
    OR OLD.note       IS NOT NEW.note
)
BEGIN
    INSERT INTO audit_log (table_name, row_id, action, changed_fields)
    SELECT 'product_price_tiers', NEW.id, 'UPDATE',
           json_group_object(field, json_array(old_v, new_v))
    FROM (
                  SELECT 'product_id' AS field, OLD.product_id AS old_v, NEW.product_id AS new_v WHERE OLD.product_id IS NOT NEW.product_id
        UNION ALL SELECT 'qty_label',           OLD.qty_label,           NEW.qty_label           WHERE OLD.qty_label  IS NOT NEW.qty_label
        UNION ALL SELECT 'price',               OLD.price,               NEW.price               WHERE OLD.price      IS NOT NEW.price
        UNION ALL SELECT 'sort_order',          OLD.sort_order,          NEW.sort_order          WHERE OLD.sort_order IS NOT NEW.sort_order
        UNION ALL SELECT 'note',                OLD.note,                NEW.note                WHERE OLD.note       IS NOT NEW.note
    );
END;

CREATE TRIGGER audit_product_price_tiers_delete
BEFORE DELETE ON product_price_tiers
BEGIN
    INSERT INTO audit_log (table_name, row_id, action, changed_fields)
    VALUES ('product_price_tiers', OLD.id, 'DELETE',
        json_object(
            'product_id', OLD.product_id,
            'qty_label',  OLD.qty_label,
            'price',      OLD.price
        ));
END;

-- Record migration -----------------------------------------------------------

INSERT INTO applied_migrations(filename, applied_at)
VALUES ('026_color_packaging_price_tiers.sql', datetime('now','localtime'));

COMMIT;
