-- 026_color_packaging_price_tiers.rollback.sql
--
-- WARNING: drops product_price_tiers + color_finish_codes tables, removes
-- products.color_code and products.packaging columns. Any data populated
-- since migration runs will be lost.

BEGIN;

-- product_price_tiers
DROP TRIGGER IF EXISTS audit_product_price_tiers_delete;
DROP TRIGGER IF EXISTS audit_product_price_tiers_update;
DROP TRIGGER IF EXISTS audit_product_price_tiers_insert;
DROP TRIGGER IF EXISTS update_product_price_tiers_timestamp;
DROP INDEX  IF EXISTS idx_product_price_tiers_product;
DROP TABLE  IF EXISTS product_price_tiers;

-- products.packaging
DROP TRIGGER IF EXISTS products_packaging_check_update;
DROP TRIGGER IF EXISTS products_packaging_check_insert;
DROP INDEX   IF EXISTS idx_products_packaging;
ALTER TABLE products DROP COLUMN packaging;

-- products.color_code
DROP INDEX IF EXISTS idx_products_color_code;
ALTER TABLE products DROP COLUMN color_code;

-- color_finish_codes
DROP TRIGGER IF EXISTS update_color_finish_codes_timestamp;
DROP TABLE   IF EXISTS color_finish_codes;

DELETE FROM applied_migrations WHERE filename = '026_color_packaging_price_tiers.sql';

COMMIT;
