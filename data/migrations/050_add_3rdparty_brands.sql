-- 050_add_3rdparty_brands.sql
-- Add 4 new 3rd-party brands surfaced during 2026-05-12 product review:
--   PHO  = ใบโพธิ์ทอง (Bodhi Leaf Gold)
--   DRAG = มังกรคู่     (Double Dragon)
--   RICE = ข้าวสาลี     (Wheat)
--   CROC = จระเข้       (Crocodile mark — separate from existing TOA brand)
-- Note: CROC is intentionally kept distinct from TOA. TOA brand (existing,
-- code=toa, name_th=จระเข้) continues to match products whose name contains
-- the literal "TOA" string. CROC matches products whose name contains
-- "จระเข้" (the Thai crocodile mark).
--
-- Apply:    sqlite3 .../inventory.db < .../050_add_3rdparty_brands.sql
-- Rollback: 050_add_3rdparty_brands.rollback.sql

BEGIN;

INSERT INTO brands(code, name, name_th, is_own_brand, sort_order, short_code) VALUES
  ('pho_thong',    'PHO Thong',     'ใบโพธิ์ทอง', 0, 100, 'PHO'),
  ('double_dragon','Double Dragon', 'มังกรคู่',    0, 100, 'DRAG'),
  ('wheat_brand',  'Wheat',         'ข้าวสาลี',    0, 100, 'RICE'),
  ('crocodile',    'Crocodile',     'จระเข้',     0, 100, 'CROC'),
  ('helicopter',   'Helicopter',    'ฮ.คอปเตอร์', 0, 100, 'HCOP'),
  ('kc_brand',     'KC',            NULL,        0, 100, 'KC'),
  ('mosu_brand',   'MOSU',          NULL,        0, 100, 'MOSU');

INSERT INTO applied_migrations(filename, applied_at)
VALUES ('050_add_3rdparty_brands.sql', datetime('now','localtime'));

COMMIT;
