-- 036_pending_product_suggestions.sql
-- Staging table for new-SKU suggestions when staff (Louis) processes BSN
-- mapping. Manager/admin reviews + edits + approves to create the actual
-- product + auto-map the BSN code.
--
-- Workflow:
--   1. staff hits 🤖 Suggest on /mapping for a pending BSN code
--   2. /mapping/suggest/<code> returns: top fuzzy matches + parsed fields + cost
--   3. staff picks "Submit new SKU for review" (vs "Map to existing" which
--      doesn't need approval)
--   4. row inserted here with status='pending', suggested_by_user_id=staff
--   5. manager/admin sees it in /mapping?tab=suggestions
--   6. manager edits any field + clicks Approve
--   7. trigger creates products row + product_code_mapping row in same txn,
--      sets status='approved', reviewed_by_user_id=manager
--
-- No 'reject' action — manager/admin can edit any field; if BSN code is
-- garbage, use the existing is_ignored flag on /mapping main tab instead.
--
-- Apply:    sqlite3 .../inventory.db < .../036_pending_product_suggestions.sql
-- Rollback: 036_pending_product_suggestions.rollback.sql

BEGIN;

CREATE TABLE pending_product_suggestions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    bsn_code            TEXT    NOT NULL UNIQUE,
    bsn_name            TEXT    NOT NULL,

    -- Suggested structured fields (editable before approve)
    suggested_name      TEXT,                   -- final product_name to create
    category            TEXT,
    series              TEXT,
    brand_id            INTEGER REFERENCES brands(id),
    model               TEXT,
    size                TEXT,
    color_th            TEXT,
    color_code          TEXT    REFERENCES color_finish_codes(code),
    packaging           TEXT,                   -- check trigger applies on products, not here
    condition           TEXT,
    pack_variant        TEXT,

    -- Suggested operational fields
    suggested_cost      REAL    DEFAULT 0.0,    -- from latest purchase_transactions.unit_price
    suggested_unit_type TEXT    DEFAULT 'ตัว',
    units_per_carton    INTEGER,
    units_per_box       INTEGER,

    -- Workflow
    status              TEXT    NOT NULL DEFAULT 'pending'
                        CHECK(status IN ('pending','approved')),
    suggested_by_user_id INTEGER REFERENCES users(id),
    reviewed_by_user_id  INTEGER REFERENCES users(id),
    approved_product_id  INTEGER REFERENCES products(id), -- set when approved
    notes               TEXT,                   -- free-text for staff/manager comments

    created_at          TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    reviewed_at         TEXT
);

CREATE INDEX idx_pps_status ON pending_product_suggestions(status);
CREATE INDEX idx_pps_bsn_code ON pending_product_suggestions(bsn_code);

INSERT INTO applied_migrations(filename, applied_at)
VALUES ('036_pending_product_suggestions.sql', datetime('now','localtime'));

COMMIT;
