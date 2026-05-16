-- 046_add_material_column.sql
-- Add `material` column to products. Used to differentiate products that
-- currently collide on sku_code (e.g., ลูกกลิ้งเคมี vs ลูกกลิ้งขนแกะ, ตลับเมตรหุ้มยาง
-- vs ตลับเมตรพลาสติก, etc.). Audit on 2026-05-11 identified 51 disambiguator rows
-- where the differentiator is material.
--
-- Values populated post-migration via script + user review CSV.
--
-- Apply:    sqlite3 .../inventory.db < .../046_add_material_column.sql
-- Rollback: 046_add_material_column.rollback.sql

BEGIN;

ALTER TABLE products ADD COLUMN material TEXT;

INSERT INTO applied_migrations(filename, applied_at)
VALUES ('046_add_material_column.sql', datetime('now','localtime'));

COMMIT;
