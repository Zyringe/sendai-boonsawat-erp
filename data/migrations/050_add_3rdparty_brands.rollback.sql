-- 050_add_3rdparty_brands.rollback.sql

BEGIN;

DELETE FROM brands WHERE short_code IN ('PHO','DRAG','RICE','CROC','HCOP','KC','MOSU');

DELETE FROM applied_migrations WHERE filename = '050_add_3rdparty_brands.sql';

COMMIT;
