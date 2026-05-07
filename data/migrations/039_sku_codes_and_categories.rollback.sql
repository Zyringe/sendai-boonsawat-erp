-- 039_sku_codes_and_categories.rollback.sql

BEGIN;

DROP INDEX IF EXISTS idx_products_sku_code;
DROP INDEX IF EXISTS idx_products_sub_category;
DROP INDEX IF EXISTS idx_categories_short_code;

ALTER TABLE products DROP COLUMN sku_code_locked;
ALTER TABLE products DROP COLUMN sku_code;
ALTER TABLE products DROP COLUMN sub_category;
ALTER TABLE categories DROP COLUMN short_code;

DELETE FROM applied_migrations WHERE filename = '039_sku_codes_and_categories.sql';

COMMIT;
