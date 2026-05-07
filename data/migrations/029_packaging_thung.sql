-- 029_packaging_thung.sql
-- Add 'ถุง' (bag) as a valid value for products.packaging.
--
-- Found 2026-05-05 review: SKUs like "(ถุง) รุ่นTOP ชา" use bag packaging.
-- Migration 026 originally limited packaging to ('แผง','ตัว'); this expands.
--
-- Apply:    sqlite3 .../inventory.db < .../029_packaging_thung.sql
-- Rollback: 029_packaging_thung.rollback.sql

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

INSERT INTO applied_migrations(filename, applied_at)
VALUES ('029_packaging_thung.sql', datetime('now','localtime'));

COMMIT;
