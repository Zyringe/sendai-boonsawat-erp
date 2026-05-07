# Runbook — Upload Local DB ขึ้น Prod

> **เมื่อไหร่ใช้ runbook นี้:** หลังทำ bulk work บน local SQLite (mass rename, schema migration, brand backfill ฯลฯ) แล้วต้องการ push ขึ้น prod
>
> **กฎเหล็ก:** ห้าม upload DB **โดยไม่ pull ก่อน**. Skip step นี้ = ของเพื่อนระหว่าง pull-push ครั้งก่อนกับครั้งนี้หาย

---

## ผู้เกี่ยวข้อง 2 คน

- **Put** — ทำงาน bulk บน local (master data, schema, structured columns)
- **เพื่อน** — upload weekly/daily transaction files ผ่านปุ่ม "อัพเดทข้อมูล" (INSERT-with-dedup, idempotent)

---

## Workflow ก่อน upload prod (8 ขั้น)

### 1. แจ้งเพื่อนล่วงหน้า

> "อีก 30 นาทีจะอัป DB อย่าเพิ่ง upload weekly file นะ จะแจ้งอีกรอบเมื่อเสร็จ"

### 2. Pull prod DB → local

- เปิด prod website → กดปุ่ม **Download DB**
- Save แทนที่ `sendy_erp/inventory_app/instance/inventory.db`

### 3. Backup ทันที

```bash
TS=$(date +%Y-%m-%d_%H%M%S)
cp sendy_erp/inventory_app/instance/inventory.db \
   sendy_erp/data/backups/inventory-pulled-prod-${TS}.db
```

### 4. ทำงาน bulk บน local

- รัน migrations (`sqlite3 inventory.db < data/migrations/NNN_*.sql`)
- รัน apply scripts (`--apply` flag)
- Verify ด้วย sample queries

### 5. Backup before-upload (safety net)

```bash
TS=$(date +%Y-%m-%d_%H%M%S)
cp sendy_erp/inventory_app/instance/inventory.db \
   sendy_erp/data/backups/inventory-pre-upload-${TS}.db
```

### 6. Upload local → prod

- เปิด prod website → กด **เปิด Upload/Download DB**
- Upload `inventory.db`
- กด **ปิด Upload/Download DB** (สำคัญ — ทิ้งเปิดไว้ = security risk)

### 7. Verify บน prod

- เปิด `/products` → sample 5 SKUs ที่เพิ่ง rename → ชื่อตรงไหม
- เปิด `/sales` → ยอดล่าสุดมีอยู่ไหม

### 8. แจ้งเพื่อน + ขอ re-upload

> "อัปเสร็จแล้ว ขอให้ re-upload weekly file ของอาทิตย์นี้อีกรอบ — ระบบมี dedup ไม่ดับเบิ้ล แต่ของอาทิตย์ที่อัปไประหว่าง 30 นาทีนั้นจะหาย"

ขั้นนี้สำคัญ — เพื่อน re-upload = transaction ที่หายระหว่าง pull-push กลับคืนผ่าน dedup

---

## ❗ Recovery — ถ้าลืม pull ก่อน upload

อาการ: เพื่อนแจ้ง "transactions อาทิตย์นี้หาย"

แก้:
1. **อย่า panic** — เพื่อน upload ไฟล์เดิมซ้ำได้เลย (dedup INSERT)
2. ขอให้เพื่อน upload ไฟล์ของช่วงที่หาย (รายวัน/รายสัปดาห์ทุกไฟล์ตั้งแต่ครั้งสุดท้ายที่ Put pull prod)
3. Verify บน prod ยอดถูกหรือไม่
4. ถ้า dedup ทำงานเพี้ยน → ใช้ backup ที่ Put pulled มาเก็บไว้ใน step 2 → restore กลับ → ทำใหม่ตั้งแต่ step 4

---

## Naming convention ของ backup

```
sendy_erp/data/backups/
  inventory-pulled-prod-YYYY-MM-DD_HHMMSS.db    ← step 2: ก่อนเริ่มทำงาน local
  inventory-pre-upload-YYYY-MM-DD_HHMMSS.db     ← step 5: ก่อนอัปขึ้น prod
  inventory-pre-<work-name>-YYYY-MM-DD_HHMMSS.db ← ก่อน specific bulk op
```

เก็บไว้อย่างน้อย 30 วัน. ลบของเก่ากว่านั้นเพื่อประหยัด disk

---

## ข้อตกลงกับเพื่อน

1. เพื่อน**เก็บไฟล์ที่ upload** ไว้อย่างน้อย 30 วัน
2. ตอบ Put ภายใน 5 นาทีเมื่อ Put แจ้ง "จะอัป DB"
3. หลัง Put อัปเสร็จ → re-upload ไฟล์ล่าสุดทันที

---

## ✅ Shortcut — Master-only mode (shipped 2026-05-07)

**ลดทอน workflow ข้างบนมาก** — ใช้โหมดนี้ถ้าแก้แค่ master data (products, brands, categories, color codes ฯลฯ)

ขั้นตอนใหม่:

1. (Optional) แจ้งเพื่อน ไม่ต้องหยุดอัปก็ได้ — โหมดนี้ไม่แตะ transaction tables
2. **Pull prod DB** (เผื่อ Put ต้องการให้ local sync ก่อน — ไม่ required สำหรับ master-only)
3. ทำงาน bulk บน local
4. กด **เปิด Upload/Download DB** → Upload form
5. **เลือก radio "Master-only (แนะนำ)"** ← key step
6. Upload → ระบบจะ:
   - Auto-backup ปัจจุบันเป็น `inventory-pre-master-upload-{ts}.db`
   - ATTACH uploaded DB
   - DELETE + INSERT 33 master tables
   - Verify FK integrity (rollback ถ้า fail)
   - Transaction tables ของเพื่อน**ปลอดภัย**
7. ปิด Upload/Download DB

**ใช้ Full Replace mode เฉพาะเมื่อ:**
- ต้อง sync transaction tables (เช่น Put แก้ historical sales บน local)
- Schema change ใหญ่ที่กระทบ transaction tables
- Master-only mode ล้มเหลวเพราะ FK violation

ดู feature spec ใน `feature_selective_db_upload.md`
