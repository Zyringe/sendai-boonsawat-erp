-- 024_listing_bundles.sql
-- Bundle composition for ecommerce_listings: a single platform sale may
-- deduct stock from multiple internal products (giveaway/freebie pairs).
--
-- Example: shopee listing 26 ("ฝาครอบ + แม่กุญแจแขวน") sells 1 unit →
-- deduct 1× sku 251 (main) + 1× sku 252 (giveaway). The main link stays in
-- ecommerce_listings.product_id; this table holds the secondary components.
--
-- Apply:    sqlite3 .../inventory.db < .../024_listing_bundles.sql
-- Rollback: 024_listing_bundles.rollback.sql

BEGIN;

CREATE TABLE listing_bundles (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id            INTEGER NOT NULL REFERENCES ecommerce_listings(id) ON DELETE CASCADE,
    component_product_id  INTEGER NOT NULL REFERENCES products(id),
    qty_per_sale          REAL    NOT NULL DEFAULT 1 CHECK (qty_per_sale > 0),
    note                  TEXT,
    created_at            TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    UNIQUE(listing_id, component_product_id)
);

CREATE INDEX idx_listing_bundles_listing ON listing_bundles(listing_id);

CREATE TRIGGER audit_listing_bundles_insert
AFTER INSERT ON listing_bundles
BEGIN
    INSERT INTO audit_log (table_name, row_id, action, changed_fields)
    VALUES ('listing_bundles', NEW.id, 'INSERT',
        json_object(
            'listing_id',           NEW.listing_id,
            'component_product_id', NEW.component_product_id,
            'qty_per_sale',         NEW.qty_per_sale,
            'note',                 NEW.note
        ));
END;

CREATE TRIGGER audit_listing_bundles_update
AFTER UPDATE ON listing_bundles
WHEN (
       OLD.listing_id           IS NOT NEW.listing_id
    OR OLD.component_product_id IS NOT NEW.component_product_id
    OR OLD.qty_per_sale         IS NOT NEW.qty_per_sale
    OR OLD.note                 IS NOT NEW.note
)
BEGIN
    INSERT INTO audit_log (table_name, row_id, action, changed_fields)
    SELECT 'listing_bundles', NEW.id, 'UPDATE',
           json_group_object(field, json_array(old_v, new_v))
    FROM (
                  SELECT 'listing_id'           AS field, OLD.listing_id           AS old_v, NEW.listing_id           AS new_v WHERE OLD.listing_id           IS NOT NEW.listing_id
        UNION ALL SELECT 'component_product_id',         OLD.component_product_id,         NEW.component_product_id         WHERE OLD.component_product_id IS NOT NEW.component_product_id
        UNION ALL SELECT 'qty_per_sale',                 OLD.qty_per_sale,                 NEW.qty_per_sale                 WHERE OLD.qty_per_sale         IS NOT NEW.qty_per_sale
        UNION ALL SELECT 'note',                         OLD.note,                         NEW.note                         WHERE OLD.note                 IS NOT NEW.note
    );
END;

CREATE TRIGGER audit_listing_bundles_delete
BEFORE DELETE ON listing_bundles
BEGIN
    INSERT INTO audit_log (table_name, row_id, action, changed_fields)
    VALUES ('listing_bundles', OLD.id, 'DELETE',
        json_object(
            'listing_id',           OLD.listing_id,
            'component_product_id', OLD.component_product_id,
            'qty_per_sale',         OLD.qty_per_sale,
            'note',                 OLD.note
        ));
END;

COMMIT;
