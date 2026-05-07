-- 039_sku_codes_and_categories.sql
-- Add structured sku_code (text identifier) + sub_category (granular Thai
-- type text) + categories.short_code (3-4 char ASCII for sku_code prefix).
--
-- Design (locked 2026-05-08):
--   • products.sku stays INTEGER (existing identifier, all FKs use products.id)
--   • products.sku_code is the new TEXT identifier for catalog/customer use
--     Format: <CAT>-<BRAND>-<MODEL>-<SIZE>-<COLOR>
--     (segments omit-when-missing; fallback INT-<sku> if everything is NULL)
--   • products.sku_code_locked = 0 (auto-regen allowed) / 1 (user-edited, do not auto-regen)
--   • products.sub_category = granular Thai text from CSV (e.g. "กลอนมะยม"),
--     non-FK, used for filtering/search. Maps to broad category_id via
--     curated mapping (see backfill_subcategory.py + map_subcategory_to_category.py).
--   • categories.short_code = 3-4 char ASCII for sku_code prefix (e.g. BLT, HNG, KNB)
--
-- Apply:    sqlite3 .../inventory.db < .../039_sku_codes_and_categories.sql
-- Rollback: 039_sku_codes_and_categories.rollback.sql

BEGIN;

-- 1) categories.short_code — populated by Put-curated review during backfill
ALTER TABLE categories ADD COLUMN short_code TEXT;
CREATE UNIQUE INDEX idx_categories_short_code ON categories(short_code) WHERE short_code IS NOT NULL;

-- 2) products.sub_category — granular Thai type text from CSV
ALTER TABLE products ADD COLUMN sub_category TEXT;
CREATE INDEX idx_products_sub_category ON products(sub_category);

-- 3) products.sku_code + lock flag
ALTER TABLE products ADD COLUMN sku_code TEXT;
ALTER TABLE products ADD COLUMN sku_code_locked INTEGER NOT NULL DEFAULT 0
                              CHECK(sku_code_locked IN (0, 1));
CREATE UNIQUE INDEX idx_products_sku_code ON products(sku_code) WHERE sku_code IS NOT NULL;

INSERT INTO applied_migrations(filename, applied_at)
VALUES ('039_sku_codes_and_categories.sql', datetime('now','localtime'));

COMMIT;
