-- 040_categories_short_codes_and_new.rollback.sql

BEGIN;

UPDATE categories SET short_code = NULL;
DELETE FROM categories WHERE code IN ('wrench', 'fitting');

DELETE FROM applied_migrations WHERE filename = '040_categories_short_codes_and_new.sql';

COMMIT;
