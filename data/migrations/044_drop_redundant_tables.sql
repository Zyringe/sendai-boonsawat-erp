-- 044_drop_redundant_tables.sql
-- Drop two tables that are functionally superseded by current schema.
--
-- product_attributes
--   Designed to hold key-value attributes (size, color, finish, model_no, etc.)
--   per product. Migration 033 added these as first-class columns on products
--   (model, size, color_code, packaging, condition, pack_variant, sub_category).
--   Table never had any rows; no code reads or writes it; was only present
--   in the master-only upload whitelist.
--
-- product_brand_map
--   Pre-FK lookup mapping product_name (TEXT, UNIQUE) → brand_name. Replaced
--   by `products.brand_id → brands.id` FK relationship. Has 1,306 rows of
--   stale data (no longer kept in sync — rename pass invalidated UNIQUE keys).
--   commission.py only mentions it in a comment; load_brand_map.py is a
--   one-time loader that's no longer run.
--
-- Apply:    sqlite3 .../inventory.db < .../044_drop_redundant_tables.sql
-- Rollback: 044_drop_redundant_tables.rollback.sql

BEGIN;

DROP INDEX IF EXISTS idx_product_attributes_product;
DROP INDEX IF EXISTS idx_product_attributes_key_val;
DROP TABLE IF EXISTS product_attributes;

DROP INDEX IF EXISTS idx_pbm_brand;
DROP TABLE IF EXISTS product_brand_map;

INSERT INTO applied_migrations(filename, applied_at)
VALUES ('044_drop_redundant_tables.sql', datetime('now','localtime'));

COMMIT;
