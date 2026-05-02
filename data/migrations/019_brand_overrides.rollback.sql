-- 019_brand_overrides.rollback.sql
BEGIN;

CREATE TABLE commission_product_overrides (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES products(id),
    fixed_per_unit REAL NOT NULL,
    apply_when_price_gt REAL NOT NULL DEFAULT 0,
    apply_when_price_lte REAL NOT NULL,
    salesperson_code TEXT,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
    note TEXT,
    effective_from TEXT NOT NULL DEFAULT (date('now')),
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX idx_cpo_product ON commission_product_overrides(product_id);

INSERT INTO commission_product_overrides
    (product_id, fixed_per_unit, apply_when_price_gt, apply_when_price_lte,
     salesperson_code, is_active, note, effective_from, created_at, updated_at)
SELECT product_id, fixed_per_unit, apply_when_price_gt, apply_when_price_lte,
       salesperson_code, is_active, note, effective_from, created_at, updated_at
FROM commission_overrides
WHERE product_id IS NOT NULL AND fixed_per_unit IS NOT NULL AND apply_when_price_lte IS NOT NULL;

DROP INDEX IF EXISTS idx_co_brand;
DROP INDEX IF EXISTS idx_co_product;
DROP TABLE IF EXISTS commission_overrides;

COMMIT;
