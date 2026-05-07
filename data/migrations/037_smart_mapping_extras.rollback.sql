-- 037_smart_mapping_extras.rollback.sql

BEGIN;

ALTER TABLE pending_product_suggestions DROP COLUMN unit_conversion_ratio;
ALTER TABLE pending_product_suggestions DROP COLUMN bsn_unit;
ALTER TABLE pending_product_suggestions DROP COLUMN packaging_other;
ALTER TABLE pending_product_suggestions DROP COLUMN color_code_other;
ALTER TABLE pending_product_suggestions DROP COLUMN brand_other_name;

ALTER TABLE product_code_mapping DROP COLUMN ignore_reason;

DELETE FROM applied_migrations WHERE filename = '037_smart_mapping_extras.sql';

COMMIT;
