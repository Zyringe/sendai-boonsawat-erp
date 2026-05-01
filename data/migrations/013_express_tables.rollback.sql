-- 013_express_tables.rollback.sql
-- Reverses 013_express_tables.sql.
--
-- Drops in FK-safe order: child tables first, then parent ledgers,
-- then the import-log table.

BEGIN;

DROP INDEX IF EXISTS idx_express_sales_doctype;
DROP INDEX IF EXISTS idx_express_sales_product;
DROP INDEX IF EXISTS idx_express_sales_customer;
DROP INDEX IF EXISTS idx_express_sales_date;
DROP INDEX IF EXISTS idx_express_sales_doc;
DROP TABLE IF EXISTS express_sales;

DROP INDEX IF EXISTS idx_express_pout_ref_doc;
DROP INDEX IF EXISTS idx_express_pout_ref_pid;
DROP TABLE IF EXISTS express_payment_out_receive_refs;

DROP INDEX IF EXISTS idx_express_pout_supplier;
DROP INDEX IF EXISTS idx_express_pout_date;
DROP INDEX IF EXISTS idx_express_pout_doc;
DROP TABLE IF EXISTS express_payments_out;

DROP INDEX IF EXISTS idx_express_ar_doc;
DROP INDEX IF EXISTS idx_express_ar_customer;
DROP INDEX IF EXISTS idx_express_ar_snapshot;
DROP TABLE IF EXISTS express_ar_outstanding;

DROP INDEX IF EXISTS idx_express_pin_ref_inv;
DROP INDEX IF EXISTS idx_express_pin_ref_pid;
DROP TABLE IF EXISTS express_payment_in_invoice_refs;

DROP INDEX IF EXISTS idx_express_pin_customer;
DROP INDEX IF EXISTS idx_express_pin_sp;
DROP INDEX IF EXISTS idx_express_pin_date;
DROP INDEX IF EXISTS idx_express_pin_doc;
DROP TABLE IF EXISTS express_payments_in;

DROP INDEX IF EXISTS idx_express_cn_line_product;
DROP INDEX IF EXISTS idx_express_cn_line_cn;
DROP TABLE IF EXISTS express_credit_note_lines;

DROP INDEX IF EXISTS idx_express_cn_supplier;
DROP INDEX IF EXISTS idx_express_cn_date;
DROP INDEX IF EXISTS idx_express_cn_doc;
DROP TABLE IF EXISTS express_credit_notes;

DROP INDEX IF EXISTS idx_express_import_log_type;
DROP TABLE IF EXISTS express_import_log;

COMMIT;
