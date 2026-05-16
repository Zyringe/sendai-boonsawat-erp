-- 046_add_material_column.rollback.sql
-- Drop the material column added by 046.

BEGIN;

ALTER TABLE products DROP COLUMN material;

DELETE FROM applied_migrations WHERE filename = '046_add_material_column.sql';

COMMIT;
