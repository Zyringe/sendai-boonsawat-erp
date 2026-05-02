-- 020_fastenic_override.sql
-- Brand-level commission override: Fastenic = 2% (same rule as SOMIC).
-- Per Put 2026-05-02: "commission Fastenic ก็ 2% เหมือน SOMIC".
--
-- Coverage: 8 Sendy products with "Fastenic" in name (none had a brand
-- assigned), 23 Express sales lines / ฿47,266 net.
--
-- Apply:    sqlite3 .../inventory.db < .../020_fastenic_override.sql
-- Rollback: 020_fastenic_override.rollback.sql

BEGIN;

-- 1. Seed the brand row if it doesn't already exist
INSERT INTO brands (code, name, is_own_brand, sort_order, note)
SELECT 'fastenic', 'Fastenic', 0, 100, 'auto-seeded for commission override'
 WHERE NOT EXISTS (SELECT 1 FROM brands WHERE code = 'fastenic');

-- 2. Assign brand_id=Fastenic to any Sendy product whose name mentions it
UPDATE products
   SET brand_id = (SELECT id FROM brands WHERE code = 'fastenic')
 WHERE brand_id IS NULL
   AND (product_name LIKE '%Fastenic%' OR product_name LIKE '%FASTENIC%');

-- 3. Brand-level override: 2% on net, every salesperson, no price gate
INSERT INTO commission_overrides (brand_id, custom_rate_pct, note)
VALUES (
    (SELECT id FROM brands WHERE code = 'fastenic'),
    2.0,
    'ยี่ห้อ Fastenic: 2% ทุกรายการ (Put 2026-05-02)'
);

-- 4. Refresh brand_kind cache for Fastenic products → third_party
UPDATE express_sales
   SET brand_kind = 'third_party'
 WHERE product_code IN (
       SELECT bsn_code FROM product_code_mapping
        WHERE product_id IN (SELECT id FROM products WHERE brand_id = (SELECT id FROM brands WHERE code='fastenic'))
   );

COMMIT;
