-- 052_add_more_3rdparty_brands.rollback.sql

BEGIN;

DELETE FROM brands WHERE short_code IN (
  'ANS','ATTA','AZUM','BELL','BULL','CK','CRC','DWSL','HITOP','IGIP',
  'LAMY','LBTY','MXBND','NRH','NRK','PSW','SCALA','SHARK','STAN','SUNCO',
  'TIGER','TRANE'
);

DELETE FROM applied_migrations WHERE filename = '052_add_more_3rdparty_brands.sql';

COMMIT;
