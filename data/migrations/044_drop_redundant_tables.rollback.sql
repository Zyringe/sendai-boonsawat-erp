-- 044_drop_redundant_tables.rollback.sql
-- WARNING: data lost forever — these tables are recreated EMPTY.
-- Original product_brand_map data (1,306 rows) is gone after the apply.

BEGIN;

CREATE TABLE product_attributes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id    INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    attr_key      TEXT    NOT NULL,
    attr_value    TEXT    NOT NULL,
    display_order INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    UNIQUE(product_id, attr_key)
);
CREATE INDEX idx_product_attributes_product ON product_attributes(product_id);
CREATE INDEX idx_product_attributes_key_val ON product_attributes(attr_key, attr_value);

CREATE TABLE product_brand_map (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    product_name  TEXT    UNIQUE NOT NULL,
    brand_name    TEXT    NOT NULL,
    is_own        INTEGER NOT NULL DEFAULT 0 CHECK(is_own IN (0,1)),
    note          TEXT,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX idx_pbm_brand ON product_brand_map(brand_name);

DELETE FROM applied_migrations WHERE filename = '044_drop_redundant_tables.sql';

COMMIT;
