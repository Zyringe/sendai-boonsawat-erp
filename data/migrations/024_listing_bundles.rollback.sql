-- 024_listing_bundles.rollback.sql

BEGIN;

DROP TRIGGER IF EXISTS audit_listing_bundles_delete;
DROP TRIGGER IF EXISTS audit_listing_bundles_update;
DROP TRIGGER IF EXISTS audit_listing_bundles_insert;
DROP INDEX IF EXISTS idx_listing_bundles_listing;
DROP TABLE IF EXISTS listing_bundles;

COMMIT;
