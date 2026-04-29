-- 009_fix_fk_orphans.rollback.sql
-- Reverses 009_fix_fk_orphans.sql: re-points sentinel batch_ids back to text
-- ('history_import' / 'manual_fix') and removes the sentinel import_log rows.
--
-- Sentinel ids: -1 (historical-backfill), -2 (manual-fix).
-- Negative ids ใช้เพื่อ sqlite_sequence ไม่ขยับ — rollback จึงไม่ต้องแตะ sqlite_sequence.
--
-- Apply:
--   sqlite3 inventory_app/instance/inventory.db < data/migrations/009_fix_fk_orphans.rollback.sql

BEGIN;

UPDATE sales_transactions    SET batch_id = 'history_import' WHERE batch_id = -1;
UPDATE sales_transactions    SET batch_id = 'manual_fix'     WHERE batch_id = -2;
UPDATE purchase_transactions SET batch_id = 'history_import' WHERE batch_id = -1;
UPDATE purchase_transactions SET batch_id = 'manual_fix'     WHERE batch_id = -2;

DELETE FROM import_log WHERE id IN (-1, -2);

COMMIT;
