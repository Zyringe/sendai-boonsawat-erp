-- 025_product_families.sql
-- Catalog grouping: many SKUs (different packaging / size / color) display
-- as ONE catalog card. Family is the catalog unit, not the SKU.
--
-- Adds:
--   1) brands.short_code      — ASCII uppercase prefix used in family_code
--   2) product_families       — catalog-level grouping
--   3) products.family_id     — nullable FK from products → families
--   4) product_images         — many-to-many photos (family-level + optional sku)
--
-- Why family is the catalog unit:
--   - One product (e.g. "บานพับสแตนเลส #170") may sell as แผง (1 SKU) AND ตัว
--     (another SKU). Customer thinks "1 product".
--   - Sizes / colors of same model also belong on one catalog card with a
--     size table (decision: scope = B / loose grouping).
--
-- Conventions enforced by application code, not schema:
--   - products.family_id is nullable. SKUs WITHOUT a family still appear in
--     catalog as a singleton card (1 SKU = 1 card). Family is for grouping
--     multi-SKU products only.
--   - product_images.image_path stores RELATIVE paths from the workspace
--     Design/ folder (e.g. 'Catalog/2026_extract/media/image170.png').
--     Never absolute; portability + repo-friendly.
--
-- Apply:    sqlite3 .../inventory.db < .../025_product_families.sql
-- Rollback: 025_product_families.rollback.sql

BEGIN;

-- 1) brands.short_code -------------------------------------------------------

ALTER TABLE brands ADD COLUMN short_code TEXT;
CREATE UNIQUE INDEX idx_brands_short_code
    ON brands(short_code) WHERE short_code IS NOT NULL;

UPDATE brands SET short_code = 'SD'    WHERE code = 'sendai';
UPDATE brands SET short_code = 'GL'    WHERE code = 'golden_lion';
UPDATE brands SET short_code = 'AS'    WHERE code = 'a_spec';
UPDATE brands SET short_code = 'META'  WHERE code = 'meta';
UPDATE brands SET short_code = 'EAGLE' WHERE code = 'eagle_one';
UPDATE brands SET short_code = 'TOA'   WHERE code = 'toa';
UPDATE brands SET short_code = 'SOMIC' WHERE code = 'somic';
UPDATE brands SET short_code = 'KING'  WHERE code = 'king_eagle';
UPDATE brands SET short_code = 'FAST'  WHERE code = 'fastenic';
UPDATE brands SET short_code = 'BRAVO' WHERE code = 'bravo';
UPDATE brands SET short_code = 'YOKO'  WHERE code = 'yokomo';
UPDATE brands SET short_code = 'SANWA' WHERE code = 'sanwa';
UPDATE brands SET short_code = 'SOLEX' WHERE code = 'solex';
UPDATE brands SET short_code = 'BAHCO' WHERE code = 'bahco';
UPDATE brands SET short_code = '3RD'   WHERE code = 'third_party';
UPDATE brands SET short_code = 'NN'    WHERE code = 'no_name';

-- 2) product_families --------------------------------------------------------

CREATE TABLE product_families (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    family_code  TEXT    UNIQUE NOT NULL,        -- e.g. 'SD-170', stable forever
    display_name TEXT    NOT NULL,                -- Thai, shown on catalog card
    brand_id     INTEGER REFERENCES brands(id),
    sort_order   INTEGER NOT NULL DEFAULT 100,
    note         TEXT,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at   TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE INDEX idx_product_families_brand ON product_families(brand_id);

CREATE TRIGGER update_product_families_timestamp
    AFTER UPDATE ON product_families
    BEGIN
        UPDATE product_families SET updated_at = datetime('now','localtime')
        WHERE id = NEW.id;
    END;

CREATE TRIGGER audit_product_families_insert
AFTER INSERT ON product_families
BEGIN
    INSERT INTO audit_log (table_name, row_id, action, changed_fields)
    VALUES ('product_families', NEW.id, 'INSERT',
        json_object(
            'family_code',  NEW.family_code,
            'display_name', NEW.display_name,
            'brand_id',     NEW.brand_id,
            'sort_order',   NEW.sort_order,
            'note',         NEW.note
        ));
END;

CREATE TRIGGER audit_product_families_update
AFTER UPDATE ON product_families
WHEN (
       OLD.family_code  IS NOT NEW.family_code
    OR OLD.display_name IS NOT NEW.display_name
    OR OLD.brand_id     IS NOT NEW.brand_id
    OR OLD.sort_order   IS NOT NEW.sort_order
    OR OLD.note         IS NOT NEW.note
)
BEGIN
    INSERT INTO audit_log (table_name, row_id, action, changed_fields)
    SELECT 'product_families', NEW.id, 'UPDATE',
           json_group_object(field, json_array(old_v, new_v))
    FROM (
                  SELECT 'family_code'  AS field, OLD.family_code  AS old_v, NEW.family_code  AS new_v WHERE OLD.family_code  IS NOT NEW.family_code
        UNION ALL SELECT 'display_name',          OLD.display_name,          NEW.display_name          WHERE OLD.display_name IS NOT NEW.display_name
        UNION ALL SELECT 'brand_id',              OLD.brand_id,              NEW.brand_id              WHERE OLD.brand_id     IS NOT NEW.brand_id
        UNION ALL SELECT 'sort_order',            OLD.sort_order,            NEW.sort_order            WHERE OLD.sort_order   IS NOT NEW.sort_order
        UNION ALL SELECT 'note',                  OLD.note,                  NEW.note                  WHERE OLD.note         IS NOT NEW.note
    );
END;

CREATE TRIGGER audit_product_families_delete
BEFORE DELETE ON product_families
BEGIN
    INSERT INTO audit_log (table_name, row_id, action, changed_fields)
    VALUES ('product_families', OLD.id, 'DELETE',
        json_object(
            'family_code',  OLD.family_code,
            'display_name', OLD.display_name,
            'brand_id',     OLD.brand_id
        ));
END;

-- 3) products.family_id ------------------------------------------------------

ALTER TABLE products ADD COLUMN family_id INTEGER REFERENCES product_families(id);
CREATE INDEX idx_products_family ON products(family_id);

-- 4) product_images ----------------------------------------------------------
--
-- family_id NOT NULL: every image belongs to a catalog card.
-- sku_id nullable: set only when the image is specifically for that SKU
--                  (e.g. shows the แผง packaging only). NULL = applies to
--                  all SKUs in the family.
-- presentation_tag: free text but seed values 'แผง','ตัว','หลัก','in-use'.

CREATE TABLE product_images (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    family_id        INTEGER NOT NULL REFERENCES product_families(id) ON DELETE CASCADE,
    sku_id           INTEGER REFERENCES products(id) ON DELETE SET NULL,
    image_path       TEXT    NOT NULL,
    presentation_tag TEXT,
    sort_order       INTEGER NOT NULL DEFAULT 100,
    note             TEXT,
    created_at       TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at       TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    UNIQUE(family_id, image_path)
);

CREATE INDEX idx_product_images_family ON product_images(family_id);
CREATE INDEX idx_product_images_sku    ON product_images(sku_id);

CREATE TRIGGER update_product_images_timestamp
    AFTER UPDATE ON product_images
    BEGIN
        UPDATE product_images SET updated_at = datetime('now','localtime')
        WHERE id = NEW.id;
    END;

CREATE TRIGGER audit_product_images_insert
AFTER INSERT ON product_images
BEGIN
    INSERT INTO audit_log (table_name, row_id, action, changed_fields)
    VALUES ('product_images', NEW.id, 'INSERT',
        json_object(
            'family_id',        NEW.family_id,
            'sku_id',           NEW.sku_id,
            'image_path',       NEW.image_path,
            'presentation_tag', NEW.presentation_tag,
            'sort_order',       NEW.sort_order
        ));
END;

CREATE TRIGGER audit_product_images_update
AFTER UPDATE ON product_images
WHEN (
       OLD.family_id        IS NOT NEW.family_id
    OR OLD.sku_id           IS NOT NEW.sku_id
    OR OLD.image_path       IS NOT NEW.image_path
    OR OLD.presentation_tag IS NOT NEW.presentation_tag
    OR OLD.sort_order       IS NOT NEW.sort_order
    OR OLD.note             IS NOT NEW.note
)
BEGIN
    INSERT INTO audit_log (table_name, row_id, action, changed_fields)
    SELECT 'product_images', NEW.id, 'UPDATE',
           json_group_object(field, json_array(old_v, new_v))
    FROM (
                  SELECT 'family_id'        AS field, OLD.family_id        AS old_v, NEW.family_id        AS new_v WHERE OLD.family_id        IS NOT NEW.family_id
        UNION ALL SELECT 'sku_id',                    OLD.sku_id,                    NEW.sku_id                    WHERE OLD.sku_id           IS NOT NEW.sku_id
        UNION ALL SELECT 'image_path',                OLD.image_path,                NEW.image_path                WHERE OLD.image_path       IS NOT NEW.image_path
        UNION ALL SELECT 'presentation_tag',          OLD.presentation_tag,          NEW.presentation_tag          WHERE OLD.presentation_tag IS NOT NEW.presentation_tag
        UNION ALL SELECT 'sort_order',                OLD.sort_order,                NEW.sort_order                WHERE OLD.sort_order       IS NOT NEW.sort_order
        UNION ALL SELECT 'note',                      OLD.note,                      NEW.note                      WHERE OLD.note             IS NOT NEW.note
    );
END;

CREATE TRIGGER audit_product_images_delete
BEFORE DELETE ON product_images
BEGIN
    INSERT INTO audit_log (table_name, row_id, action, changed_fields)
    VALUES ('product_images', OLD.id, 'DELETE',
        json_object(
            'family_id',  OLD.family_id,
            'sku_id',     OLD.sku_id,
            'image_path', OLD.image_path
        ));
END;

-- Record migration -----------------------------------------------------------

INSERT INTO applied_migrations(filename, applied_at)
VALUES ('025_product_families.sql', datetime('now','localtime'));

COMMIT;
