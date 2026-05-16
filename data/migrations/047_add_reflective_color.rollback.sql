-- 047_add_reflective_color.rollback.sql

BEGIN;

DELETE FROM color_finish_codes WHERE code = 'REF';

DELETE FROM applied_migrations WHERE filename = '047_add_reflective_color.sql';

COMMIT;
