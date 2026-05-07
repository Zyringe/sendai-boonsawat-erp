-- 025_product_families.rollback.sql
--
-- WARNING: This DROPS the product_images and product_families tables and
-- removes products.family_id + brands.short_code. Any data populated since
-- migration runs will be lost.
--
-- Apply: sqlite3 .../inventory.db < .../025_product_families.rollback.sql

BEGIN;

-- Drop triggers first (SQLite drops them automatically with the table, but
-- we list them explicitly for clarity).
DROP TRIGGER IF EXISTS audit_product_images_delete;
DROP TRIGGER IF EXISTS audit_product_images_update;
DROP TRIGGER IF EXISTS audit_product_images_insert;
DROP TRIGGER IF EXISTS update_product_images_timestamp;

DROP TRIGGER IF EXISTS audit_product_families_delete;
DROP TRIGGER IF EXISTS audit_product_families_update;
DROP TRIGGER IF EXISTS audit_product_families_insert;
DROP TRIGGER IF EXISTS update_product_families_timestamp;

DROP INDEX IF EXISTS idx_product_images_sku;
DROP INDEX IF EXISTS idx_product_images_family;
DROP TABLE IF EXISTS product_images;

-- products.family_id — SQLite supports DROP COLUMN since 3.35 (2021).
DROP INDEX IF EXISTS idx_products_family;
ALTER TABLE products DROP COLUMN family_id;

DROP INDEX IF EXISTS idx_product_families_brand;
DROP TABLE IF EXISTS product_families;

-- brands.short_code
DROP INDEX IF EXISTS idx_brands_short_code;
ALTER TABLE brands DROP COLUMN short_code;

DELETE FROM applied_migrations WHERE filename = '025_product_families.sql';

COMMIT;
