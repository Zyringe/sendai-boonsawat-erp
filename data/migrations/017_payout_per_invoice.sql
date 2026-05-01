-- 017_payout_per_invoice.sql
-- Add invoice_no to commission_payouts so each "I paid commission" event
-- is anchored to a specific invoice (Put 2026-05-02: "ติ๊กได้คือติ๊กที่
-- บิล invoice ว่าจะจ่ายอันไหน").
--
-- Existing month-level payout rows (without invoice_no) are still valid
-- — invoice_no nullable. New rows inserted from the drill-down checkbox
-- form will always carry an invoice_no.
--
-- Apply:    sqlite3 .../inventory.db < .../017_payout_per_invoice.sql
-- Rollback: 017_payout_per_invoice.rollback.sql

BEGIN;

ALTER TABLE commission_payouts ADD COLUMN invoice_no TEXT;
CREATE INDEX idx_cp_invoice_sp ON commission_payouts(invoice_no, salesperson_code);

COMMIT;
