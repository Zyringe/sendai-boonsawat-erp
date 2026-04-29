-- 009_fix_fk_orphans.sql
-- Purpose: Fix FK orphan rows in sales_transactions / purchase_transactions
--   where batch_id is text ('history_import' / 'manual_fix') instead of an
--   INTEGER FK -> import_log(id). Insert sentinel import_log rows and
--   re-point orphan batch_id values to them, preserving data while restoring
--   referential integrity.
--
-- Scope (verified 2026-04-29):
--   sales_transactions:    'history_import' = 453 rows, 'manual_fix' = 1 row
--   purchase_transactions: no orphans
--
-- Sentinel id choice:
--   Negative sentinel ids (-1, -2) chosen เพื่อ sqlite_sequence ไม่ขยับ
--   (AUTOINCREMENT next value ยังคงเดิม — INSERT ปกติได้ id ต่อจาก max ที่ใช้จริง).
--   Positive ids ขนาดใหญ่ (เช่น 99998/99999) จะดัน sqlite_sequence.seq ไป 99999
--   ทำให้ import_log row ถัดไปได้ id=100000 ผิดธรรมชาติ.
--
-- Apply:
--   sqlite3 inventory_app/instance/inventory.db < data/migrations/009_fix_fk_orphans.sql
--
-- Rollback: data/migrations/009_fix_fk_orphans.rollback.sql

BEGIN;

INSERT INTO import_log (id, filename, rows_imported, rows_skipped, imported_at, notes)
VALUES
  (-1, '<historical-backfill>', 453, 0, '2024-01-03 00:00:00',
   'Historical sales/purchase backfill — data load ก่อนระบบ import_log proper (2024-01 ถึง 2026-02). Sentinel row from migration 009. Negative id เพื่อไม่กระทบ AUTOINCREMENT sequence.'),
  (-2, '<manual-fix>', 1, 0, '2026-03-10 00:00:00',
   'Manual data correction — row IV6900392-1. Sentinel row from migration 009. Negative id เพื่อไม่กระทบ AUTOINCREMENT sequence.');

UPDATE sales_transactions    SET batch_id = -1 WHERE batch_id = 'history_import';
UPDATE sales_transactions    SET batch_id = -2 WHERE batch_id = 'manual_fix';
UPDATE purchase_transactions SET batch_id = -1 WHERE batch_id = 'history_import';
UPDATE purchase_transactions SET batch_id = -2 WHERE batch_id = 'manual_fix';

COMMIT;
