-- 031_round4_brands_colors.rollback.sql

BEGIN;

DELETE FROM color_finish_codes WHERE code IN ('MAC','PAC','BN/AC','SB/WB');

UPDATE brands SET name = 'INTER' WHERE code = 'inter';
UPDATE brands SET name_th = NULL WHERE code = 'star';

DELETE FROM brands WHERE code IN
    ('swallow','kps','kp','kobe','red_fox','maxweld','asahi','keenness');

DELETE FROM applied_migrations WHERE filename = '031_round4_brands_colors.sql';

COMMIT;
