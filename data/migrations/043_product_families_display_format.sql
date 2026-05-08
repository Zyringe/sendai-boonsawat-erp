-- 043_product_families_display_format.sql
-- Extend product_families table with display_format + catalogue_label.
--
-- Why: catalog rendering needs to know how to present a family of related
-- SKUs. Five display modes cover Put's three real-world cases (2026-05-08):
--
--   single           1 SKU → 1 card (default for solo products)
--                     E.g. คีมย้ำรีเวท #SD-111 (no variants)
--
--   pack_variants    Same product, only packaging differs.
--                     E.g. กลอนมะยม Sendai #230-6in AC ตัว vs แผง
--                     Render: 1 card with packaging toggle/badges
--
--   size_table       Same brand+model+color, multiple sizes.
--                     E.g. ดจ.โรตารี — sold in size table (price by size)
--                     Render: 1 card with size→price table
--
--   color_swatch     Same brand+model+size, multiple colors.
--                     Render: 1 card with color picker
--
--   matrix           Multiple sizes AND colors.
--                     E.g. กรอบจตุคาม with 5cm/7cm × ทอง/เงิน/อ่อน
--                     Render: 1 card with size×color price grid
--
-- catalogue_label is a free-text marketing label shown above the family
-- card (e.g. "ขายดี!", "Best Seller", "ราคาพิเศษ"). Optional.
--
-- products.family_id (FK, exists since mig 025) groups SKUs into families.
-- Population happens via build_family_review.py + apply_family_mapping.py
-- (next steps after this migration).
--
-- Apply:    sqlite3 .../inventory.db < .../043_product_families_display_format.sql
-- Rollback: 043_product_families_display_format.rollback.sql

BEGIN;

ALTER TABLE product_families ADD COLUMN display_format TEXT DEFAULT 'single';
ALTER TABLE product_families ADD COLUMN catalogue_label TEXT;

-- CHECK trigger to enforce display_format values (SQLite doesn't support
-- ALTER TABLE ADD CHECK, so we use BEFORE INSERT/UPDATE triggers).
CREATE TRIGGER product_families_display_format_check_insert
    BEFORE INSERT ON product_families
    WHEN NEW.display_format IS NOT NULL
         AND NEW.display_format NOT IN
             ('single', 'pack_variants', 'size_table', 'color_swatch', 'matrix')
    BEGIN
        SELECT RAISE(ABORT,
            'display_format must be NULL or one of: single, pack_variants, size_table, color_swatch, matrix');
    END;

CREATE TRIGGER product_families_display_format_check_update
    BEFORE UPDATE ON product_families
    WHEN NEW.display_format IS NOT NULL
         AND NEW.display_format NOT IN
             ('single', 'pack_variants', 'size_table', 'color_swatch', 'matrix')
    BEGIN
        SELECT RAISE(ABORT,
            'display_format must be NULL or one of: single, pack_variants, size_table, color_swatch, matrix');
    END;

INSERT INTO applied_migrations(filename, applied_at)
VALUES ('043_product_families_display_format.sql', datetime('now','localtime'));

COMMIT;
