-- 053_add_customer_gmap_fields.sql
-- Add Google-Map metadata columns to customers, populated from the curated
-- per-region customer_map CSVs (อีสาน first; north/south/east/west later).
-- lat/lng/geocoded_at already exist (base schema) and are reused — only the
-- three Google-Map-specific fields are new.
--
-- Apply:    sqlite3 .../inventory.db < .../053_add_customer_gmap_fields.sql
-- Rollback: 053_add_customer_gmap_fields.rollback.sql

-- NOTE: do NOT self-insert into applied_migrations here. run_pending_migrations
-- (database.py) records every migration it executes; a self-insert causes a
-- duplicate-key crash on boot. (The 046/051 template's self-insert line is only
-- safe for migrations that were bootstrap-backfilled, never runner-executed.)

BEGIN;

ALTER TABLE customers ADD COLUMN plus_code    TEXT;
ALTER TABLE customers ADD COLUMN gmap_name    TEXT;
ALTER TABLE customers ADD COLUMN gmap_address TEXT;

COMMIT;
