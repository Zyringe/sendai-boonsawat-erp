-- 004_brands_categories.sql
-- Phase C1 of the schema refactor.
-- Adds brand + category master tables and links them to products.
-- Seeds the 11 brands actually present in the catalogue (counted in
-- audit), plus a 3rd_party fallback. Seeds 22 sensible top-level
-- hardware categories.
--
-- Backfill strategy:
--   - brand_id: high-confidence regex match by name keyword (Sendai →
--     sendai, สิงห์ทอง → golden_lion, Eagle One/อีเกิ้ลวัน → eagle_one,
--     etc.). Anything not matched stays NULL — user fills manually.
--   - category_id: NOT auto-filled. Too many edge cases; user assigns
--     while editing each product. Categories table seeded so the
--     dropdown is ready.
--
-- Apply:
--   sqlite3 .../inventory.db < .../migrations/004_brands_categories.sql
--
-- Rollback: 004_brands_categories.rollback.sql

BEGIN;

-- ── brands ────────────────────────────────────────────────────────────────
CREATE TABLE brands (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    code         TEXT    UNIQUE NOT NULL,
    name         TEXT    NOT NULL,            -- canonical display name (e.g. 'Sendai')
    name_th      TEXT,                         -- Thai display (e.g. 'เซ็นได')
    is_own_brand INTEGER NOT NULL DEFAULT 0 CHECK(is_own_brand IN (0,1)),
    sort_order   INTEGER NOT NULL DEFAULT 100,
    note         TEXT,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at   TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

INSERT INTO brands (code, name, name_th, is_own_brand, sort_order) VALUES
    -- own brands first (sort priority)
    ('golden_lion',  'Golden Lion',  'สิงห์ทอง',  1,  10),
    ('a_spec',       'A-SPEC',       NULL,        1,  20),
    ('sendai',       'Sendai',       'เซ็นได',     1,  30),
    -- common 3rd-party brands seen in product names
    ('eagle_one',    'Eagle One',    'อีเกิ้ลวัน',    0,  100),
    ('king_eagle',   'King Eagle',   NULL,        0,  100),
    ('toa',          'TOA',          'จระเข้',     0,  100),
    ('meta',         'META',         NULL,        0,  100),
    ('bravo',        'BRAVO',        NULL,        0,  100),
    ('yokomo',       'Yokomo',       NULL,        0,  100),
    ('sanwa',        'SANWA',        NULL,        0,  100),
    ('solex',        'SOLEX',        NULL,        0,  100),
    ('bahco',        'BAHCO',        NULL,        0,  100),
    -- catch-all for un-classified
    ('third_party',  'Other',        'ทั่วไป',      0,  999);

-- ── categories ────────────────────────────────────────────────────────────
CREATE TABLE categories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT    UNIQUE NOT NULL,
    name_th     TEXT    NOT NULL,
    parent_id   INTEGER REFERENCES categories(id),
    sort_order  INTEGER NOT NULL DEFAULT 100,
    note        TEXT,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

INSERT INTO categories (code, name_th, sort_order) VALUES
    ('door_bolt',     'กลอน / สลักประตู',         10),
    ('door_knob',     'ลูกบิด / ก๊อกประตู',         20),
    ('hinge',         'บานพับ',                   30),
    ('handle',        'มือจับ / หูเหล็ก',           40),
    ('lock_key',      'กุญแจ / แม่กุญแจ',           50),
    ('hammer',        'ค้อน',                    60),
    ('screwdriver',   'ไขควง',                   70),
    ('cutter',        'กรรไกร / มีดตัด',          80),
    ('plier',         'คีม',                    90),
    ('drill_bit',     'ดอกสว่าน',                100),
    ('saw',           'เลื่อย / ใบเลื่อย',          110),
    ('fastener',      'ตะปู / น๊อต / สกรู',       120),
    ('anchor',        'ปุ๊ก / สมอ',               130),
    ('glue',          'กาว / ซิลิโคน',            140),
    ('paint_brush',   'สี / แปรง',               150),
    ('sandpaper',     'กระดาษทราย / ผ้าทราย',   160),
    ('tape_gypsum',   'เทป / ผ้ายิปซั่ม',          170),
    ('faucet',        'ก๊อกน้ำ / สุขภัณฑ์',        180),
    ('trowel',        'เกียง / ฉาก / มือจับโป้ว',  190),
    ('wire_cable',    'ลวด / ลวดสลิง / สาย',     200),
    ('disc',          'แผ่นตัด / แผ่นขัด',         210),
    ('chemical',      'สารเคมี / น้ำยา / โซดาไฟ',  220),
    ('measuring',     'เครื่องวัด / ตลับเมตร',      230),
    ('safety',        'อุปกรณ์ความปลอดภัย',       240),
    ('other',         'อื่น ๆ',                  999);

-- ── link products → brand + category ──────────────────────────────────────
ALTER TABLE products ADD COLUMN brand_id INTEGER REFERENCES brands(id);
ALTER TABLE products ADD COLUMN category_id INTEGER REFERENCES categories(id);

CREATE INDEX idx_products_brand    ON products(brand_id);
CREATE INDEX idx_products_category ON products(category_id);

-- ── auto-backfill brand_id (high-confidence keyword match only) ───────────
-- Order matters: more specific matches first to avoid mis-classification
-- (e.g. 'King Eagle' contains 'Eagle' so check 'King Eagle' before 'Eagle One').
UPDATE products SET brand_id = (SELECT id FROM brands WHERE code = 'king_eagle')
 WHERE brand_id IS NULL AND product_name LIKE '%King Eagle%';

UPDATE products SET brand_id = (SELECT id FROM brands WHERE code = 'eagle_one')
 WHERE brand_id IS NULL AND (product_name LIKE '%Eagle One%' OR product_name LIKE '%อีเกิ้ลวัน%' OR product_name LIKE '%Eagle-One%' OR product_name LIKE '%Eagle-one%');

UPDATE products SET brand_id = (SELECT id FROM brands WHERE code = 'sendai')
 WHERE brand_id IS NULL AND (product_name LIKE '%Sendai%' OR product_name LIKE '%SENDAI%');

UPDATE products SET brand_id = (SELECT id FROM brands WHERE code = 'golden_lion')
 WHERE brand_id IS NULL AND product_name LIKE '%สิงห์%';

UPDATE products SET brand_id = (SELECT id FROM brands WHERE code = 'a_spec')
 WHERE brand_id IS NULL AND product_name LIKE '%A-SPEC%';

UPDATE products SET brand_id = (SELECT id FROM brands WHERE code = 'meta')
 WHERE brand_id IS NULL AND (product_name LIKE '%META%' OR product_name LIKE '%''META''%');

UPDATE products SET brand_id = (SELECT id FROM brands WHERE code = 'toa')
 WHERE brand_id IS NULL AND (product_name LIKE '%จระเข้%' OR product_name LIKE '%TOA%');

UPDATE products SET brand_id = (SELECT id FROM brands WHERE code = 'bravo')
 WHERE brand_id IS NULL AND product_name LIKE '%BRAVO%';

UPDATE products SET brand_id = (SELECT id FROM brands WHERE code = 'yokomo')
 WHERE brand_id IS NULL AND product_name LIKE '%Yokomo%';

UPDATE products SET brand_id = (SELECT id FROM brands WHERE code = 'sanwa')
 WHERE brand_id IS NULL AND (product_name LIKE '%SANWA%' OR product_name LIKE '%Sanwa%');

UPDATE products SET brand_id = (SELECT id FROM brands WHERE code = 'solex')
 WHERE brand_id IS NULL AND product_name LIKE '%SOLEX%';

UPDATE products SET brand_id = (SELECT id FROM brands WHERE code = 'bahco')
 WHERE brand_id IS NULL AND product_name LIKE '%BAHCO%';

COMMIT;
