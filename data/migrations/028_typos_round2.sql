-- 028_typos_round2.sql
-- Second pass of typo fixes found by audit_sku_naming.py 2026-05-05:
--
--   แสตนเลส → สแตนเลส   (14 SKUs)
--   แสตนแลส → สแตนเลส   (3 SKUs)
--   น๊อต   → น็อต       (10 SKUs)
--
-- audit_log captures each rename via update trigger.
--
-- Apply:    sqlite3 .../inventory.db < .../028_typos_round2.sql
-- Rollback: 028_typos_round2.rollback.sql

BEGIN;

UPDATE products
   SET product_name = REPLACE(product_name, 'แสตนแลส', 'สแตนเลส')
 WHERE product_name LIKE '%แสตนแลส%';

UPDATE products
   SET product_name = REPLACE(product_name, 'แสตนเลส', 'สแตนเลส')
 WHERE product_name LIKE '%แสตนเลส%';

UPDATE products
   SET product_name = REPLACE(product_name, 'น๊อต', 'น็อต')
 WHERE product_name LIKE '%น๊อต%';

INSERT INTO applied_migrations(filename, applied_at)
VALUES ('028_typos_round2.sql', datetime('now','localtime'));

COMMIT;
