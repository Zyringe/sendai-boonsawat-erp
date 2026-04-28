# ERP File Format Reference

Load this as context when working with BSN import files or reference CSVs.

---

## BSN Weekly Report Files (cp874)

**Encoding:** cp874 (Thai Windows)
**Non-breaking space:** `\xa0` used as padding — strip with `.replace('\xa0', ' ')`
**Date format:** Buddhist Era short year `DD/MM/YY` → convert: `year = (2500 + YY) - 543` → ISO `YYYY-MM-DD`

### File Types
| Keyword in file | Type | Doc-no format |
|-----------------|------|---------------|
| `ขาย` | sales | `IV6900478-  1` (spaces inside) → normalize `re.sub(r'\s+','',doc)` |
| `ซื้อ` | purchase | `HP6900017` (single token) |

### Line Structure (indentation-based)
```
(skip) — headers: (BSN), รายงาน, รหัส, วันที่, พนักงาน, เลือก, สินค้า วัน, รวมตาม, ----, ====
  party line    — 2 leading spaces — "Name /CODE"
   product line — 3 leading spaces — "Name /CODE"
    txn line    — contains DD/MM/YY date — regex captures: date doc_no qty unit unit_price vat discount total _ignored net
```

### Transaction Regex Groups
```
group 1: date (DD/MM/YY BE)
group 2: doc_no
group 3: qty       (comma-formatted float) ← strip '!' before parsing: "2.00!มน" → qty=2.00
group 4: unit      ← strip '!' before use: "2.00!มน" → unit="มน"
group 5: unit_price
group 6: vat_type  (int) — 1=รวม VAT, 2=แยก VAT (+7%), 0=ยกเว้น VAT
group 7: discount  (e.g. "5%", "10+5%", "")
group 8: total
group 9: net       (skip one column before this)
```

> **⚠️ parse bug:** BSN บางไฟล์ qty และ unit ติดกันด้วย `!` เช่น `2.00!มน` — `parse_weekly.py` แก้แล้วที่ line 97-98 ให้ `.replace('!', '')` ก่อน parse ถ้าเจอ rows_skipped สูงผิดปกติ ให้ตรวจ raw file

### VAT Type Convention
| vat_type | ความหมาย | แสดงใน UI |
|----------|----------|----------|
| 1 | ราคา **รวม VAT** แล้ว | badge "รวม VAT" |
| 2 | ราคา **ยังไม่รวม VAT** → +7% | badge "แยก VAT" + แสดง VAT 7% ใน footer |
| 0 | ยกเว้น VAT | badge "ยกเว้น VAT" |

---

## Reference CSV Files (`data/source/`)

### Inventory Management - Product_Master.csv (UTF-8)
`SKU, Product_Name, บรรจุ/ลัง, บรรจุ/กล่อง, หน่วย, ขายยาก`
Product names use `'S/D'` for Sendai brand, `4"` for inch notation.

### Inventory Management - Location.csv (UTF-8)
`Floor-No, รายการ`
- Floor-No `-` = no location assigned
- One row per location; same product can appear on multiple rows (multi-location)
- Name normalization to match DB: `'S/D'→Sendai`, `#GL-→#Golden Lion - `, `'G/L'→Golden Lion`, `\bS/D\b→Sendai`, `(\d+)"→\1นิ้ว`, `#GL\s*-\s*→#Golden Lion - `
- After normalization, also normalize whitespace in DB keys: `re.sub(r'\s+', ' ', name.strip())`

### mapping_suggestions.csv (exports, UTF-8)
`status, score, bsn_code, bsn_name, suggested_sku, suggested_product_name, product_id, ยืนยัน`

### ลูกหนี้คงค้าง (cp874) — Detailed AR Outstanding
```
4-space indent: date  IV/SR-no  salesperson  bill_amount  paid_amount  outstanding_amount
                                RE-no        date         paid_amount
```
- `bill_amount` = ยอดเต็มบิล (ไม่รวม VAT ถ้า vat_type=2)
- `outstanding_amount` = ยอดค้างจริง (หลังหักที่จ่ายแล้ว)
- SR = credit note → outstanding เป็นลบ

### บิลที่ถึงกำหนด (cp874) — Due Bills
```
3-space indent: due_date  IV/SR-no  bill_date  amount  [VAT-ref]
```
- `amount` = ยอดคงค้าง (ไม่ใช่ยอดเต็มบิล ถ้ามี partial payment)
- `VAT-ref` เช่น `VAT26/097` = เลขใบกำกับภาษี ไม่ใช่หลักฐานชำระเงิน
