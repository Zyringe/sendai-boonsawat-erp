-- 014_commission.sql
-- Stage 8a — commission rules + per-salesperson assignment.
--
-- Two tiers in active use today (decided 2026-05-01):
--
--   Tier A (ต๋อ /06):  10% on own brands, 5% on third-party. No threshold.
--
--   Tier B (หนุ่ม /31): 5% flat (own AND third) until monthly net hits
--                       50,000 baht; ABOVE that point the rates switch
--                       to Tier-A style (10% own / 5% third) on the
--                       excess only.
--
-- Tier C is a placeholder ("TBD") for the other 10 salespersons whose
-- commission rules Put hasn't decided yet — earns 0% so the dashboard
-- shows them but doesn't accidentally accrue anything.
--
-- Threshold logic note: when a tier has threshold_amount IS NOT NULL,
-- engine code computes commission as
--      below = min(monthly_net, threshold) × rate_*_pct
--      above_excess = max(monthly_net - threshold, 0)
--      above = above_excess × {own,third} ratio × above_rate_*_pct
-- (proportional split — chronological tracking is a future
--  refinement if Put wants stricter ordering.)
--
-- Apply:
--   sqlite3 .../inventory.db < .../014_commission.sql
--
-- Rollback: 014_commission.rollback.sql

BEGIN;

-- ── tiers ────────────────────────────────────────────────────────────────
CREATE TABLE commission_tiers (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    code                   TEXT    UNIQUE NOT NULL,           -- 'A', 'B', 'C'
    name_th                TEXT    NOT NULL,
    description            TEXT,
    rate_own_pct           REAL    NOT NULL DEFAULT 0,        -- below threshold (or always if no threshold)
    rate_third_pct         REAL    NOT NULL DEFAULT 0,
    threshold_amount       REAL,                               -- NULL = no threshold
    above_rate_own_pct     REAL,                               -- only used if threshold IS NOT NULL
    above_rate_third_pct   REAL,
    is_active              INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
    note                   TEXT,
    created_at             TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at             TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

INSERT INTO commission_tiers
    (code, name_th, description,
     rate_own_pct, rate_third_pct,
     threshold_amount, above_rate_own_pct, above_rate_third_pct)
VALUES
    ('A', 'Tier A — แยกอัตราตามแบรนด์',
     '10% own brands (Sendai/Golden Lion/A-SPEC), 5% third-party. ไม่มี threshold.',
     10.0, 5.0,
     NULL, NULL, NULL),

    ('B', 'Tier B — ผ่าน threshold รายเดือน',
     '5% flat ทุกแบรนด์ จนถึง 50,000/เดือน; ส่วนเกินใช้ rate Tier A (10% own / 5% third)',
     5.0, 5.0,
     50000.0, 10.0, 5.0),

    ('C', 'Tier C — รอตัดสินใจ',
     'placeholder — Put ยังไม่ได้คิดอัตรา commission, ทุกอย่าง 0%',
     0.0, 0.0,
     NULL, NULL, NULL);

-- ── per-salesperson assignment ───────────────────────────────────────────
CREATE TABLE commission_assignments (
    salesperson_code TEXT    PRIMARY KEY REFERENCES salespersons(code),
    tier_id          INTEGER NOT NULL REFERENCES commission_tiers(id),
    effective_from   TEXT    NOT NULL,                          -- YYYY-MM-DD
    note             TEXT,
    created_at       TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at       TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

-- 12 salespersons — 06 → A, 31 → B, rest → C (placeholder).
INSERT INTO commission_assignments (salesperson_code, tier_id, effective_from, note) VALUES
    ('06',   (SELECT id FROM commission_tiers WHERE code='A'), '2024-01-01', 'ต๋อ /06'),
    ('31',   (SELECT id FROM commission_tiers WHERE code='B'), '2024-01-01', 'หนุ่ม /31'),
    ('02',   (SELECT id FROM commission_tiers WHERE code='C'), '2024-01-01', 'น้อย /02 — TBD'),
    ('06-L', (SELECT id FROM commission_tiers WHERE code='C'), '2024-01-01', 'TOU /06-L — TBD'),
    ('03',   (SELECT id FROM commission_tiers WHERE code='C'), '2024-01-01', 'ท /03 — TBD'),
    ('07',   (SELECT id FROM commission_tiers WHERE code='C'), '2024-01-01', 'Kน /07 — TBD'),
    ('99',   (SELECT id FROM commission_tiers WHERE code='C'), '2024-01-01', 'NET /99 — TBD'),
    ('13',   (SELECT id FROM commission_tiers WHERE code='C'), '2024-01-01', 'วิชัย /13 — TBD'),
    ('97',   (SELECT id FROM commission_tiers WHERE code='C'), '2024-01-01', 'Lazada /97 — TBD'),
    ('33',   (SELECT id FROM commission_tiers WHERE code='C'), '2024-01-01', 'ภ /33 — TBD'),
    ('98',   (SELECT id FROM commission_tiers WHERE code='C'), '2024-01-01', 'BRR /98 — TBD'),
    ('01',   (SELECT id FROM commission_tiers WHERE code='C'), '2024-01-01', 'ส /01 — TBD');

-- ── audit triggers: commission_tiers ─────────────────────────────────────
CREATE TRIGGER audit_commission_tiers_insert
AFTER INSERT ON commission_tiers
BEGIN
    INSERT INTO audit_log (table_name, row_id, action, changed_fields)
    VALUES ('commission_tiers', NEW.id, 'INSERT',
        json_object('code', NEW.code, 'name_th', NEW.name_th,
                    'rate_own_pct', NEW.rate_own_pct,
                    'rate_third_pct', NEW.rate_third_pct,
                    'threshold_amount', NEW.threshold_amount,
                    'above_rate_own_pct', NEW.above_rate_own_pct,
                    'above_rate_third_pct', NEW.above_rate_third_pct));
END;

CREATE TRIGGER audit_commission_tiers_update
AFTER UPDATE ON commission_tiers
WHEN (
       OLD.code                  IS NOT NEW.code
    OR OLD.name_th               IS NOT NEW.name_th
    OR OLD.description           IS NOT NEW.description
    OR OLD.rate_own_pct          IS NOT NEW.rate_own_pct
    OR OLD.rate_third_pct        IS NOT NEW.rate_third_pct
    OR OLD.threshold_amount      IS NOT NEW.threshold_amount
    OR OLD.above_rate_own_pct    IS NOT NEW.above_rate_own_pct
    OR OLD.above_rate_third_pct  IS NOT NEW.above_rate_third_pct
    OR OLD.is_active             IS NOT NEW.is_active
)
BEGIN
    INSERT INTO audit_log (table_name, row_id, action, changed_fields)
    SELECT 'commission_tiers', NEW.id, 'UPDATE',
           json_group_object(field, json_array(old_v, new_v))
    FROM (
                  SELECT 'code'                  AS field, OLD.code                  AS old_v, NEW.code                  AS new_v WHERE OLD.code                  IS NOT NEW.code
        UNION ALL SELECT 'name_th',                       OLD.name_th,                       NEW.name_th                       WHERE OLD.name_th               IS NOT NEW.name_th
        UNION ALL SELECT 'description',                   OLD.description,                   NEW.description                   WHERE OLD.description           IS NOT NEW.description
        UNION ALL SELECT 'rate_own_pct',                  OLD.rate_own_pct,                  NEW.rate_own_pct                  WHERE OLD.rate_own_pct          IS NOT NEW.rate_own_pct
        UNION ALL SELECT 'rate_third_pct',                OLD.rate_third_pct,                NEW.rate_third_pct                WHERE OLD.rate_third_pct        IS NOT NEW.rate_third_pct
        UNION ALL SELECT 'threshold_amount',              OLD.threshold_amount,              NEW.threshold_amount              WHERE OLD.threshold_amount      IS NOT NEW.threshold_amount
        UNION ALL SELECT 'above_rate_own_pct',            OLD.above_rate_own_pct,            NEW.above_rate_own_pct            WHERE OLD.above_rate_own_pct    IS NOT NEW.above_rate_own_pct
        UNION ALL SELECT 'above_rate_third_pct',          OLD.above_rate_third_pct,          NEW.above_rate_third_pct          WHERE OLD.above_rate_third_pct  IS NOT NEW.above_rate_third_pct
        UNION ALL SELECT 'is_active',                     OLD.is_active,                     NEW.is_active                     WHERE OLD.is_active             IS NOT NEW.is_active
    );
END;

CREATE TRIGGER audit_commission_tiers_delete
BEFORE DELETE ON commission_tiers
BEGIN
    INSERT INTO audit_log (table_name, row_id, action, changed_fields)
    VALUES ('commission_tiers', OLD.id, 'DELETE',
        json_object('code', OLD.code, 'name_th', OLD.name_th));
END;

-- ── audit triggers: commission_assignments ───────────────────────────────
CREATE TRIGGER audit_commission_assignments_insert
AFTER INSERT ON commission_assignments
BEGIN
    INSERT INTO audit_log (table_name, row_id, action, changed_fields)
    VALUES ('commission_assignments', NEW.rowid, 'INSERT',
        json_object('salesperson_code', NEW.salesperson_code,
                    'tier_id', NEW.tier_id,
                    'effective_from', NEW.effective_from,
                    'note', NEW.note));
END;

CREATE TRIGGER audit_commission_assignments_update
AFTER UPDATE ON commission_assignments
WHEN (
       OLD.tier_id        IS NOT NEW.tier_id
    OR OLD.effective_from IS NOT NEW.effective_from
    OR OLD.note           IS NOT NEW.note
)
BEGIN
    INSERT INTO audit_log (table_name, row_id, action, changed_fields)
    SELECT 'commission_assignments', NEW.rowid, 'UPDATE',
           json_group_object(field, json_array(old_v, new_v))
    FROM (
                  SELECT 'tier_id'        AS field, OLD.tier_id        AS old_v, NEW.tier_id        AS new_v WHERE OLD.tier_id        IS NOT NEW.tier_id
        UNION ALL SELECT 'effective_from',          OLD.effective_from,          NEW.effective_from          WHERE OLD.effective_from IS NOT NEW.effective_from
        UNION ALL SELECT 'note',                    OLD.note,                    NEW.note                    WHERE OLD.note           IS NOT NEW.note
    );
END;

CREATE TRIGGER audit_commission_assignments_delete
BEFORE DELETE ON commission_assignments
BEGIN
    INSERT INTO audit_log (table_name, row_id, action, changed_fields)
    VALUES ('commission_assignments', OLD.rowid, 'DELETE',
        json_object('salesperson_code', OLD.salesperson_code, 'tier_id', OLD.tier_id));
END;

COMMIT;
