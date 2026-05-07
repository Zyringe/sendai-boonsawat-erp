-- 034_colors_round5.rollback.sql
-- WARNING: will fail if any product already references one of these codes.
-- Run after NULLing color_code on those rows.

BEGIN;

DELETE FROM color_finish_codes WHERE code IN ('GP', 'SB/PB', 'BN/PB', 'JSN');

DELETE FROM applied_migrations WHERE filename = '034_colors_round5.sql';

COMMIT;
