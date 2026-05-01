-- 015_brand_map.rollback.sql
BEGIN;
DROP INDEX IF EXISTS idx_express_sales_brandkind;
ALTER TABLE express_sales DROP COLUMN brand_kind;
DROP INDEX IF EXISTS idx_pbm_brand;
DROP TABLE IF EXISTS product_brand_map;
COMMIT;
