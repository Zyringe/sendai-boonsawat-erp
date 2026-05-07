# Feature — Selective DB Upload (master-only mode)

> **Status:** ✅ Shipped 2026-05-07
> **Owner:** flask-dev
> **Why:** Two writers (Put on local SQLite via Upload/Download, friend via "อัพเดทข้อมูล" tab on prod). Full-DB upload wipes friend's interim transaction uploads. Master-only mode replaces only Put-owned tables, preserving friend's transactions.

## Behavior

`/admin/upload-db` form has two modes (radio):

### Master-only (default, recommended)
- ATTACH uploaded DB → for each whitelisted master table, `DELETE` + `INSERT SELECT * FROM upl.<t>`
- Transaction tables and anything else **untouched** (preserved from current prod)
- FK integrity verified before commit; rollback on violation
- Auto-backup to `inventory-pre-master-upload-{ts}.db`

### Full replace (legacy)
- Existing behavior: replace entire DB file with row-count diff warnings
- Auto-backup to `inventory-pre-upload-{ts}.db`

## Master tables (replaced from upload)

Defined in `app.py::_MASTER_TABLES` — 33 tables in v1:

| Group | Tables |
|---|---|
| Schema sync | `applied_migrations` |
| Product master | `products`, `product_families`, `product_images`, `product_attributes`, `product_brand_map`, `product_locations`, `product_barcodes`, `product_price_tiers` |
| Lookup master | `brands`, `categories`, `color_finish_codes` |
| Mapping master | `product_code_mapping`, `unit_conversions`, `conversion_formulas`, `conversion_formula_inputs` |
| Operations master | `regions`, `customer_regions`, `expense_categories`, `promotions`, `platform_skus`, `ecommerce_listings`, `listing_bundles`, `po_sequences`, `salespersons`, `commission_tiers`, `commission_assignments`, `commission_overrides` |
| Supplier master | `suppliers`, `supplier_catalogue_items`, `supplier_catalogue_versions`, `supplier_catalogue_price_history`, `supplier_product_mapping` |

## NOT replaced (preserved from current prod)

All transaction tables (sales/purchase/payments/transactions/stock_levels/express_*), audit_log, customers, users, companies. If table missing from `_MASTER_TABLES`, it stays as-is.

**Decision rationale for excluded tables:**
- `customers` — friend may add new from invoice imports; defer to manual coordination if needed
- `users` — security-sensitive (password hashes); shouldn't sync from local
- `audit_log` — append-only history per-DB; merging is non-trivial
- `companies` — rarely changes; conservative

If Put needs to update one of these, use Full Replace mode + coordinate with friend.

## Test coverage

Smoke test in implementation session: simulated friend transaction added to prod copy, Put rename added to upload copy, ran `_replace_master_tables` — friend's transaction preserved, Put's rename applied, no FK violations.

Recommended pytest smoke test (TODO): same scenario as smoke test above, run on every CI pass.

## Failure modes

| Scenario | Behavior |
|---|---|
| Master table missing in current DB | skip, log in flash message |
| Master table missing in upload DB | skip, log |
| FK violation after replace | rollback transaction, raise; current DB unchanged; user sees error flash |
| Upload file invalid SQLite | sqlite3 error, current DB unchanged |
| Backup copy fails | continues without backup (file might not exist on first install) |

## Rollback path

If a master-only upload breaks something on prod:
1. Use auto-backup `inventory-pre-master-upload-{ts}.db`
2. Toggle Upload/Download DB on
3. Full Replace mode with the backup → restored
4. Coordinate with friend for any transaction re-upload

## Future work

- pytest test for `_replace_master_tables` (currently smoke-tested only)
- Show preview screen before commit (like full mode's diff warning) — optional
- Add `customers` to master list once dedup logic clarifies who creates new customers
- Audit-log diff merge (so upload preserves both sides' audit history)

## Related files

- `inventory_app/app.py` — `_MASTER_TABLES`, `_replace_master_tables`, `upload_db()` route
- `inventory_app/templates/admin_upload_db.html` — radio mode selector
- `docs/runbook_db_upload.md` — operational procedure
