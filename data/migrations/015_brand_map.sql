-- 015_brand_map.sql
-- Adds an authoritative product → brand lookup so commission no longer
-- depends solely on regex against product_name.
--
-- Source: Put's brand.csv export (1,305 product names tagged with one of
-- 62 brand strings). Loaded by scripts/load_brand_map.py.
--
-- Three brands are own (per Put 2026-05-02):
--     SENDAI, GOLDEN LION, A-SPEC
-- (and "SD" inside any product name also maps to Sendai — handled by the
--  fallback regex in commission.py for product names absent from the map.)
--
-- Also adds a brand_kind cache column on express_sales so commission
-- queries can filter by 'own' / 'third_party' without a JOIN. Backfilled
-- by the loader: lookup wins; regex fallback fills the rest.
--
-- Apply:
--   sqlite3 .../inventory.db < .../015_brand_map.sql
-- Rollback: 015_brand_map.rollback.sql

BEGIN;

CREATE TABLE product_brand_map (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    product_name  TEXT    UNIQUE NOT NULL,
    brand_name    TEXT    NOT NULL,                 -- as recorded in brand.csv
    is_own        INTEGER NOT NULL DEFAULT 0 CHECK(is_own IN (0,1)),
    note          TEXT,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE INDEX idx_pbm_brand ON product_brand_map(brand_name);

ALTER TABLE express_sales ADD COLUMN brand_kind TEXT;
CREATE INDEX idx_express_sales_brandkind ON express_sales(brand_kind);

COMMIT;
