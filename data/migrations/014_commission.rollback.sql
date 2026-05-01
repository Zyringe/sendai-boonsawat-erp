-- 014_commission.rollback.sql
-- Reverses 014_commission.sql.

BEGIN;

DROP TRIGGER IF EXISTS audit_commission_assignments_delete;
DROP TRIGGER IF EXISTS audit_commission_assignments_update;
DROP TRIGGER IF EXISTS audit_commission_assignments_insert;
DROP TRIGGER IF EXISTS audit_commission_tiers_delete;
DROP TRIGGER IF EXISTS audit_commission_tiers_update;
DROP TRIGGER IF EXISTS audit_commission_tiers_insert;

DROP TABLE IF EXISTS commission_assignments;
DROP TABLE IF EXISTS commission_tiers;

COMMIT;
