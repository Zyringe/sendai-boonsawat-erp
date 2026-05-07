-- 035_packaging_extend.sql
-- Extend packaging CHECK trigger allowlist to include legitimate non-weight
-- packaging values found during 2026-05-07 mass rename.
--
-- Old set: แผง, ตัว, ถุง, แพ็คหัว, แพ็คถุง
-- New set: + ซอง, อัดแผง, แพ็ค, แบบหลอด, โหล, 1กลมี60ใบ
--
-- Per user feedback (2026-05-07): "non-weight packaging ถูกแล้ว" — the values
-- themselves are correct, just need to be allowed by the CHECK trigger.
--
-- Apply:    sqlite3 .../inventory.db < .../035_packaging_extend.sql
-- Rollback: 035_packaging_extend.rollback.sql

BEGIN;

DROP TRIGGER IF EXISTS products_packaging_check_insert;
DROP TRIGGER IF EXISTS products_packaging_check_update;

CREATE TRIGGER products_packaging_check_insert
    BEFORE INSERT ON products
    WHEN NEW.packaging IS NOT NULL
         AND NEW.packaging NOT IN (
             'แผง', 'ตัว', 'ถุง', 'แพ็คหัว', 'แพ็คถุง',
             'ซอง', 'อัดแผง', 'แพ็ค', 'แบบหลอด', 'โหล', '1กลมี60ใบ'
         )
    BEGIN
        SELECT RAISE(ABORT,
            'packaging must be NULL or one of: แผง, ตัว, ถุง, แพ็คหัว, แพ็คถุง, ซอง, อัดแผง, แพ็ค, แบบหลอด, โหล, 1กลมี60ใบ');
    END;

CREATE TRIGGER products_packaging_check_update
    BEFORE UPDATE ON products
    WHEN NEW.packaging IS NOT NULL
         AND NEW.packaging NOT IN (
             'แผง', 'ตัว', 'ถุง', 'แพ็คหัว', 'แพ็คถุง',
             'ซอง', 'อัดแผง', 'แพ็ค', 'แบบหลอด', 'โหล', '1กลมี60ใบ'
         )
    BEGIN
        SELECT RAISE(ABORT,
            'packaging must be NULL or one of: แผง, ตัว, ถุง, แพ็คหัว, แพ็คถุง, ซอง, อัดแผง, แพ็ค, แบบหลอด, โหล, 1กลมี60ใบ');
    END;

INSERT INTO applied_migrations(filename, applied_at)
VALUES ('035_packaging_extend.sql', datetime('now','localtime'));

COMMIT;
