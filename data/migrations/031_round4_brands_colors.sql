-- 031_round4_brands_colors.sql
-- Round 4 of catalog cleanup based on user CSV review 2026-05-05:
--
--   Brands added: นกนางแอ่น, KPS, KP, Kobe, Red Fox, Maxweld, ASAHI, Keenness
--   Brand updated: STAR.name_th = 'ตราดาว'  (alias, same brand)
--   Brand renamed: INTER → 'INTER TAPE' (canonical full name)
--   Color codes added: MAC, PAC, BN/AC, SB/WB
--   (Bare color 'เทา' added in parser, no schema change)
--
-- Apply:    sqlite3 .../inventory.db < .../031_round4_brands_colors.sql
-- Rollback: 031_round4_brands_colors.rollback.sql

BEGIN;

-- 1) Brands -----------------------------------------------------------------

INSERT INTO brands(code, name, name_th, is_own_brand, sort_order, short_code) VALUES
    ('swallow',     'นกนางแอ่น',  NULL,        0, 200, 'SWAL'),
    ('kps',         'KPS',        NULL,        0, 200, 'KPS'),
    ('kp',          'KP',         NULL,        0, 200, 'KP'),
    ('kobe',        'Kobe',       NULL,        0, 200, 'KOBE'),
    ('red_fox',     'Red Fox',    NULL,        0, 200, 'FOX'),
    ('maxweld',     'Maxweld',    NULL,        0, 200, 'MAXWELD'),
    ('asahi',       'ASAHI',      NULL,        0, 200, 'ASAHI'),
    ('keenness',    'Keenness',   NULL,        0, 200, 'KEEN');

-- 2) Update STAR — Thai alias name_th = 'ตราดาว'.
UPDATE brands SET name_th = 'ตราดาว' WHERE code = 'star';

-- 3) Rename INTER → 'INTER TAPE' canonical.
UPDATE brands SET name = 'INTER TAPE' WHERE code = 'inter';

-- 4) Color codes -----------------------------------------------------------

INSERT INTO color_finish_codes(code, name_th, sort_order) VALUES
    ('MAC',   'สีเมทัลลิกดำ',          15),
    ('PAC',   'สีสเปรย์',              105),
    ('BN/AC', 'สีน้ำตาลเข้ม-รมดำ',     85),
    ('SB/WB', 'สีทองด้าน-ขาว',         55);

INSERT INTO applied_migrations(filename, applied_at)
VALUES ('031_round4_brands_colors.sql', datetime('now','localtime'));

COMMIT;
