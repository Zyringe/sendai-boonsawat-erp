-- 036_pending_product_suggestions.rollback.sql

BEGIN;

DROP INDEX IF EXISTS idx_pps_bsn_code;
DROP INDEX IF EXISTS idx_pps_status;
DROP TABLE IF EXISTS pending_product_suggestions;

DELETE FROM applied_migrations
 WHERE filename = '036_pending_product_suggestions.sql';

COMMIT;
