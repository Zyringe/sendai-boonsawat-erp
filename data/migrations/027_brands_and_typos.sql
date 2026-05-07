-- 027_brands_and_typos.sql
-- Two related cleanups identified by audit_sku_naming.py 2026-05-05:
--
--   1) Add 7 missing brands found in product names but absent from brands
--      table: FION, ORBIT, STAR, ตราจิงโจ้, HORSE SHOE, NITTO, BAC
--   2) Fix two common typos in product_name:
--        สแตนแลส → สแตนเลส (43 SKUs)
--        โครเมี่ยม → โครเมียม (5 SKUs)
--
-- This migration does NOT backfill products.brand_id — that's a heuristic
-- pass requiring review. Done as a separate scripted CSV review.
--
-- Apply:    sqlite3 .../inventory.db < .../027_brands_and_typos.sql
-- Rollback: 027_brands_and_typos.rollback.sql

BEGIN;

-- 1) Add missing brands ------------------------------------------------------

INSERT INTO brands(code, name, name_th, is_own_brand, sort_order, short_code) VALUES
    ('fion',       'FION',        NULL,        0, 200, 'FION'),
    ('orbit',      'ORBIT',       NULL,        0, 200, 'ORBIT'),
    ('star',       'STAR',        NULL,        0, 200, 'STAR'),
    ('kangaroo',   'ตราจิงโจ้',     NULL,        0, 200, 'KANGA'),
    ('horse_shoe', 'HORSE SHOE',  NULL,        0, 200, 'HORSE'),
    ('nitto',      'NITTO',       NULL,        0, 200, 'NITTO'),
    ('bac',        'BAC',         NULL,        0, 200, 'BAC');

-- 2) Fix typos in product_name ----------------------------------------------
-- Trigger update_product_timestamp will refresh updated_at automatically;
-- audit_products_update will log the rename via audit_log.

UPDATE products
   SET product_name = REPLACE(product_name, 'สแตนแลส', 'สแตนเลส')
 WHERE product_name LIKE '%สแตนแลส%';

UPDATE products
   SET product_name = REPLACE(product_name, 'โครเมี่ยม', 'โครเมียม')
 WHERE product_name LIKE '%โครเมี่ยม%';

-- Record migration -----------------------------------------------------------

INSERT INTO applied_migrations(filename, applied_at)
VALUES ('027_brands_and_typos.sql', datetime('now','localtime'));

COMMIT;
