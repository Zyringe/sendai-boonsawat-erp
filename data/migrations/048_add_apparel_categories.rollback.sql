-- 048_add_apparel_categories.rollback.sql

BEGIN;

DELETE FROM categories WHERE short_code IN ('APR','SHI','UMB','TLT','RUB');

DELETE FROM applied_migrations WHERE filename = '048_add_apparel_categories.sql';

COMMIT;
