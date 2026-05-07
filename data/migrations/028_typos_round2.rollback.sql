-- 028_typos_round2.rollback.sql
-- Reverses typo fixes from migration 028. CAVEAT: REPLACE-based reversal
-- can over-match if 'สแตนเลส' / 'น็อต' was already present elsewhere in the
-- name. Manual review recommended.

BEGIN;

UPDATE products
   SET product_name = REPLACE(product_name, 'สแตนเลส', 'แสตนเลส')
 WHERE id IN (
     SELECT row_id FROM audit_log
     WHERE table_name = 'products'
       AND action = 'UPDATE'
       AND (changed_fields LIKE '%แสตนเลส%สแตนเลส%'
            OR changed_fields LIKE '%แสตนแลส%สแตนเลส%')
 );

UPDATE products
   SET product_name = REPLACE(product_name, 'น็อต', 'น๊อต')
 WHERE id IN (
     SELECT row_id FROM audit_log
     WHERE table_name = 'products'
       AND action = 'UPDATE'
       AND changed_fields LIKE '%น๊อต%น็อต%'
 );

DELETE FROM applied_migrations WHERE filename = '028_typos_round2.sql';

COMMIT;
