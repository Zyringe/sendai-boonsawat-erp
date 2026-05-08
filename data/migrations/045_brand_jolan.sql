-- 045_brand_jolan.sql
-- Add 'โจลัน' (Jolan) as a new third-party brand surfaced during 2026-05-08
-- catalog review (products like 'ดจ.ปูน โจลัน 1/4x4').
--
-- Apply:    sqlite3 .../inventory.db < .../045_brand_jolan.sql
-- Rollback: 045_brand_jolan.rollback.sql

BEGIN;

INSERT INTO brands(code, name, name_th, is_own_brand, sort_order, short_code)
VALUES ('jolan', 'JOLAN', 'โจลัน', 0, 100, 'JOLAN');

INSERT INTO applied_migrations(filename, applied_at)
VALUES ('045_brand_jolan.sql', datetime('now','localtime'));

COMMIT;
