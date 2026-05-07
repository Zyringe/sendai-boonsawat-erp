-- 035_packaging_extend.rollback.sql
-- Restore the original CHECK trigger (5 packaging values only).

BEGIN;

DROP TRIGGER IF EXISTS products_packaging_check_insert;
DROP TRIGGER IF EXISTS products_packaging_check_update;

CREATE TRIGGER products_packaging_check_insert
    BEFORE INSERT ON products
    WHEN NEW.packaging IS NOT NULL
         AND NEW.packaging NOT IN ('แผง','ตัว','ถุง','แพ็คหัว','แพ็คถุง')
    BEGIN
        SELECT RAISE(ABORT,
            'packaging must be NULL or one of: แผง, ตัว, ถุง, แพ็คหัว, แพ็คถุง');
    END;

CREATE TRIGGER products_packaging_check_update
    BEFORE UPDATE ON products
    WHEN NEW.packaging IS NOT NULL
         AND NEW.packaging NOT IN ('แผง','ตัว','ถุง','แพ็คหัว','แพ็คถุง')
    BEGIN
        SELECT RAISE(ABORT,
            'packaging must be NULL or one of: แผง, ตัว, ถุง, แพ็คหัว, แพ็คถุง');
    END;

DELETE FROM applied_migrations WHERE filename = '035_packaging_extend.sql';

COMMIT;
