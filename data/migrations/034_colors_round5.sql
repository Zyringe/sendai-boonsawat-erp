-- 034_colors_round5.sql
-- Round 5 color additions identified during 2026-05-07 mass rename apply
-- (sku_full_update_needs_review.csv).
--
-- Codes confirmed by user:
--   GP    = สีทองเคลือบ      (gold-plated finish; distinct from PB=สีทองเงา)
--   SB/PB = สีทองด้าน/เงา    (combo finish — matte+glossy gold)
--   BN/PB = สีนิกเกิล/ทองเงา (combo finish — nickel+glossy gold)
--   JSN   = สีนิกเกิล        (alternate code; coexists with NK=สีนิกเกิล)
--
-- Note on JSN/NK overlap: build_name_from_columns.py reverse-lookup
-- (name_th → code) will pick whichever comes last in iteration order. This is
-- acceptable since the source CSV always has color_code set explicitly when
-- JSN is intended.
--
-- Apply:    sqlite3 .../inventory.db < .../034_colors_round5.sql
-- Rollback: 034_colors_round5.rollback.sql

BEGIN;

INSERT INTO color_finish_codes(code, name_th, sort_order) VALUES
    ('GP',    'สีทองเคลือบ',       65),
    ('SB/PB', 'สีทองด้าน/เงา',    52),
    ('BN/PB', 'สีนิกเกิล/ทองเงา', 53),
    ('JSN',   'สีนิกเกิล',          54);

INSERT INTO applied_migrations(filename, applied_at)
VALUES ('034_colors_round5.sql', datetime('now','localtime'));

COMMIT;
