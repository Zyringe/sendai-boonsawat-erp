-- 032_color_bronze.sql
-- Add 'BZ' color code for บรอนซ์ (bronze finish).
--
-- Reason: 'บรอนซ์' (and truncated 'บรอน') appears in 13+ active SKUs across
-- categories (บานพับ, สายยู, สายยูชุบบรอน). Worth promoting from
-- bare-color dictionary → structured color code so it can be tracked
-- consistently and shown as `... สีบรอนซ์ (BZ)` in product names.
--
-- Note: ลายฆ้อน / ลายคราม remain as bare Thai descriptors (textures,
-- not colors) — see Rule 19 + Rule 24 in product_name_naming_rule.md.
--
-- Apply:    sqlite3 .../inventory.db < .../032_color_bronze.sql
-- Rollback: 032_color_bronze.rollback.sql

BEGIN;

INSERT INTO color_finish_codes(code, name_th, sort_order) VALUES
    ('BZ', 'สีบรอนซ์', 70);

INSERT INTO applied_migrations(filename, applied_at)
VALUES ('032_color_bronze.sql', datetime('now','localtime'));

COMMIT;
