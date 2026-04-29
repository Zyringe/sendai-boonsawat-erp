-- 005_suppliers_consolidate.rollback.sql
-- Rolls back 005_suppliers_consolidate.sql.
-- Removes the supplier_id FK column from purchase_transactions and the
-- new master columns (code, tax_id, payment_terms_days, default_currency)
-- from suppliers. Keeps any seeded supplier rows (delete manually if a
-- clean slate is needed: DELETE FROM suppliers WHERE id != 1).

BEGIN;

DROP INDEX IF EXISTS idx_pt_supplier_id;
DROP INDEX IF EXISTS idx_suppliers_code;

ALTER TABLE purchase_transactions DROP COLUMN supplier_id;

ALTER TABLE suppliers DROP COLUMN default_currency;
ALTER TABLE suppliers DROP COLUMN payment_terms_days;
ALTER TABLE suppliers DROP COLUMN tax_id;
ALTER TABLE suppliers DROP COLUMN code;

COMMIT;
