-- 004_brands_categories.rollback.sql
-- Rolls back 004_brands_categories.sql.
--
-- Drops the brand_id + category_id columns from products (SQLite ≥3.35
-- supports DROP COLUMN), drops the categories + brands tables.
--
-- Pre-flight:
--   1. Stop Flask app.
--   2. Backup: scripts/backup_db.sh
--   3. Confirm no other tables FK to brands/categories yet (this rollback
--      file assumes they don't — only products has those columns).

BEGIN;

DROP INDEX IF EXISTS idx_products_brand;
DROP INDEX IF EXISTS idx_products_category;

ALTER TABLE products DROP COLUMN brand_id;
ALTER TABLE products DROP COLUMN category_id;

DROP TABLE IF EXISTS categories;
DROP TABLE IF EXISTS brands;

COMMIT;
