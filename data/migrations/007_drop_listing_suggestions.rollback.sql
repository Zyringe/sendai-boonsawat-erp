-- Rollback for migration 007: recreate `_listing_suggestions` staging table.
--
-- NOTE: This rollback restores the table STRUCTURE ONLY.
-- The 808 rows of original data are NOT restored here — to recover the data,
-- restore from backup file:
--   data/backups/inventory-pre-phase-D-2026-04-29_194631.db
--
-- Schema captured pre-drop on 2026-04-29 via `.schema _listing_suggestions`.

CREATE TABLE _listing_suggestions (
    listing_id INTEGER PRIMARY KEY,
    suggested_sku INTEGER,
    suggested_name TEXT,
    confidence INTEGER,
    reason TEXT
  );
