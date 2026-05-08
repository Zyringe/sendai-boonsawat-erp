-- 042_color_variants_round6.rollback.sql

BEGIN;

DELETE FROM color_finish_codes WHERE code IN (
    'MIX','TRN','ALM','DBK','LBK','MBK','LGY'
);

DELETE FROM applied_migrations WHERE filename = '042_color_variants_round6.sql';

COMMIT;
