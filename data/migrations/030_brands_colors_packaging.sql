-- 030_brands_colors_packaging.sql
-- Round 3 of catalog cleanup based on user CSV review 2026-05-05:
--
--   1) Add 7 brands: MACOH, INTER, Sonic, Heller, เหรียญทอง, ตราม้า, นก
--   2) Add 2 color codes: JBB (สีทองแดงรมดำ), SS-BK (สีเงิน-สแตนเลส-ดำ)
--   3) Fix typo เหรีญทอง → เหรียญทอง
--   4) Extend packaging CHECK to allow แพ็คหัว, แพ็คถุง
--
-- Apply:    sqlite3 .../inventory.db < .../030_brands_colors_packaging.sql
-- Rollback: 030_brands_colors_packaging.rollback.sql

BEGIN;

-- 1) Brands -----------------------------------------------------------------

INSERT INTO brands(code, name, name_th, is_own_brand, sort_order, short_code) VALUES
    ('macoh',       'MACOH',      NULL,        0, 200, 'MACOH'),
    ('inter',       'INTER',      NULL,        0, 200, 'INTER'),
    ('sonic',       'Sonic',      NULL,        0, 200, 'SONIC'),
    ('heller',      'Heller',     NULL,        0, 200, 'HELLER'),
    ('coin_gold',   'เหรียญทอง',   NULL,        0, 200, 'COIN'),
    ('horse_brand', 'ตราม้า',      NULL,        0, 200, 'MAA'),
    ('bird_brand',  'นก',         NULL,        0, 200, 'BIRD');

-- 2) Color codes ------------------------------------------------------------

INSERT INTO color_finish_codes(code, name_th, sort_order) VALUES
    ('JBB',   'สีทองแดงรมดำ',       25),
    ('SS-BK', 'สีเงิน-สแตนเลส-ดำ',   75);

-- 3) Typo fix ---------------------------------------------------------------

UPDATE products
   SET product_name = REPLACE(product_name, 'เหรีญทอง', 'เหรียญทอง')
 WHERE product_name LIKE '%เหรีญทอง%';

-- 4) Extend packaging CHECK -------------------------------------------------

DROP TRIGGER IF EXISTS products_packaging_check_insert;
DROP TRIGGER IF EXISTS products_packaging_check_update;

CREATE TRIGGER products_packaging_check_insert
    BEFORE INSERT ON products
    WHEN NEW.packaging IS NOT NULL
         AND NEW.packaging NOT IN ('แผง','ตัว','ถุง','แพ็คหัว','แพ็คถุง')
    BEGIN
        SELECT RAISE(ABORT,
            'packaging must be NULL or one of: แผง, ตัว, ถุง, แพ็คหัว, แพ็คถุง');
    END;

CREATE TRIGGER products_packaging_check_update
    BEFORE UPDATE ON products
    WHEN NEW.packaging IS NOT NULL
         AND NEW.packaging NOT IN ('แผง','ตัว','ถุง','แพ็คหัว','แพ็คถุง')
    BEGIN
        SELECT RAISE(ABORT,
            'packaging must be NULL or one of: แผง, ตัว, ถุง, แพ็คหัว, แพ็คถุง');
    END;

INSERT INTO applied_migrations(filename, applied_at)
VALUES ('030_brands_colors_packaging.sql', datetime('now','localtime'));

COMMIT;
