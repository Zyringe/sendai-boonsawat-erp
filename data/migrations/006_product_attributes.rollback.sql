-- 006_product_attributes.rollback.sql
-- Rolls back 006_product_attributes.sql.
-- Drops the product_attributes table (any data captured is lost).

BEGIN;
DROP INDEX IF EXISTS idx_product_attributes_key_val;
DROP INDEX IF EXISTS idx_product_attributes_product;
DROP TABLE IF EXISTS product_attributes;
COMMIT;
