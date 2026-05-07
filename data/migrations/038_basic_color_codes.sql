-- 038_basic_color_codes.sql
-- Add basic paint-color codes (Black/Brown/Red/...) to color_finish_codes.
--
-- Reason: products like ตะปูยิงรีเวท 4-4 Black have color_th='สีดำ' but no
-- color_code (DB previously only had finish codes like AC=สีรมดำ, SS=สีเงิน-
-- สแตนเลส, BZ=สีบรอนซ์ — metal treatments, not paint colors). Without a
-- code, parser can't promote bare-color tokens (ดำ/ขาว/Black/Brown) to a
-- structured FK, leaving SKUs un-classifiable by color filter on /products.
--
-- Codes use 3-char ASCII tokens distinct from finish codes (BZ, AB, etc.)
-- to avoid namespace collision. sort_order=200+ keeps them after finishes.
--
-- After this migration, run autofix_sku_naming or re-parse to populate
-- existing SKUs' color_code from their color_th.
--
-- Apply:    sqlite3 .../inventory.db < .../038_basic_color_codes.sql
-- Rollback: 038_basic_color_codes.rollback.sql

BEGIN;

INSERT INTO color_finish_codes(code, name_th, sort_order) VALUES
    ('BLK', 'สีดำ',         200),
    ('WHT', 'สีขาว',        201),
    ('RED', 'สีแดง',        202),
    ('BLU', 'สีน้ำเงิน',    203),
    ('GRN', 'สีเขียว',      204),
    ('YEL', 'สีเหลือง',     205),
    ('BRN', 'สีน้ำตาล',     206),
    ('ORG', 'สีส้ม',        207),
    ('PRP', 'สีม่วง',       208),
    ('PNK', 'สีชมพู',       209),
    ('GRY', 'สีเทา',        210),
    ('GLD', 'สีทอง',        211),
    ('SLV', 'สีเงิน',       212),
    ('SKY', 'สีฟ้า',        213),
    ('TEA', 'สีชา',         214),
    ('CRM', 'สีครีม',       215),
    ('NAT', 'สีธรรมชาติ',   216),
    ('IVY', 'สีงา',         217);

INSERT INTO applied_migrations(filename, applied_at)
VALUES ('038_basic_color_codes.sql', datetime('now','localtime'));

COMMIT;
