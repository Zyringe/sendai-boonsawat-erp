-- 027_brands_and_typos.rollback.sql
--
-- WARNING: REPLACE-based typo fixes cannot be auto-rolled-back if any
-- product_name was edited again after migration 027. This rollback only
-- removes the 7 new brands and reverses the typo fix on names that still
-- contain the corrected spelling. Manual review recommended.

BEGIN;

-- Reverse typo fixes (only safe if the corrected substring still appears
-- exactly as 'สแตนเลส' / 'โครเมียม' in product names).
UPDATE products
   SET product_name = REPLACE(product_name, 'สแตนเลส', 'สแตนแลส')
 WHERE id IN (
     SELECT row_id FROM audit_log
     WHERE table_name = 'products'
       AND action = 'UPDATE'
       AND changed_fields LIKE '%สแตนแลส%สแตนเลส%'
 );

UPDATE products
   SET product_name = REPLACE(product_name, 'โครเมียม', 'โครเมี่ยม')
 WHERE id IN (
     SELECT row_id FROM audit_log
     WHERE table_name = 'products'
       AND action = 'UPDATE'
       AND changed_fields LIKE '%โครเมี่ยม%โครเมียม%'
 );

-- Remove brands added in migration 027.
-- Will fail if any product.brand_id references them — backfill must be
-- reverted first.
DELETE FROM brands WHERE code IN
    ('fion','orbit','star','kangaroo','horse_shoe','nitto','bac');

DELETE FROM applied_migrations WHERE filename = '027_brands_and_typos.sql';

COMMIT;
