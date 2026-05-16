-- 049_color_codes_round7.rollback.sql

BEGIN;

-- Restore SS-BK
INSERT INTO color_finish_codes(code, name_th, sort_order)
SELECT 'SS-BK', name_th, sort_order FROM color_finish_codes WHERE code='SS/BK';

UPDATE products SET color_code = 'SS-BK' WHERE color_code = 'SS/BK';

DELETE FROM color_finish_codes WHERE code IN ('POR','HMT','SS/BK');

DELETE FROM applied_migrations WHERE filename = '049_color_codes_round7.sql';

COMMIT;
