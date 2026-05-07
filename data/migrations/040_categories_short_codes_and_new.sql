-- 040_categories_short_codes_and_new.sql
-- Populate categories.short_code (3-char ASCII for sku_code prefix) on all
-- 25 existing categories + add 2 new broad categories surfaced during the
-- 2026-05-08 sub_category mapping review:
--   wrench  ประแจ                  WRN  (no existing fit; was 9+ SKUs unmatched)
--   fitting อุปกรณ์เสริม / กิ๊ปรัด    FIT  (กิ๊ป/สายยู — generic fit)
--
-- Short_codes use 3 char ASCII chosen for memorability (BLT/HNG/KNB style).
-- Decision: ใบตัดเพชร → disc (existing); โฮลซอ → drill_bit; จารบี → chemical;
-- ลูกดิ่ง → measuring; ลูกกลิ้ง → paint_brush; ถุงหิ้ว → other (existing 25 cover them).
--
-- Apply:    sqlite3 .../inventory.db < .../040_categories_short_codes_and_new.sql
-- Rollback: 040_categories_short_codes_and_new.rollback.sql

BEGIN;

-- 1) Add 2 new broad categories
INSERT INTO categories(code, name_th, sort_order, short_code) VALUES
    ('wrench',  'ประแจ',         100, 'WRN'),
    ('fitting', 'อุปกรณ์เสริม',   100, 'FIT');

-- 2) Populate short_code for all 25 existing categories
UPDATE categories SET short_code = 'BLT' WHERE code = 'door_bolt';
UPDATE categories SET short_code = 'KNB' WHERE code = 'door_knob';
UPDATE categories SET short_code = 'HNG' WHERE code = 'hinge';
UPDATE categories SET short_code = 'HDL' WHERE code = 'handle';
UPDATE categories SET short_code = 'LCK' WHERE code = 'lock_key';
UPDATE categories SET short_code = 'HMR' WHERE code = 'hammer';
UPDATE categories SET short_code = 'SDR' WHERE code = 'screwdriver';
UPDATE categories SET short_code = 'CTR' WHERE code = 'cutter';
UPDATE categories SET short_code = 'PLR' WHERE code = 'plier';
UPDATE categories SET short_code = 'DRB' WHERE code = 'drill_bit';
UPDATE categories SET short_code = 'SAW' WHERE code = 'saw';
UPDATE categories SET short_code = 'FAS' WHERE code = 'fastener';
UPDATE categories SET short_code = 'ANC' WHERE code = 'anchor';
UPDATE categories SET short_code = 'GLU' WHERE code = 'glue';
UPDATE categories SET short_code = 'PNT' WHERE code = 'paint_brush';
UPDATE categories SET short_code = 'SND' WHERE code = 'sandpaper';
UPDATE categories SET short_code = 'TAP' WHERE code = 'tape_gypsum';
UPDATE categories SET short_code = 'FCT' WHERE code = 'faucet';
UPDATE categories SET short_code = 'TRW' WHERE code = 'trowel';
UPDATE categories SET short_code = 'WIR' WHERE code = 'wire_cable';
UPDATE categories SET short_code = 'DSC' WHERE code = 'disc';
UPDATE categories SET short_code = 'CHM' WHERE code = 'chemical';
UPDATE categories SET short_code = 'MSR' WHERE code = 'measuring';
UPDATE categories SET short_code = 'SFT' WHERE code = 'safety';
UPDATE categories SET short_code = 'OTH' WHERE code = 'other';

INSERT INTO applied_migrations(filename, applied_at)
VALUES ('040_categories_short_codes_and_new.sql', datetime('now','localtime'));

COMMIT;
