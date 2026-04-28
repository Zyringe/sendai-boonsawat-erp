# Sendy — ERP System Context — Sendai Boonsawat

> **Sendy** = ชื่อเรียก ERP backend app (Flask) ของ BSN/Sendai Trading. ทุกที่ที่เห็น "ERP" ในไฟล์นี้ = Sendy.

Load this at the start of every session to get full context of the current state of Sendy (the ERP).

---

## Stack
- Flask 3.x (Python), no ORM
- SQLite → `inventory_app/instance/inventory.db`
- Encoding: UTF-8 for DB, **cp874** for BSN CSV files
- Python: `/usr/local/bin/python3` (not system python)
- Dev server: `mcp__Claude_Preview__preview_start` → "Sendy Server" (port 5001)

---

## Database State (as of 2026-04-20)

| Table | Count |
|-------|-------|
| products (active) | 1,872 |
| products (inactive) | 12 (9 merged + 3 เก่า) |
| transactions | 38,305 |
| sales_transactions | 19,704 |
| purchase_transactions | 289 |
| product_code_mapping | 1,682 |
| unit_conversions | 1,911 |
| stock_levels | 1,870 |
| received_payments | 2,473 |
| paid_invoices | 7,329 |

- Sales unsynced: 0
- BSN mapping ค้าง: 0
- Unpaid bills: **150 บิล / ฿955,265**
- **Stock ติดลบ: 0** ✅
- **สินค้าไม่มีราคาทุน: ~1,076 รายการ** (ปล่อยไว้ก่อน)

---

## Schema

### products
`id, sku(INT), product_name, units_per_carton, units_per_box, unit_type(default ตัว), hard_to_sell, cost_price, base_sell_price, low_stock_threshold, is_active, created_at, updated_at, shopee_stock, lazada_stock`

### transactions (stock ledger)
`id, product_id, txn_type(IN/OUT/ADJUST), quantity_change(REAL), unit_mode, reference_no, note, created_at`
- trigger `after_transaction_insert` อัปเดต `stock_levels` อัตโนมัติ
- qty เก็บเป็น REAL (ไม่ปัดทศนิยม)

### stock_levels
`product_id, quantity`

### sales_transactions / purchase_transactions
`id, batch_id, date_iso, doc_no, product_id, bsn_code, product_name_raw, customer/supplier, customer_code/supplier_code, qty, unit, unit_price, vat_type, discount, total, net, created_at, synced_to_stock(0/1)`

### product_code_mapping
`id, bsn_code, bsn_name, product_id, is_ignored, created_at`
- duplicate check ใน import: `(doc_base + bsn_code + unit_price)` สำหรับ weekly, `(doc_no + bsn_code)` สำหรับ history format
- เพิ่ม unit_price เข้า check เพื่อรองรับของแถม (unit_price=0) ที่มี bsn_code เดียวกับแถวปกติ

### unit_conversions
`id, product_id, bsn_unit, ratio, created_at`
- UNIQUE(product_id, bsn_unit)
- BSN sync ข้ามแถวที่ไม่มี conversion

### product_locations
`id, product_id, floor_no, created_at`

### customer_regions *(ใหม่)*
`customer_code TEXT PRIMARY KEY, region TEXT, salesperson TEXT`
- populate จากไฟล์ `ยอดขาย_แจกตามพนักงานขาย_till_7.4.69.csv` (cp874)
- 272 rows, match กับ sales_transactions ครบ 264/264 รายการ

---

## BSN Sync Logic
- import ไฟล์รายสัปดาห์ → parse → บันทึกใน `sales/purchase_transactions` (synced_to_stock=0)
- ต้องผูกรหัส BSN ก่อน (`product_code_mapping`)
- ถ้า BSN unit ≠ product unit_type → ต้องกำหนด ratio ใน `unit_conversions`
- `_sync_bsn_to_stock()` สร้าง transaction IN/OUT แล้ว set synced_to_stock=1
- `batch_id='history_import'` → สร้าง IN+OUT pair (net=0) สำหรับข้อมูลก่อน cutoff 3/3/2569
- `_get_base_qty()` คืนค่า REAL (ไม่มี `int()` wrapper แล้ว)
- ถ้า BSN unit ไม่มีใน unit_conversions → แถวนั้นถูกข้ามและ synced_to_stock=0 ค้างไว้ → ต้องเพิ่ม conversion แล้ว re-sync

## Routes หลัก
| URL | Function |
|-----|----------|
| `/` | dashboard |
| `/products` | product_list |
| `/products/<id>` | product_detail |
| `/products/<id>/trade` | product_trade_summary |
| `/products/<id>/pricing` | product_pricing (ราคาขายปกติ + จริงต่อร้าน) |
| `/products/<id>/online-stock` POST | อัปเดต shopee/lazada stock |
| `/transactions` | transaction_history |
| `/import-weekly` | import_weekly |
| `/mapping` | mapping (ผูกรหัส BSN) |
| `/mapping/save` | mapping_save POST |
| `/unit-conversions` | unit_conversions (search + pagination) |
| `/unit-conversions/save` | unit_conversions_save POST |
| `/sales` | sales_view (รองรับ filter ?product_id=X) |
| `/sales/<doc_base>` | sales_doc (เรียง line ตามเลข integer ASC) |
| `/purchases` | purchases_view |
| `/trade-dashboard` | trade_dashboard |
| `/customers` | customer_list (search + filter by region) |
| `/customer/<name>` | customer_summary (มี unpaid bills card) |
| `/payment-status` | payment_status (รายบิล paid/unpaid) |
| `/payment-status/customers` | payment_customers (หนี้ค้างรายลูกค้า + คาดคะเนยอดโอน) |

---

## Unit Conversion Rules (สำคัญ)
- **หล** (โหล):
  - unit_type=โหล → ratio=1
  - unit_type=โหลคู่ → ratio=0.5 (2 หล = 1 โหลคู่)
  - unit_type อื่น (ตัว/อัน/ดอก/ฯลฯ) → ratio=12
- ค่า ratio หมายถึง: 1 BSN unit = ratio × product unit
- หน่วย BSN ที่มักสับสน: `อน`=อัน, `ผง`=แผง, `ดก`=ดอก, `กส`=กิโลกรัม, `ชด`=ชุด, `ซง`=ซอง

## VAT Convention
ดู `/erp-formats` สำหรับตาราง vat_type (1=รวม, 2=แยก+7%, 0=ยกเว้น) และ UI badge
ระวัง: ชื่อเดิม "มี VAT" / "ไม่มี VAT" ใช้ไม่ได้แล้ว — แก้แล้ว 2026-04-17

## Payment Status Rules
- `paid_invoices` track **full payment** เท่านั้น — ถ้าจ่ายบางส่วนให้ **ไม่ใส่** ใน paid_invoices จนกว่าจะครบ
- ERP แสดงยอดบิลเต็มเสมอ (ไม่ track partial amount)
- **SR** (ใบลดหนี้) = credit note → net ใน sales_transactions ต้องเป็น **ลบ** เสมอ
- ตรวจสอบด้วย ลูกหนี้คงค้าง file (มี bill/paid/outstanding แยก) แทน บิลที่ถึงกำหนด (มีแค่ outstanding)

## สิ่งที่ต้องระวัง
- **Python 3.9**: ไม่รองรับ `int | None` syntax
- **วันที่ BSN**: เป็น Buddhist Era (พ.ศ.) ต้องแปลงก่อนบันทึก
- **recalculate stock**: `DELETE FROM stock_levels WHERE product_id=?` แล้ว INSERT จาก `SUM(quantity_change)`
- **เปลี่ยน unit_type**: ต้อง (1) update unit_type+cost ÷ ratio (2) ×ratio ทุก transaction (3) recalculate stock (4) update unit_conversions ratio
- **ลบ BSN sync**: (1) ลบ transactions ที่ note LIKE 'BSN%' (2) reset synced_to_stock=0 (3) recalculate stock
- **merge product**: UPDATE transactions/mapping/sales_transactions/purchase_transactions/unit_conversions SET product_id=NEW → recalculate stock NEW → DELETE stock_levels OLD → is_active=0 OLD
- **ย้าย transaction ข้ามสินค้า (one-time)**: DELETE txn เดิม → recalculate stock เก่า → INSERT txn ใหม่ → recalculate stock ใหม่ → UPDATE sales_transactions.product_id
- **import_log**: เช็คก่อนแนะนำให้ import — `SELECT * FROM import_log ORDER BY id DESC LIMIT 5`
- **BSN parse bug**: qty/unit บางบรรทัดติดกันด้วย `!` เช่น `2.00!มน` → แก้ใน parse_weekly.py line 97-98 แล้ว

## Templates สำคัญที่สร้างเพิ่ม
- `templates/trade_dashboard.html` — ภาพรวมการค้า, Top 10 สินค้าคลิกได้
- `templates/products/trade_summary.html` — สรุปการขายต่อสินค้า (Chart.js dual-axis)
- `templates/products/detail.html` — มี Shopee/Lazada stock card + ราคาขายปกติ/จริงจาก BSN (คลิกไปหน้า pricing)
- `templates/products/pricing.html` — ราคาขายสินค้า: ราคาตั้งแยกตาม vat_type + ราคาจริงเฉลี่ยต่อร้าน
- `templates/customers.html` — รายชื่อลูกค้า search + filter เขต + pagination
- `templates/customer_summary.html` — info card รหัส/เขต/พนักงานขาย + unpaid bills card (badge สีตาม vat_type)
- `templates/payment_status.html` — สถานะชำระหนี้ลูกหนี้ รายบิล + import modal (admin)
- `templates/payment_customers.html` — หนี้ค้างชำระรายลูกค้า + ช่องคาดคะเนยอดโอน (badge สีตาม vat_type)
- `templates/sales_doc.html` — เลขที่เอกสารขาย, Line column เรียง integer ASC

## โครงสร้างไฟล์
```
ERP/
  inventory_app/
    app.py          — routes ทั้งหมด
    models.py       — business logic + DB queries
    database.py     — schema + init_db()
    parse_weekly.py — parser BSN รายสัปดาห์ (cp874)
    config.py       — DATABASE_PATH, UPLOAD_FOLDER, SECRET_KEY
    instance/inventory.db
    templates/
      base.html
      trade_dashboard.html
      customers.html
      customer_summary.html
      transactions/history.html
      mapping.html
      unit_conversions.html
      products/
        detail.html
        trade_summary.html
  data/
    source/              — ต้นฉบับ CSV (ยังอยู่)
    source-backup.zip    — zip ของ source/ ทั้งหมด
    exports/             — ว่างเปล่า (ลบแล้ว)
  .claude/
    launch.json
    commands/
      erp-formats.md
      erp-context.md   ← ไฟล์นี้
```

## การเปลี่ยนแปลงในเซสชัน 2026-04-17 (session 1)
- Import `ยอดขาย_แยกตามลูกค้า_17.4.69(recheck).csv` → พบ 1,239 missing rows ใน 680 บิล
- สร้าง 83 placeholder products (SKU 1840–1922) + mappings + unit_conversions
- สร้างฟีเจอร์ **สถานะชำระหนี้** (`/payment-status`): import payment CSV → แสดง paid/unpaid
- เพิ่ม `received_payments` + `paid_invoices` tables ใน schema
- เพิ่ม `doc_base` column + indexes ใน `sales_transactions` (performance)
- Import payment CSV: 2,473 receipts, 7,330 paid invoices
- แก้ Flask reloader double-startup: `use_reloader=False`
- **Mapping review เสร็จสิ้น**: merge 8 bsn_codes, activate 75 สินค้าใหม่ (12 UNCERTAIN + 63 NO)
- unit_conversion `กล`: สายเอ็น #50=10ตัว/กล, #60=6ตัว/กล → unsynced=0
- **ประวัติขาย BSN ครบ**: batch=7,8 (979 rows) sync เป็น "ประวัติขาย (ไม่นับสต็อค)" IN+OUT pair + real OUT สำหรับ recent
- เพิ่ม unit_conversions 42 รายการ จาก unit_conversion_review
- เปลี่ยน unit_type หล→อัน/ตัว ×12 ใน 10 สินค้า (sku: 1892,1895,593,1872,1882,1896,1902,1903,1917,1918)
- remap `030บ3412` → sku=80 บานพับ(P)#412 GP สิงห์ (แผง), เพิ่ม ผง→1, ตว→1
- เพิ่มปุ่ม "ประวัติขาย BSN →" ในหน้า product detail → `/sales?product_id=X`
- `/sales` รองรับ filter `product_id` param แล้ว

## การเปลี่ยนแปลงในเซสชัน 2026-04-17 (session 2)
- สร้างหน้า **หนี้ค้างชำระรายลูกค้า** (`/payment-status/customers`) — summary cards + table
- คลิกชื่อลูกค้าจากหน้า payment → ไปที่ `/customer/<name>` (customer_summary) โดยตรง
- เพิ่ม **unpaid bills card** ในหน้า customer_summary (border-danger, แสดง doc_base + ยอด)
- แก้ payment queries ทุกตัวให้รองรับ VAT: `SUM(CASE WHEN vat_type=2 THEN net*1.07 ELSE net END)`
- กรอง SR (ใบลดหนี้) และ HS (เงินสด) ออกจากทุก payment query ด้วย `NOT LIKE 'SR%'` / `NOT LIKE 'HS%'`
- แก้ Line column ใน sales_doc.html ให้แสดงเลขบรรทัด เรียง integer ASC
- แก้ `purchase_transactions` เพิ่ม `doc_base` column (เคยขาดทำให้ import error)
- แก้ history_import rows ที่ net=0 แต่ total มีค่า → `UPDATE SET net=total` (82 rows)
- Import `ยอดขาย_แยกตามลูกค้า_17.4.69_from_2024(recheck)_new.csv` ครบถ้วน
- **ระบบป้องกัน duplicate import** ใน `import_weekly()`:
  - weekly format (ไม่มี suffix): ตรวจ `doc_base + bsn_code`
  - history format (มี suffix -N): ตรวจ `bsn_code + (doc_no = exact OR doc_no = doc_base)`
- ลบ 18 duplicate rows จาก weekly batch 7,8 ที่ซ้ำกับ history_import (IV6900524–IV6900532)
- Import HS ที่หาย: `HS6700002-1`, `HS6700020-1`, `HS6700006-2`
- อัปเดต 28 rows ที่ bsn_code ไม่ตรงกับ recheck file ให้ตรงตาม CSV

## การเปลี่ยนแปลงในเซสชัน 2026-04-23
- **แก้หน่วย ใบมีดคัตเตอร์เฉียง 30 องศา เล็ก** (product_id=726, sku=759):
  - unit_type: โหล → **หลอด** (12 หลอด = 1 โหล)
  - cost_price: 190 → 15.8333 บาท/หลอด
  - unit_conversions: หล ratio 1→**12**, หด/!หด คงที่ ratio=1
  - stock: 97 หลอด
  - แก้ IV6900487-1: unit หล→หด (BSN บันทึกผิด, ราคา 39 บาท = ราคาหลอด ไม่ใช่โหล)
  - หมายเหตุ: หด/!หด ใน BSN = หลอด (ratio=1), หล = โหล (ratio=12)
- **เพิ่มฟีเจอร์ Toggle Upload/Download DB** ใน admin sidebar:
  - `app.config['DB_ROUTES_ENABLED']` default=False (reset ทุก restart)
  - ปุ่ม toggle ใน sidebar (admin only) → เปิด/ปิด link Upload/Download
  - template: `templates/admin_upload_db.html`
  - PR #1: https://github.com/Zyringe/sendai-boonsawat-erp/pull/1

## การเปลี่ยนแปลงในเซสชัน 2026-04-20
- แก้บิล net=0 แต่ total>0 จำนวน 12 rows (IV6800557 → ยอด 804 บาท)
- แก้ filter payment queries: เพิ่ม `HAVING total_net > 0` และ `HAVING outstanding_amount > 0` เพื่อกรองบิล/ลูกค้าที่ยอดเป็น 0 ออก
- แก้ duplicate check ใน `import_weekly()`: เพิ่ม `unit_price` เข้า check → รองรับของแถม (unit_price=0) ที่มี bsn_code เดียวกัน
- เพิ่มฟีเจอร์ **คาดคะเนยอดโอน** ใน payment_customers: ช่อง "ยอดโอน" → `find_payment_candidates()` ลอง subset ของบิลทุก combo (tolerance ±5%/±200 บาท)
- เพิ่มหน้า **ราคาขายสินค้า** (`/products/<id>/pricing`): ราคาตั้ง (GROUP BY unit_price+vat_type + expand รายร้าน) + ราคาจริงเฉลี่ยต่อร้าน
- แก้หน้า product detail: ราคาขายปกติ/จริงดึงจาก BSN จริง (`get_product_pricing_summary()`) แทน `base_sell_price`
- เพิ่มสีบิล (VAT badge) ในหน้า payment_customers และ customer_summary: เขียว=รวม VAT, ฟ้า=แยก VAT, เทา=ยกเว้น VAT
- Merge SKU 1541 (มือจับบัวใหญ่, product_id=1504) → SKU 134 (product_id=134)
- แก้ RR6900056: เพิ่มของแถม 1 ตัว (ปืนยิงกาวเปลือย แกนคู่) → transaction IN +1
- **Import ของแถมทั้งหมดจาก history CSV**: ซื้อ 254 rows + ขาย 18 rows → sync stock 66 สินค้า
- เพิ่ม IN pair สำหรับของแถมขายที่วันก่อน cutoff 3/3/69 (18 rows) เพื่อ offset OUT (ไม่นับสต็อก)
- แก้ IV6900527-4: ย้าย product จาก SKU 407 (7นิ้ว 60T ธรรมดา) → SKU 408 (C7 SUPER THIN)
- **Stock ติดลบเหลือ 0** ✅ (จากเดิม 8 sku)

## การเปลี่ยนแปลงในเซสชัน 2026-04-07
- ลบแท็บ "ตรวจสอบรายการสงสัย" ออกจาก sidebar
- แก้ performance หน้าแปลงหน่วย (6.7s → 0.3s) — เปลี่ยน correlated subquery เป็น LEFT JOIN aggregate
- เพิ่ม search + pagination (ellipsis style) ในหน้าแปลงหน่วย
- zip `data/source/` → `data/source-backup.zip`, ลบไฟล์ใน `data/exports/`
- Merge SKU 1436 (บานพับ 3.2mm, product_id=1399) → SKU 93 (product_id=93)
- Merge SKU 1286 (GOLDEN LION 8", product_id=1249) → SKU 287 (product_id=285)
- เพิ่ม unit_conversions: `อน=1` (product 56, 55), `กส=1` (product 415), `ชด=1` (product 253)
- sync ครบ → unsynced = 0
- สร้าง `customer_regions` table จาก CSV (272 rows)
- สร้าง `/customers` route + `customers.html` (search + region filter + pagination)
- อัปเดต `customer_summary.html` ให้แสดง info card รหัส/เขต/พนักงานขาย
- เพิ่ม sidebar link "ลูกค้า"
