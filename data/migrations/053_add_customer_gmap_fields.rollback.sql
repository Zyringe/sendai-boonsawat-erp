-- 053_add_customer_gmap_fields.rollback.sql

BEGIN;

ALTER TABLE customers DROP COLUMN plus_code;
ALTER TABLE customers DROP COLUMN gmap_name;
ALTER TABLE customers DROP COLUMN gmap_address;

DELETE FROM applied_migrations WHERE filename = '053_add_customer_gmap_fields.sql';

COMMIT;
