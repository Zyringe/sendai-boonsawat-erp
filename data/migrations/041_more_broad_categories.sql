-- 041_more_broad_categories.sql
-- Round-2 broad-category additions per 2026-05-08 user review of long-tail
-- sub_categories that didn't fit any existing 27 broad categories.
--
-- Decisions (locked by user 2026-05-08):
--   amulet         AML  กรอบจตุคาม         (Buddhist amulet frame — specialty)
--   hook           HOK  ขอแขวน / ตะขอแขวน
--   cement_bucket  BCT  ถังปูน             (mason's bucket — distinct from trowel)
--   chalk_line     CLN  บักเต้า             (carpenter's chalk-line tool)
--   pen            PEN  ปากกาเคมี           (marker pens)
--   box            BOX  ลังนอก / กล่องนอก  (packaging boxes for resale)
--   file_tool      FIL  ตะไบ                (metal/wood file)
--
-- Brings total broad categories: 27 → 34. Coverage 92% → expected ~96%.
--
-- Apply:    sqlite3 .../inventory.db < .../041_more_broad_categories.sql
-- Rollback: 041_more_broad_categories.rollback.sql

BEGIN;

INSERT INTO categories(code, name_th, sort_order, short_code) VALUES
    ('amulet',        'กรอบจตุคาม / พระเครื่อง',      120, 'AML'),
    ('hook',          'ขอแขวน / ตะขอ',                120, 'HOK'),
    ('cement_bucket', 'ถังปูน',                       120, 'BCT'),
    ('chalk_line',    'บักเต้า / ตีเส้น',              120, 'CLN'),
    ('pen',           'ปากกาเคมี',                    120, 'PEN'),
    ('box',           'ลังนอก / กล่องนอก',            120, 'BOX'),
    ('file_tool',     'ตะไบ',                         120, 'FIL');

INSERT INTO applied_migrations(filename, applied_at)
VALUES ('041_more_broad_categories.sql', datetime('now','localtime'));

COMMIT;
