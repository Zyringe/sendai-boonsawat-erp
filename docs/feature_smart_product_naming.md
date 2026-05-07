# Feature spec — Smart product-naming on new-product entry

> **Status:** idea, not built. Captured 2026-05-06.
> **Owner:** flask-dev (when picked up).
> **Related skill:** `product-spec-parse` (workspace-level Claude skill, parses competitor names — different use case).

## Goal

ตอนผู้ใช้สร้างสินค้าใหม่ใน Sendy (Flask app, route `/products/new` → `blueprints/products.py:product_new`), แทนที่จะกรอก field ทุกช่องเอง, ให้ผู้ใช้พิมพ์ **ชื่อสินค้า** หรือ **คำอธิบายอิสระ** แล้วระบบ suggest ค่าของ field structured อื่นๆ ให้ทันที — แล้ว user แค่ confirm/แก้.

## Why

- 1,978 SKUs ปัจจุบัน — ผู้ใช้สร้างเองด้วยมือ, naming consistency ต่ำ (เลย rename pass 970 rows ใน 2026-05-06)
- ทุกครั้งที่เพิ่ม SKU ใหม่ → user ต้องคิด: brand_id, category_id, color_code, packaging, family_id ฯลฯ
- ส่วนใหญ่ derive ได้จากชื่อสินค้าโดยอัตโนมัติถ้าทำตามกฎ `product_name_naming_rule.md`
- ลด data-quality regression — ทุก SKU ใหม่จะตรงตามกฎตั้งแต่แรก ไม่ต้องไล่ rename ทีหลัง

## User flow (proposed)

### Phase 1 — On new product form

1. User เปิด `/products/new`
2. มี **2 input boxes บน form**:
   - **"พิมพ์ชื่อสินค้า / รายละเอียด"** (free text, full width) — สำหรับ suggest mode
   - SKU (number) — auto-populated เป็น `MAX(sku)+1` ให้แล้ว, edit ได้
3. User พิมพ์ตัวอย่าง: `บานพับสแตนเลส Sendai 170 4 นิ้ว สี AC แบบแผง`
4. **Click "วิเคราะห์ชื่อ"** หรือ auto-trigger เมื่อ blur
5. Backend route `POST /products/parse-suggest` รับ text → return JSON:
   ```json
   {
     "category": "บานพับสแตนเลส",
     "brand_id": 1, "brand_name": "Sendai",
     "model": "#170", "size": "4in",
     "color_code": "AC", "color_th": "สีรมดำ",
     "packaging": "แผง",
     "proposed_name": "บานพับสแตนเลส Sendai #170-4in สีรมดำ (AC) (แผง)",
     "confidence": {"category": "high", "brand": "high", "color_code": "high", ...}
   }
   ```
6. Form fields populate ด้วยค่า suggested + show confidence color (เขียว/เหลือง/แดง)
7. User confirm หรือแก้ field ที่ยังไม่ถูก แล้ว Submit

### Phase 2 — On batch import (CSV / xlsx)

ถ้าเพิ่มสินค้าหลายรายการ → upload CSV ที่มี column `description` → backend parse แต่ละ row → return preview ของทั้ง batch + confidence flag → user confirm → INSERT batch.

## Implementation outline

### Backend

- เพิ่ม route `POST /products/parse-suggest` ใน `blueprints/products.py`
  - Input: `{"text": "..."}` (JSON)
  - Process: import + call `parse_sku_names.parse_name()` ด้วย DB connection (load brands + color_codes)
  - Output: JSON ตามตัวอย่างข้างบน
- ส่วน `parse_sku_names.py` ทำ refactor นิดหน่อยให้ parse_name() เรียกได้แบบ standalone (รับ string เดียว, ไม่ต้องผ่าน CSV)
- Compose proposed_name โดยเรียก `build_name_from_columns.build()` หรือ inline
- ทำ test สำหรับ route นี้: `tests/test_products_parse_suggest.py`

### Frontend

- Edit `templates/products/form.html`:
  - เพิ่ม textarea "พิมพ์ชื่อสินค้า / รายละเอียด"
  - เพิ่มปุ่ม "วิเคราะห์ชื่อ" + JS handler ที่ POST → parse-suggest → fill form
  - เพิ่ม confidence indicator (badge เขียว/เหลือง/แดง) หน้าทุก field ที่ถูก populate
- ใช้ existing form layout, ไม่ต้องสร้าง modal ใหม่

### DB

- ไม่มี schema change — feature นี้แค่ wrap parser logic + UI

## Edge cases

| Case | Behavior |
|---|---|
| Brand ไม่อยู่ใน registry | suggest `brand: null`, แสดงเขียนว่า "Brand ใหม่? เพิ่มก่อนค่อย save" |
| Color ไม่มี code | suggest `color_th` only, `color_code: null` (ลายฆ้อน, ลายคราม) |
| Multiple matches | choose highest-confidence, แสดง alternatives ใน dropdown |
| User พิมพ์อย่างย่อ ("สแตนเลส 4นิ้ว") | low-confidence parse, populate เท่าที่ทำได้, mark fields เป็นเหลือง |
| Bundle (มี `+` ระหว่าง 2 ชนิด) | flag `is_bundle: true`, แนะนำให้ user ตัดสินใจว่าจะ track เป็น flat SKU หรือ link components |
| ชื่อซ้ำกับ SKU เดิม | warn "ชื่อนี้มีในระบบแล้ว: SKU 170 — ใช้ขนาดอื่นหรือ family เดียวกันมั้ย?" |

## Acceptance criteria

- [ ] Route `POST /products/parse-suggest` returns valid JSON within 200ms (1 product)
- [ ] Form auto-populates ≥6 fields from a typical input string
- [ ] Confidence indicator visible per populated field
- [ ] Submit creates SKU with all expected fields filled correctly
- [ ] Test coverage: parse correctness on 50 sample inputs (use `data/exports/sku_name_parsed.csv` first 50 rows as test set)

## Why this stays in Sendy (not a Claude skill)

- Lives close to the workflow it serves — user creates SKU **inside the ERP**, not via Claude chat
- Need ↔ DB tight coupling (brand_id resolution, MAX(sku)+1 lookup, INSERT after confirm)
- Used by **all team members** including ones who don't have Claude Code installed
- Performance — should respond in <200ms, not after a Claude API roundtrip
- The Claude skill `product-spec-parse` covers a different use case (competitor analysis, batch parse) — outside the ERP

## Out of scope (defer)

- Auto-creating brand entries (user decides whether to add new brand first)
- Catalog auto-grouping into family (separate `family_id` assignment workflow)
- Image upload during product creation (separate `product_images` workflow)
- Bulk import of competitor data — that's `product-spec-parse` skill's job
