-- 041_more_broad_categories.rollback.sql

BEGIN;

DELETE FROM categories WHERE code IN (
    'amulet','hook','cement_bucket','chalk_line','pen','box','file_tool'
);

DELETE FROM applied_migrations WHERE filename = '041_more_broad_categories.sql';

COMMIT;
