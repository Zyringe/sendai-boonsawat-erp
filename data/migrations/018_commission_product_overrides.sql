-- 018_commission_product_overrides.sql
-- Per-product commission rule overrides — beats the tier rate for
-- specific products under price conditions.
--
-- Per Put 2026-05-02: "แผ่นตัด สิงห์ทอง 14นิ้ว ดำ (2ใย) ที่ขายลูกค้า
-- 95 บาท เซลล์จะได้ commission ที่ 5 บาทต่อใบ แทนที่จะเป็น 10%".
-- Conditions:
--   - if unit_price = 0 (ของแถม)              → no commission
--   - if 0 < unit_price <= 95                  → ฿5 / unit (override)
--   - if unit_price > 95                       → fall back to tier rate
--                                                (own = 10%, third = 5%)
--
-- Schema is generic enough to support more products later via the
-- /commission UI (TBD).
--
-- Apply:    sqlite3 .../inventory.db < .../018_commission_product_overrides.sql
-- Rollback: 018_commission_product_overrides.rollback.sql

BEGIN;

CREATE TABLE commission_product_overrides (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id            INTEGER NOT NULL REFERENCES products(id),
    fixed_per_unit        REAL    NOT NULL,                 -- THB per unit; commission = qty × this
    apply_when_price_gt   REAL    NOT NULL DEFAULT 0,       -- override only if unit_price > this (default 0 → excludes freebies)
    apply_when_price_lte  REAL    NOT NULL,                 -- and unit_price <= this
    salesperson_code      TEXT,                              -- NULL = applies to every salesperson
    is_active             INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
    note                  TEXT,
    effective_from        TEXT    NOT NULL DEFAULT (date('now')),
    created_at            TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at            TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE INDEX idx_cpo_product ON commission_product_overrides(product_id);

INSERT INTO commission_product_overrides
    (product_id, fixed_per_unit, apply_when_price_gt, apply_when_price_lte, note)
VALUES
    (398, 5.0, 0.0, 95.0,
     'แผ่นตัด สิงห์ทอง 14" ดำ (2ใย): ฿5/ใบ ถ้าราคา ≤ ฿95 (กำไรบาง). ราคา > 95 → 10% ตามปกติ. ราคา 0 (แถม) → ไม่มี commission.');

COMMIT;
