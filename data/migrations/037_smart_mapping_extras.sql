-- 037_smart_mapping_extras.sql
-- Round-2 enhancements to the smart-suggest BSN mapping flow:
--   * Free-text overrides for Brand/Color/Packaging when the dropdown
--     doesn't have what staff needs ("พิมพ์เอง" mode in modal Card B).
--   * BSN unit + conversion ratio captured when staging a new SKU so the
--     unit_conversions row is auto-created at approve time
--     (e.g. BSN "โหล" → product unit "ตัว", ratio = 12).
--   * Skip reason on product_code_mapping for the new "Card C" path
--     (e.g. "BSN code = ค่าขนส่ง not stock").
--
-- Apply:    sqlite3 .../inventory.db < .../037_smart_mapping_extras.sql
-- Rollback: 037_smart_mapping_extras.rollback.sql

BEGIN;

-- pending_product_suggestions extras
ALTER TABLE pending_product_suggestions ADD COLUMN brand_other_name      TEXT;
ALTER TABLE pending_product_suggestions ADD COLUMN color_code_other      TEXT;
ALTER TABLE pending_product_suggestions ADD COLUMN packaging_other       TEXT;
ALTER TABLE pending_product_suggestions ADD COLUMN bsn_unit              TEXT;
ALTER TABLE pending_product_suggestions ADD COLUMN unit_conversion_ratio REAL;

-- product_code_mapping skip-reason
ALTER TABLE product_code_mapping ADD COLUMN ignore_reason TEXT;

INSERT INTO applied_migrations(filename, applied_at)
VALUES ('037_smart_mapping_extras.sql', datetime('now','localtime'));

COMMIT;
