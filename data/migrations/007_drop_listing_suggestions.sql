-- Migration 007: drop legacy `_listing_suggestions` staging table
--
-- Phase D3 of schema refactor (2026-04-29).
-- This table held 808 staging rows from an old listing-mapping experiment.
-- Verified no Python/HTML/SQL callers in the repo (grep clean).
-- Data is preserved in backup: data/backups/inventory-pre-phase-D-2026-04-29_194631.db
--
-- Apply:
--   sqlite3 inventory_app/instance/inventory.db < data/migrations/007_drop_listing_suggestions.sql
--
-- Rollback:
--   sqlite3 inventory_app/instance/inventory.db < data/migrations/007_drop_listing_suggestions.rollback.sql
--   (rollback restores schema only; for data, restore from backup .db)

DROP TABLE IF EXISTS _listing_suggestions;
