-- 047_add_reflective_color.sql
-- Add REF color code for สีสะท้อนแสง (reflective/fluorescent finish).
-- Used by trimmer-line products (สายเอ็นสีสะท้อนแสง Sendai #50-#120) and
-- their containers (กล่องสายเอ็นสีสะท้อนแสง).
--
-- Apply:    sqlite3 .../inventory.db < .../047_add_reflective_color.sql
-- Rollback: 047_add_reflective_color.rollback.sql

BEGIN;

INSERT INTO color_finish_codes(code, name_th, sort_order)
VALUES ('REF', 'สีสะท้อนแสง', 230);

INSERT INTO applied_migrations(filename, applied_at)
VALUES ('047_add_reflective_color.sql', datetime('now','localtime'));

COMMIT;
