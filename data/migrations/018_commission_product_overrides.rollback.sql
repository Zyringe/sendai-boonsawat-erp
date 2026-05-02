-- 018_commission_product_overrides.rollback.sql
BEGIN;
DROP INDEX IF EXISTS idx_cpo_product;
DROP TABLE IF EXISTS commission_product_overrides;
COMMIT;
