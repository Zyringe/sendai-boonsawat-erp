-- 049_color_codes_round7.sql
-- Add 2 new color/finish codes: POR (ลายคราม / porcelain pattern),
-- HMT (ลายฆ้อน / hammered pattern). Also rename SS-BK → SS/BK to match
-- the slash convention used by BN/AC, BN/PB, SB/PB, SB/WB.
--
-- Apply:    sqlite3 .../inventory.db < .../049_color_codes_round7.sql
-- Rollback: 049_color_codes_round7.rollback.sql

BEGIN;

-- Add new finish/pattern codes
INSERT INTO color_finish_codes(code, name_th, sort_order) VALUES
  ('POR', 'ลายคราม',  130),
  ('HMT', 'ลายฆ้อน',  131);

-- Rename SS-BK → SS/BK
INSERT INTO color_finish_codes(code, name_th, sort_order)
SELECT 'SS/BK', name_th, sort_order FROM color_finish_codes WHERE code='SS-BK';

UPDATE products SET color_code = 'SS/BK' WHERE color_code = 'SS-BK';

DELETE FROM color_finish_codes WHERE code = 'SS-BK';

INSERT INTO applied_migrations(filename, applied_at)
VALUES ('049_color_codes_round7.sql', datetime('now','localtime'));

COMMIT;
