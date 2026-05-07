-- 029_packaging_thung.rollback.sql
-- Restore the original CHECK trigger that rejects 'ถุง'.
-- WARNING: any SKU with packaging='ถุง' will block the rollback (CHECK fires
-- on UPDATE not retroactively, but the new trigger will refuse those values
-- on any future UPDATE). Reset such packaging values to NULL first if needed.

BEGIN;

DROP TRIGGER IF EXISTS products_packaging_check_insert;
DROP TRIGGER IF EXISTS products_packaging_check_update;

CREATE TRIGGER products_packaging_check_insert
    BEFORE INSERT ON products
    WHEN NEW.packaging IS NOT NULL AND NEW.packaging NOT IN ('แผง','ตัว')
    BEGIN
        SELECT RAISE(ABORT, 'packaging must be NULL, ''แผง'', or ''ตัว''');
    END;

CREATE TRIGGER products_packaging_check_update
    BEFORE UPDATE ON products
    WHEN NEW.packaging IS NOT NULL AND NEW.packaging NOT IN ('แผง','ตัว')
    BEGIN
        SELECT RAISE(ABORT, 'packaging must be NULL, ''แผง'', or ''ตัว''');
    END;

DELETE FROM applied_migrations WHERE filename = '029_packaging_thung.sql';

COMMIT;
