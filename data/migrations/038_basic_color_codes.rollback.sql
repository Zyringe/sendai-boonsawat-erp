-- 038_basic_color_codes.rollback.sql
-- WARNING: will fail if any product references one of these codes.

BEGIN;

DELETE FROM color_finish_codes WHERE code IN (
    'BLK','WHT','RED','BLU','GRN','YEL','BRN','ORG','PRP','PNK',
    'GRY','GLD','SLV','SKY','TEA','CRM','NAT','IVY'
);

DELETE FROM applied_migrations WHERE filename = '038_basic_color_codes.sql';

COMMIT;
