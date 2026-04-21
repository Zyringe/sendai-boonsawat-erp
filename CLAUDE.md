# Sendai-Boonsawat ERP — CLAUDE.md

## Dev Server
```
runtimeExecutable: /usr/local/bin/python3
runtimeArgs: ["/Users/put/Documents/Sendai-Boonsawat/ERP/inventory_app/app.py"]
port: 5001
```
ใช้ `mcp__Claude_Preview__preview_start` → "Flask ERP Server" (config อยู่ใน `.claude/launch.json`)

## Stack
- **Framework**: Flask 3.x (Python), ไม่มี ORM
- **Database**: SQLite → `inventory_app/instance/inventory.db`
- **Encoding**: UTF-8 สำหรับ DB, **cp874** สำหรับไฟล์ BSN CSV
- **Python**: ต้องใช้ `/usr/local/bin/python3` (ไม่ใช่ system python)

## โครงสร้างไฟล์สำคัญ
```
ERP/
  CLAUDE.md
  .claude/
    launch.json          — dev server config
    commands/
      erp-formats.md     — /erp-formats skill (file format reference)
  data/
    source/              — ต้นฉบับ CSV (Product_Master, Location, Cost, ฯลฯ)
    exports/             — ไฟล์ที่ generate ออกมา (reports, mapping_suggestions)
  inventory_app/
    app.py          — routes ทั้งหมด
    models.py       — business logic + DB queries
    database.py     — schema + init_db()
    parse_weekly.py — parser สำหรับไฟล์ BSN รายสัปดาห์ (cp874)
    config.py       — DATABASE_PATH, UPLOAD_FOLDER, SECRET_KEY
    instance/inventory.db
    templates/
      base.html
      transactions/history.html
      mapping.html
      unit_conversions.html
```

## Schema ตาราง

### products
`id, sku(INT), product_name, units_per_carton, units_per_box, unit_type(default ตัว), hard_to_sell, cost_price, base_sell_price, low_stock_threshold, is_active, created_at, updated_at`

### transactions (stock ledger)
`id, product_id, txn_type(IN/OUT/ADJUST), quantity_change(INT), unit_mode, reference_no, note, created_at`
- trigger `after_transaction_insert` อัปเดต `stock_levels` อัตโนมัติ

### stock_levels
`product_id, quantity` — ยอดสต็อกปัจจุบัน

### sales_transactions / purchase_transactions (ข้อมูล BSN)
`id, batch_id, date_iso, doc_no, product_id, bsn_code, product_name_raw, customer/supplier, customer_code/supplier_code, qty, unit, unit_price, vat_type, discount, total, net, created_at, synced_to_stock(0/1)`

### product_code_mapping
`id, bsn_code, bsn_name, product_id, is_ignored, created_at`
- duplicate check: `(doc_no, bsn_code)` ไม่ใช่แค่ `doc_no`

### unit_conversions
`id, product_id, bsn_unit, ratio, created_at`
- UNIQUE(product_id, bsn_unit)
- BSN sync จะข้ามแถวที่ไม่มี conversion

### product_locations
`id, product_id, floor_no, created_at`
- สินค้าหนึ่งชนิดมีได้หลายแถว (หลายสถานที่)

## BSN Sync Logic
- import ไฟล์รายสัปดาห์ → parse → บันทึกใน `sales/purchase_transactions` (synced_to_stock=0)
- ต้องผูกรหัส BSN ก่อน (`product_code_mapping`)
- ถ้า BSN unit ≠ product unit_type → ต้องกำหนด ratio ใน `unit_conversions`
- `_sync_bsn_to_stock()` สร้าง transaction IN (ซื้อ) / OUT (ขาย) แล้ว set synced_to_stock=1
- redirect flow: import → mapping (ถ้า pending) → unit_conversions (ถ้า pending) → sales view

## Routes หลัก
| URL | Function |
|-----|----------|
| `/` | dashboard |
| `/products` | product_list |
| `/transactions` | transaction_history |
| `/import-weekly` | import_weekly |
| `/mapping` | mapping (ผูกรหัส BSN) |
| `/mapping/save` | mapping_save POST |
| `/unit-conversions` | unit_conversions |
| `/unit-conversions/save` | unit_conversions_save POST |
| `/sales` | sales_view |
| `/purchases` | purchases_view |

## สิ่งที่ต้องระวัง
- **ปรับสต็อกหน่วย**: ถ้าเปลี่ยน unit_type → ต้อง multiply quantity_change ใน transactions + stock_levels ด้วย ratio
- **ลบ BSN sync**: ต้อง (1) ลบ transactions ที่ note LIKE 'BSN%' (2) reset synced_to_stock=0 (3) ลบ unit_conversions (4) recalculate stock_levels
- **recalculate stock**: `DELETE FROM stock_levels WHERE product_id=?` แล้ว `INSERT` ใหม่จาก `SUM(quantity_change)`
- **วันที่ BSN**: เป็น Buddhist Era (พ.ศ.) ต้องแปลงก่อนบันทึก
- **Python 3.9**: ไม่รองรับ `int | None` syntax → ไม่ใส่ return type annotation
