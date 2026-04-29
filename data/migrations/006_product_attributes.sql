-- 006_product_attributes.sql
-- Phase C3 of the schema refactor.
-- Adds a flexible key/value attribute table for product specs (size,
-- color, finish, model_no, material, etc.) so product_name no longer
-- needs to encode every detail as a free-text string.
--
-- No backfill — too noisy to regex-extract reliably from existing
-- product_name strings. User will populate as they edit each product
-- (or via a future bulk-import workflow).
--
-- Apply:
--   sqlite3 .../inventory.db < .../migrations/006_product_attributes.sql
-- Rollback: 006_product_attributes.rollback.sql

BEGIN;

CREATE TABLE product_attributes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id    INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    attr_key      TEXT    NOT NULL,    -- e.g. 'size', 'color', 'finish', 'model_no', 'material'
    attr_value    TEXT    NOT NULL,    -- e.g. '4นิ้ว', 'ขาว', 'CR', '#230', 'สแตนเลส'
    display_order INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    UNIQUE(product_id, attr_key)
);

CREATE INDEX idx_product_attributes_product ON product_attributes(product_id);
CREATE INDEX idx_product_attributes_key_val ON product_attributes(attr_key, attr_value);

COMMIT;
