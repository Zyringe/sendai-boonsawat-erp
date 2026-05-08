-- 045_brand_jolan.rollback.sql

BEGIN;
DELETE FROM brands WHERE code = 'jolan';
DELETE FROM applied_migrations WHERE filename = '045_brand_jolan.sql';
COMMIT;
