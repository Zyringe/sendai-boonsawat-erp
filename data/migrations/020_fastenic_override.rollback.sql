-- 020_fastenic_override.rollback.sql
BEGIN;
DELETE FROM commission_overrides
 WHERE brand_id = (SELECT id FROM brands WHERE code = 'fastenic');
UPDATE products SET brand_id = NULL
 WHERE brand_id = (SELECT id FROM brands WHERE code = 'fastenic');
DELETE FROM brands WHERE code = 'fastenic' AND note = 'auto-seeded for commission override';
COMMIT;
