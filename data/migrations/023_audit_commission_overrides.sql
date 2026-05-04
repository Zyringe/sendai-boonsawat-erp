-- 023_audit_commission_overrides.sql
-- Audit triggers for commission_overrides — until now this table had no
-- audit coverage, so the 3 existing rules (Singh Tong product, SOMIC brand,
-- Fastenic brand) and any future UI-driven edits were silent.
--
-- Mirrors the trigger shape used for commission_tiers (migration 014).
-- Captures every column that can be edited from the upcoming
-- /commission/overrides UI: product_id, brand_id, salesperson_code,
-- fixed_per_unit, custom_rate_pct, apply_when_price_gt, apply_when_price_lte,
-- is_active, note, effective_from.
--
-- Apply:    sqlite3 .../inventory.db < .../023_audit_commission_overrides.sql
-- Rollback: 023_audit_commission_overrides.rollback.sql

BEGIN;

CREATE TRIGGER audit_commission_overrides_insert
AFTER INSERT ON commission_overrides
BEGIN
    INSERT INTO audit_log (table_name, row_id, action, changed_fields)
    VALUES ('commission_overrides', NEW.id, 'INSERT',
        json_object(
            'product_id',           NEW.product_id,
            'brand_id',             NEW.brand_id,
            'salesperson_code',     NEW.salesperson_code,
            'fixed_per_unit',       NEW.fixed_per_unit,
            'custom_rate_pct',      NEW.custom_rate_pct,
            'apply_when_price_gt',  NEW.apply_when_price_gt,
            'apply_when_price_lte', NEW.apply_when_price_lte,
            'is_active',            NEW.is_active,
            'effective_from',       NEW.effective_from,
            'note',                 NEW.note
        ));
END;

CREATE TRIGGER audit_commission_overrides_update
AFTER UPDATE ON commission_overrides
WHEN (
       OLD.product_id           IS NOT NEW.product_id
    OR OLD.brand_id             IS NOT NEW.brand_id
    OR OLD.salesperson_code     IS NOT NEW.salesperson_code
    OR OLD.fixed_per_unit       IS NOT NEW.fixed_per_unit
    OR OLD.custom_rate_pct      IS NOT NEW.custom_rate_pct
    OR OLD.apply_when_price_gt  IS NOT NEW.apply_when_price_gt
    OR OLD.apply_when_price_lte IS NOT NEW.apply_when_price_lte
    OR OLD.is_active            IS NOT NEW.is_active
    OR OLD.effective_from       IS NOT NEW.effective_from
    OR OLD.note                 IS NOT NEW.note
)
BEGIN
    INSERT INTO audit_log (table_name, row_id, action, changed_fields)
    SELECT 'commission_overrides', NEW.id, 'UPDATE',
           json_group_object(field, json_array(old_v, new_v))
    FROM (
                  SELECT 'product_id'           AS field, OLD.product_id           AS old_v, NEW.product_id           AS new_v WHERE OLD.product_id           IS NOT NEW.product_id
        UNION ALL SELECT 'brand_id',                     OLD.brand_id,                     NEW.brand_id                     WHERE OLD.brand_id             IS NOT NEW.brand_id
        UNION ALL SELECT 'salesperson_code',             OLD.salesperson_code,             NEW.salesperson_code             WHERE OLD.salesperson_code     IS NOT NEW.salesperson_code
        UNION ALL SELECT 'fixed_per_unit',               OLD.fixed_per_unit,               NEW.fixed_per_unit               WHERE OLD.fixed_per_unit       IS NOT NEW.fixed_per_unit
        UNION ALL SELECT 'custom_rate_pct',              OLD.custom_rate_pct,              NEW.custom_rate_pct              WHERE OLD.custom_rate_pct      IS NOT NEW.custom_rate_pct
        UNION ALL SELECT 'apply_when_price_gt',          OLD.apply_when_price_gt,          NEW.apply_when_price_gt          WHERE OLD.apply_when_price_gt  IS NOT NEW.apply_when_price_gt
        UNION ALL SELECT 'apply_when_price_lte',         OLD.apply_when_price_lte,         NEW.apply_when_price_lte         WHERE OLD.apply_when_price_lte IS NOT NEW.apply_when_price_lte
        UNION ALL SELECT 'is_active',                    OLD.is_active,                    NEW.is_active                    WHERE OLD.is_active            IS NOT NEW.is_active
        UNION ALL SELECT 'effective_from',               OLD.effective_from,               NEW.effective_from               WHERE OLD.effective_from       IS NOT NEW.effective_from
        UNION ALL SELECT 'note',                         OLD.note,                         NEW.note                         WHERE OLD.note                 IS NOT NEW.note
    );
END;

CREATE TRIGGER audit_commission_overrides_delete
BEFORE DELETE ON commission_overrides
BEGIN
    INSERT INTO audit_log (table_name, row_id, action, changed_fields)
    VALUES ('commission_overrides', OLD.id, 'DELETE',
        json_object(
            'product_id',       OLD.product_id,
            'brand_id',         OLD.brand_id,
            'salesperson_code', OLD.salesperson_code,
            'fixed_per_unit',   OLD.fixed_per_unit,
            'custom_rate_pct',  OLD.custom_rate_pct,
            'note',             OLD.note
        ));
END;

COMMIT;
