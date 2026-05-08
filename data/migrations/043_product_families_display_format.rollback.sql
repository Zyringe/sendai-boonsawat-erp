-- 043_product_families_display_format.rollback.sql

BEGIN;

DROP TRIGGER IF EXISTS product_families_display_format_check_update;
DROP TRIGGER IF EXISTS product_families_display_format_check_insert;

ALTER TABLE product_families DROP COLUMN catalogue_label;
ALTER TABLE product_families DROP COLUMN display_format;

DELETE FROM applied_migrations
 WHERE filename = '043_product_families_display_format.sql';

COMMIT;
