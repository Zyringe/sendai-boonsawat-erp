-- 005_suppliers_consolidate.sql
-- Phase C2 of the schema refactor.
-- Consolidate the supplier text field into the suppliers master table:
--   1. Add new master columns (code, tax_id, payment_terms_days, default_currency)
--   2. Insert any distinct supplier names from purchase_transactions
--      that aren't already in suppliers (49 distinct names → 48 new
--      inserts, ศรีไทยเจริญโลหะกิจ already exists from migration 002).
--   3. Add supplier_id INTEGER REFERENCES suppliers(id) on
--      purchase_transactions (keep the legacy text column for archaeology).
--   4. Backfill supplier_id by exact-name match.
--
-- Apply:
--   sqlite3 .../inventory.db < .../migrations/005_suppliers_consolidate.sql
-- Rollback: 005_suppliers_consolidate.rollback.sql

BEGIN;

-- ── Extend suppliers schema ───────────────────────────────────────────────
ALTER TABLE suppliers ADD COLUMN code TEXT;
ALTER TABLE suppliers ADD COLUMN tax_id TEXT;
ALTER TABLE suppliers ADD COLUMN payment_terms_days INTEGER;
ALTER TABLE suppliers ADD COLUMN default_currency TEXT NOT NULL DEFAULT 'THB';

CREATE UNIQUE INDEX idx_suppliers_code ON suppliers(code) WHERE code IS NOT NULL;

-- ── Seed all distinct suppliers from purchase_transactions ────────────────
-- INSERT OR IGNORE so ศรีไทย (already in suppliers from migration 002) is skipped.
INSERT OR IGNORE INTO suppliers (name, display_name)
SELECT DISTINCT supplier, supplier
  FROM purchase_transactions
 WHERE supplier IS NOT NULL AND TRIM(supplier) != '';

-- ── Add FK column to purchase_transactions ────────────────────────────────
ALTER TABLE purchase_transactions ADD COLUMN supplier_id INTEGER REFERENCES suppliers(id);
CREATE INDEX idx_pt_supplier_id ON purchase_transactions(supplier_id);

-- ── Backfill supplier_id by exact-name match ──────────────────────────────
UPDATE purchase_transactions
   SET supplier_id = (SELECT id FROM suppliers s WHERE s.name = purchase_transactions.supplier)
 WHERE supplier IS NOT NULL AND TRIM(supplier) != '';

COMMIT;
