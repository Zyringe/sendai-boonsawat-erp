-- 052_add_more_3rdparty_brands.sql
-- Add 22 additional 3rd-party brands surfaced during 2026-05-12 review.
-- These appear in product names and were assigned short_codes during the
-- v10 cleanup; the codes are needed before products.brand_id can be linked.
--
-- Apply:    sqlite3 .../inventory.db < .../052_add_more_3rdparty_brands.sql
-- Rollback: 052_add_more_3rdparty_brands.rollback.sql

BEGIN;

INSERT INTO brands(code, name, name_th, is_own_brand, sort_order, short_code) VALUES
  ('ans',       'ANS',         NULL,           0, 100, 'ANS'),
  ('atta',      'ATTA',        NULL,           0, 100, 'ATTA'),
  ('azuma',     'AZUMA',       NULL,           0, 100, 'AZUM'),
  ('bell_mark', 'Bell',        'ระฆัง',         0, 100, 'BELL'),
  ('bulltech',  'BullTech',    NULL,           0, 100, 'BULL'),
  ('ck',        'CK',          NULL,           0, 100, 'CK'),
  ('crc',       'CRC',         NULL,           0, 100, 'CRC'),
  ('dowsil',    'DOWSIL',      NULL,           0, 100, 'DWSL'),
  ('hitop',     'HI-TOP',      NULL,           0, 100, 'HITOP'),
  ('exide',     'Exide',       'อีกิ๊ป',         0, 100, 'IGIP'),
  ('lamy',      'LAMY',        NULL,           0, 100, 'LAMY'),
  ('liberty',   'Liberty',     NULL,           0, 100, 'LBTY'),
  ('max_bond',  'Max Bond',    NULL,           0, 100, 'MXBND'),
  ('nrh',       'NRH',         NULL,           0, 100, 'NRH'),
  ('nrk',       'NRK',         NULL,           0, 100, 'NRK'),
  ('psw',       'PSW',         NULL,           0, 100, 'PSW'),
  ('scala',     'SCALA',       NULL,           0, 100, 'SCALA'),
  ('shark',     'Shark',       'ปลาฉลาม',      0, 100, 'SHARK'),
  ('stanley',   'STANLEY',     NULL,           0, 100, 'STAN'),
  ('sunco',     'SUNCO',       NULL,           0, 100, 'SUNCO'),
  ('tiger',     'Tiger',       'ตราเสือ',       0, 100, 'TIGER'),
  ('trane',     'Trane',       NULL,           0, 100, 'TRANE');

INSERT INTO applied_migrations(filename, applied_at)
VALUES ('052_add_more_3rdparty_brands.sql', datetime('now','localtime'));

COMMIT;
