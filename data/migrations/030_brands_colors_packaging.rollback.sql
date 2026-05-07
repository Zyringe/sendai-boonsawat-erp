-- 030_brands_colors_packaging.rollback.sql
-- Reverse migration 030. Will fail if any product references the new
-- brands or color codes via FK — manual cleanup required first.

BEGIN;

DROP TRIGGER IF EXISTS products_packaging_check_insert;
DROP TRIGGER IF EXISTS products_packaging_check_update;

CREATE TRIGGER products_packaging_check_insert
    BEFORE INSERT ON products
    WHEN NEW.packaging IS NOT NULL AND NEW.packaging NOT IN ('แผง','ตัว','ถุง')
    BEGIN
        SELECT RAISE(ABORT, 'packaging must be NULL, ''แผง'', ''ตัว'', or ''ถุง''');
    END;

CREATE TRIGGER products_packaging_check_update
    BEFORE UPDATE ON products
    WHEN NEW.packaging IS NOT NULL AND NEW.packaging NOT IN ('แผง','ตัว','ถุง')
    BEGIN
        SELECT RAISE(ABORT, 'packaging must be NULL, ''แผง'', ''ตัว'', or ''ถุง''');
    END;

UPDATE products
   SET product_name = REPLACE(product_name, 'เหรียญทอง', 'เหรีญทอง')
 WHERE id IN (
     SELECT row_id FROM audit_log
     WHERE table_name = 'products'
       AND action = 'UPDATE'
       AND changed_fields LIKE '%เหรีญทอง%เหรียญทอง%'
 );

DELETE FROM color_finish_codes WHERE code IN ('JBB','SS-BK');

DELETE FROM brands WHERE code IN
    ('macoh','inter','sonic','heller','coin_gold','horse_brand','bird_brand');

DELETE FROM applied_migrations WHERE filename = '030_brands_colors_packaging.sql';

COMMIT;
