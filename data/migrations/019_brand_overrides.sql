-- 019_brand_overrides.sql
-- Extend commission overrides to support BRAND-level rules + percentage
-- rates (not just per-unit fixed amounts).
--
-- Per Put 2026-05-02: "commission ของสินค้าที่เป็นยี่ห้อ Somic ต้อง
-- เป็น 2%". SOMIC has 23 Sendy products and ~244 Express sales lines —
-- a per-product seed would be tedious + brittle. A brand-level rule
-- (brand_id=SOMIC, custom_rate_pct=2.0) covers them all.
--
-- Renamed table: commission_product_overrides → commission_overrides.
-- New columns:
--   brand_id          INTEGER NULL   - apply to every product of this brand
--   custom_rate_pct   REAL    NULL   - apply percentage of net (vs fixed/unit)
--   apply_when_price_lte is now NULLABLE (= no upper bound)
--
-- Constraint: at least one of product_id or brand_id must be set;
--             at least one of fixed_per_unit or custom_rate_pct must be set.
-- Priority (resolved in commission.py): product-level > brand-level.
--
-- Apply:    sqlite3 .../inventory.db < .../019_brand_overrides.sql
-- Rollback: 019_brand_overrides.rollback.sql

BEGIN;

CREATE TABLE commission_overrides (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id            INTEGER REFERENCES products(id),
    brand_id              INTEGER REFERENCES brands(id),
    salesperson_code      TEXT,
    fixed_per_unit        REAL,
    custom_rate_pct       REAL,
    apply_when_price_gt   REAL    NOT NULL DEFAULT 0,
    apply_when_price_lte  REAL,
    is_active             INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
    note                  TEXT,
    effective_from        TEXT    NOT NULL DEFAULT (date('now')),
    created_at            TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at            TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    CHECK ((product_id IS NOT NULL) OR (brand_id IS NOT NULL)),
    CHECK ((fixed_per_unit IS NOT NULL) OR (custom_rate_pct IS NOT NULL))
);

CREATE INDEX idx_co_product ON commission_overrides(product_id);
CREATE INDEX idx_co_brand   ON commission_overrides(brand_id);

-- Migrate the single existing row (product 398 / แผ่นตัด สิงห์ทอง 14")
INSERT INTO commission_overrides
    (product_id, fixed_per_unit, apply_when_price_gt, apply_when_price_lte,
     salesperson_code, is_active, note, effective_from, created_at, updated_at)
SELECT product_id, fixed_per_unit, apply_when_price_gt, apply_when_price_lte,
       salesperson_code, is_active, note, effective_from, created_at, updated_at
FROM commission_product_overrides;

DROP TABLE commission_product_overrides;

-- Backfill: assign SOMIC brand to every product whose name contains 'SOMIC'.
UPDATE products SET brand_id = (SELECT id FROM brands WHERE code = 'somic')
 WHERE brand_id IS NULL AND product_name LIKE '%SOMIC%';

-- Brand-level override: SOMIC = 2% on net, every salesperson, no price gate.
INSERT INTO commission_overrides (brand_id, custom_rate_pct, note)
VALUES (
    (SELECT id FROM brands WHERE code = 'somic'),
    2.0,
    'ยี่ห้อ SOMIC: 2% ทุกรายการ (Put 2026-05-02)'
);

-- Refresh brand_kind cache for the SOMIC products we just labelled
-- (brand SOMIC has is_own_brand=0 → third_party).
UPDATE express_sales
   SET brand_kind = 'third_party'
 WHERE product_code IN (
       SELECT bsn_code FROM product_code_mapping
        WHERE product_id IN (SELECT id FROM products WHERE brand_id = (SELECT id FROM brands WHERE code='somic'))
   );

COMMIT;
