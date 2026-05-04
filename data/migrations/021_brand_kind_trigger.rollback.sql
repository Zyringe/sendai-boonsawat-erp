-- 021_brand_kind_trigger.rollback.sql
-- Drop the cache-refresh trigger. After rollback, brand_kind cache
-- can go stale on raw SQL UPDATE products.brand_id again. Use only
-- if the trigger is causing problems (e.g. unexpected interaction
-- with another trigger, perf regression on bulk updates).

BEGIN;

DROP TRIGGER IF EXISTS refresh_brand_kind_on_product_brand_change;

COMMIT;
