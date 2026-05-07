-- 033_product_structured_columns.sql
-- Add structured naming columns to products + create products_full VIEW.
--
-- Reason: After the 2026-05-06 product-name rebuild pass, every SKU has been
-- parsed into 13 columns (sku, product_name, category, series, brand, model,
-- size, color_th, color_code, packaging, condition, pack_variant, proposed_name).
-- Of those, brand/category/color_th/color_code/packaging are already represented
-- (brand_id, category_id FK + color_code FK + packaging col). The remaining
-- 5 — series, model, size, condition, pack_variant — are NOT in the schema
-- and need persistent columns so SKUs are queryable by spec without parsing
-- product_name strings at query time.
--
-- products_full VIEW exposes all 10 spec columns in one row (joining brands,
-- categories, color_finish_codes) for query-time convenience. Underlying
-- writes still go through products / brands / categories / color_finish_codes.
--
-- Apply:    sqlite3 .../inventory.db < .../033_product_structured_columns.sql
-- Rollback: 033_product_structured_columns.rollback.sql

BEGIN;

-- 5 new nullable text columns on products.
ALTER TABLE products ADD COLUMN series       TEXT;
ALTER TABLE products ADD COLUMN model        TEXT;
ALTER TABLE products ADD COLUMN size         TEXT;
ALTER TABLE products ADD COLUMN condition    TEXT;
ALTER TABLE products ADD COLUMN pack_variant TEXT;

-- products_full: spec-rich virtual table joining FK lookups.
-- Writes still go through products (and the FK target tables); this is
-- read-only convenience for catalog/reporting/spec-comparison work.
DROP VIEW IF EXISTS products_full;
CREATE VIEW products_full AS
SELECT
    p.id,
    p.sku,
    p.product_name,
    c.name_th        AS category,
    p.series,
    b.name           AS brand,
    b.short_code     AS brand_short_code,
    b.is_own_brand   AS is_own_brand,
    p.model,
    p.size,
    cf.name_th       AS color_th,
    p.color_code,
    p.packaging,
    p.condition,
    p.pack_variant,
    p.family_id,
    p.unit_type,
    p.units_per_carton,
    p.units_per_box,
    p.cost_price,
    p.base_sell_price,
    p.hard_to_sell,
    p.is_active,
    COALESCE(s.quantity, 0) AS stock,
    p.shopee_stock,
    p.lazada_stock,
    p.created_at,
    p.updated_at
FROM products p
LEFT JOIN brands               b  ON b.id   = p.brand_id
LEFT JOIN categories           c  ON c.id   = p.category_id
LEFT JOIN color_finish_codes   cf ON cf.code = p.color_code
LEFT JOIN stock_levels         s  ON s.product_id = p.id;

INSERT INTO applied_migrations(filename, applied_at)
VALUES ('033_product_structured_columns.sql', datetime('now','localtime'));

COMMIT;
