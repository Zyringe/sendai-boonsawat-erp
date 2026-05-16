-- 051_add_sub_cat_short_code.sql
-- Add `sub_category_short_code` column to products. Used by sku_code generator
-- to include sub-category as a single segment (e.g., MYM, BOWFINE, BCTGRA).
-- Pairs with sub_category (Thai display name).
--
-- Apply:    sqlite3 .../inventory.db < .../051_add_sub_cat_short_code.sql
-- Rollback: 051_add_sub_cat_short_code.rollback.sql

BEGIN;

ALTER TABLE products ADD COLUMN sub_category_short_code TEXT;

INSERT INTO applied_migrations(filename, applied_at)
VALUES ('051_add_sub_cat_short_code.sql', datetime('now','localtime'));

COMMIT;
