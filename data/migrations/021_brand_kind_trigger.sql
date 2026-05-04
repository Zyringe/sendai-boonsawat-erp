-- 021_brand_kind_trigger.sql
-- Defense-in-depth for the express_sales.brand_kind cache.
--
-- Background: express_sales.brand_kind is a denormalized cache of
-- "is this line an own-brand product or third-party?". It's read by
-- the commission engine on every /commission render. Source of truth
-- chain: brands.is_own_brand ← products.brand_id ← product_code_mapping.
--
-- Today the cache is refreshed in 2 places:
--   - scripts/load_brand_map.py — initial bulk backfill
--   - models.set_product_brand() — when brand changes via the UI
--
-- Gap: any UPDATE on products.brand_id that bypasses set_product_brand
-- (raw SQL, future migrations, subagent scripts, bulk fix-ups) leaves
-- the cache stale. The commission engine then computes with the OLD
-- brand classification — silently, no warning.
--
-- Fix: a DB-level trigger that catches every brand_id change regardless
-- of caller and refreshes brand_kind for the affected product's
-- express_sales rows. Same UPDATE as set_product_brand step 2 — so
-- when set_product_brand runs, the manual UPDATE there becomes a
-- redundant no-op (idempotent, safe).
--
-- Scope notes:
--   - This trigger handles products.brand_id changes only.
--   - Re-mapping bsn_code → product_id (changes to product_code_mapping)
--     would also stale the cache. Not covered here — rare; can be
--     added later if needed.
--   - brands.is_own_brand changes (e.g. flipping a brand from own to
--     third-party) would also stale the cache. Also not covered —
--     extremely rare; would need a sweep across many products anyway.
--
-- Apply:
--   sqlite3 inventory_app/instance/inventory.db < data/migrations/021_brand_kind_trigger.sql
--
-- Rollback: 021_brand_kind_trigger.rollback.sql

BEGIN;

CREATE TRIGGER refresh_brand_kind_on_product_brand_change
AFTER UPDATE OF brand_id ON products
WHEN OLD.brand_id IS NOT NEW.brand_id
BEGIN
    UPDATE express_sales
       SET brand_kind = (
           SELECT CASE WHEN b.is_own_brand = 1 THEN 'own' ELSE 'third_party' END
             FROM brands b WHERE b.id = NEW.brand_id
       )
     WHERE product_code IN (
         SELECT bsn_code FROM product_code_mapping WHERE product_id = NEW.id
     );
END;

COMMIT;
