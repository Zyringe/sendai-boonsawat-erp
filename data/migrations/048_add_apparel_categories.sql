-- 048_add_apparel_categories.sql
-- Add new categories surfaced during 2026-05-12 product review:
--   APR (ผ้ากันเปื้อน), SHI (เสื้อ), UMB (ร่ม), TLT (สุขภัณฑ์), RUB (ยาง/Rubber)
--
-- Apply:    sqlite3 .../inventory.db < .../048_add_apparel_categories.sql
-- Rollback: 048_add_apparel_categories.rollback.sql

BEGIN;

INSERT INTO categories(code, name_th, sort_order, short_code) VALUES
  ('apron',    'ผ้ากันเปื้อน', 350, 'APR'),
  ('shirt',    'เสื้อ',        351, 'SHI'),
  ('umbrella', 'ร่ม',         352, 'UMB'),
  ('toilet',   'สุขภัณฑ์',     353, 'TLT'),
  ('rubber',   'ยาง',         354, 'RUB');

INSERT INTO applied_migrations(filename, applied_at)
VALUES ('048_add_apparel_categories.sql', datetime('now','localtime'));

COMMIT;
