-- 023_audit_commission_overrides.rollback.sql
-- Drop the audit triggers added in 023.
--
-- Apply rollback:
--   sqlite3 .../inventory.db < .../023_audit_commission_overrides.rollback.sql

BEGIN;

DROP TRIGGER IF EXISTS audit_commission_overrides_insert;
DROP TRIGGER IF EXISTS audit_commission_overrides_update;
DROP TRIGGER IF EXISTS audit_commission_overrides_delete;

COMMIT;
