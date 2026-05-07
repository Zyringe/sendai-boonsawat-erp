-- 033_product_structured_columns.rollback.sql
-- Rollback for 033_product_structured_columns.sql
--
-- Drops the products_full VIEW and the 5 added columns.
-- WARNING: dropping columns loses all populated structured data.
-- Take a backup first.

BEGIN;

DROP VIEW IF EXISTS products_full;

ALTER TABLE products DROP COLUMN pack_variant;
ALTER TABLE products DROP COLUMN condition;
ALTER TABLE products DROP COLUMN size;
ALTER TABLE products DROP COLUMN model;
ALTER TABLE products DROP COLUMN series;

DELETE FROM applied_migrations
 WHERE filename = '033_product_structured_columns.sql';

COMMIT;
