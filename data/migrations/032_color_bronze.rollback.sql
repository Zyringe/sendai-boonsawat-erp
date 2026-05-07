-- 032_color_bronze.rollback.sql

BEGIN;

DELETE FROM color_finish_codes WHERE code = 'BZ';

DELETE FROM applied_migrations WHERE filename = '032_color_bronze.sql';

COMMIT;
