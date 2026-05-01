-- 016_commission_payouts.sql
-- Track when commission has been paid out to a salesperson.
--
-- Design — multiple rows per (year_month, salesperson_code) allowed so
-- partial / split payouts work (Put 2026-05-02: "เลือกได้ว่ามีกี่อันที่
-- จ่ายแล้ว"). Each row records one payout event with amount + date +
-- method + note + who marked it.
--
-- Engine code computes "paid amount this month" = SUM(amount_paid) and
-- "remaining" = total_commission - paid_amount.
--
-- Apply:    sqlite3 .../inventory.db < .../016_commission_payouts.sql
-- Rollback: 016_commission_payouts.rollback.sql

BEGIN;

CREATE TABLE commission_payouts (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    year_month        TEXT    NOT NULL,                       -- 'YYYY-MM'
    salesperson_code  TEXT    NOT NULL REFERENCES salespersons(code),
    amount_paid       REAL    NOT NULL,
    paid_date         TEXT    NOT NULL,                       -- 'YYYY-MM-DD'
    paid_method       TEXT,                                    -- 'cash', 'transfer', 'cheque', etc
    note              TEXT,
    paid_by           TEXT,                                    -- user that marked
    created_at        TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE INDEX idx_cp_month_sp ON commission_payouts(year_month, salesperson_code);
CREATE INDEX idx_cp_paid_date ON commission_payouts(paid_date);

-- Audit triggers
CREATE TRIGGER audit_commission_payouts_insert
AFTER INSERT ON commission_payouts
BEGIN
    INSERT INTO audit_log (table_name, row_id, action, changed_fields, user)
    VALUES ('commission_payouts', NEW.id, 'INSERT',
        json_object('year_month', NEW.year_month,
                    'salesperson_code', NEW.salesperson_code,
                    'amount_paid', NEW.amount_paid,
                    'paid_date', NEW.paid_date,
                    'paid_method', NEW.paid_method),
        NEW.paid_by);
END;

CREATE TRIGGER audit_commission_payouts_update
AFTER UPDATE ON commission_payouts
WHEN (
       OLD.amount_paid  IS NOT NEW.amount_paid
    OR OLD.paid_date    IS NOT NEW.paid_date
    OR OLD.paid_method  IS NOT NEW.paid_method
    OR OLD.note         IS NOT NEW.note
)
BEGIN
    INSERT INTO audit_log (table_name, row_id, action, changed_fields)
    SELECT 'commission_payouts', NEW.id, 'UPDATE',
           json_group_object(field, json_array(old_v, new_v))
    FROM (
                  SELECT 'amount_paid' AS field, OLD.amount_paid AS old_v, NEW.amount_paid AS new_v WHERE OLD.amount_paid IS NOT NEW.amount_paid
        UNION ALL SELECT 'paid_date',            OLD.paid_date,            NEW.paid_date            WHERE OLD.paid_date    IS NOT NEW.paid_date
        UNION ALL SELECT 'paid_method',          OLD.paid_method,          NEW.paid_method          WHERE OLD.paid_method  IS NOT NEW.paid_method
        UNION ALL SELECT 'note',                 OLD.note,                 NEW.note                 WHERE OLD.note         IS NOT NEW.note
    );
END;

CREATE TRIGGER audit_commission_payouts_delete
BEFORE DELETE ON commission_payouts
BEGIN
    INSERT INTO audit_log (table_name, row_id, action, changed_fields)
    VALUES ('commission_payouts', OLD.id, 'DELETE',
        json_object('year_month', OLD.year_month,
                    'salesperson_code', OLD.salesperson_code,
                    'amount_paid', OLD.amount_paid,
                    'paid_date', OLD.paid_date));
END;

COMMIT;
