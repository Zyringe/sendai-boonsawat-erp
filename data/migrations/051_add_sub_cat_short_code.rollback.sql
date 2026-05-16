-- 051_add_sub_cat_short_code.rollback.sql

BEGIN;

ALTER TABLE products DROP COLUMN sub_category_short_code;

DELETE FROM applied_migrations WHERE filename = '051_add_sub_cat_short_code.sql';

COMMIT;
