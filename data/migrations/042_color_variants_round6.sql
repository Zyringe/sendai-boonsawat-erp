-- 042_color_variants_round6.sql
-- Round 6 color additions surfaced during 2026-05-08 sub_category review:
--   MIX  สีคละ / คละสี        (assorted/mixed)
--   TRN  สีใส                  (transparent / clear)
--   ALM  สีอลูมิเนียม          (aluminum finish)
--   DBK  สีดำเข้ม              (Dark BlacK — deeper black)
--   LBK  สีดำอ่อน              (Light BlacK — lighter black/grayish)
--   MBK  สีดำด้าน              (Matte BlacK — matte finish)
--   LGY  สีเทาสว่าง            (Light GrаY)
--
-- Note: combo pattern like BLK/BLU (สีดำ-น้ำเงิน) doesn't need a new row —
-- the / separator pattern is supported by the build_name_from_columns
-- code_to_name lookup but does NOT need its own color_finish_codes entry
-- (would create namespace conflicts).
--
-- Packaging short codes (UN/PN/BG/SC/PK/DZ/HP/PP/TB/SP/C60) are NOT in DB —
-- they're hardcoded in `inventory_app/sku_code_utils.py` (no FK table for
-- packaging since the values live as TEXT on products with CHECK trigger).
--
-- Apply:    sqlite3 .../inventory.db < .../042_color_variants_round6.sql
-- Rollback: 042_color_variants_round6.rollback.sql

BEGIN;

INSERT INTO color_finish_codes(code, name_th, sort_order) VALUES
    ('MIX', 'คละสี',         220),
    ('TRN', 'สีใส',          221),
    ('ALM', 'สีอลูมิเนียม',   222),
    ('DBK', 'สีดำเข้ม',       223),
    ('LBK', 'สีดำอ่อน',       224),
    ('MBK', 'สีดำด้าน',       225),
    ('LGY', 'สีเทาสว่าง',     226);

INSERT INTO applied_migrations(filename, applied_at)
VALUES ('042_color_variants_round6.sql', datetime('now','localtime'));

COMMIT;
