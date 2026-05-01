-- 016_commission_payouts.rollback.sql
BEGIN;
DROP TRIGGER IF EXISTS audit_commission_payouts_delete;
DROP TRIGGER IF EXISTS audit_commission_payouts_update;
DROP TRIGGER IF EXISTS audit_commission_payouts_insert;
DROP INDEX IF EXISTS idx_cp_paid_date;
DROP INDEX IF EXISTS idx_cp_month_sp;
DROP TABLE IF EXISTS commission_payouts;
COMMIT;
