-- 017_payout_per_invoice.rollback.sql
BEGIN;
DROP INDEX IF EXISTS idx_cp_invoice_sp;
ALTER TABLE commission_payouts DROP COLUMN invoice_no;
COMMIT;
