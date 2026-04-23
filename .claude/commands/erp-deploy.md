# ERP Deploy & Auth Reference — Sendai Boonsawat

Reference สำหรับ deploy Flask ERP ขึ้น Railway และจัดการระบบ auth หลายระดับ

---

## Live URLs
- **Production:** https://web-production-1554c.up.railway.app
- **GitHub Repo:** https://github.com/Zyringe/sendai-boonsawat-erp
- **Local path:** `/Users/put/Documents/Sendai-Boonsawat/ERP`

---

## ระบบ Auth (3 ระดับ)

| Role | สิทธิ์ |
|---|---|
| **admin** | ทุกอย่าง + จัดการ users + เห็นราคาทุน/GP |
| **manager** | เห็นราคาทุน/GP + import payments + ดูทุกรายงาน |
| **staff** | import ไฟล์สัปดาห์ + mapping + unit_conversions + ดูสต็อก/ยอดขาย (ไม่เห็นราคาทุน) |

### Implementation details
- Users เก็บใน table `users` (werkzeug password hash)
- Session keys: `role`, `user_id`, `username`, `display_name`
- `inject_auth()` inject `is_admin`, `is_manager`, `current_user`, `current_role` ใน templates
- **Staff POST whitelist:** `login`, `logout`, `import_weekly`, `mapping_save`, `unit_conversions_save`
- **Manager POST whitelist:** staff + `import_payments`, `product_online_stock`
- Admin seed: สร้าง user `admin` จาก `ADMIN_PASSWORD` env var โดยอัตโนมัติถ้า users table ว่าง
- User management: `/users` (admin only) — เพิ่ม/แก้ไข/ปิดใช้งาน
- Templates ใช้ `{% if is_manager %}` ซ่อนราคาทุน/GP จาก staff

---

## Railway Deployment

### ไฟล์ที่จำเป็น
```
Procfile:     web: gunicorn --chdir inventory_app -w 2 -b 0.0.0.0:$PORT app:app
railway.toml: builder=nixpacks, healthcheck path=/
requirements.txt: flask>=3.1, werkzeug>=3.1, gunicorn>=21.0, pandas>=2.0, openpyxl>=3.1
```

### Environment Variables (ตั้งใน Railway → Variables)
```
SECRET_KEY      = (random string ยาวๆ)
ADMIN_PASSWORD  = (รหัสผ่าน admin ตั้งต้น)
DATA_DIR        = /data
```

### Persistent Volume
- Add Volume → Mount Path: `/data`
- SQLite database จะอยู่ที่ `/data/inventory.db`
- `config.py` อ่าน `DATA_DIR` จาก env var → `DATABASE_PATH = DATA_DIR/inventory.db`

### Deploy flow
1. Push code ขึ้น GitHub → Railway auto-deploy
2. ถ้าไม่ auto-deploy: Railway dashboard → service → Deployments → Redeploy

---

## Database Migration (Local → Railway)

### วิธีที่แนะนำ — Toggle Upload/Download ใน Sidebar (ถาวรแล้ว ไม่ต้องเพิ่ม temp route)

routes `/admin/upload-db` และ `/admin/download-db` มีอยู่ใน codebase แล้ว แต่ถูกป้องกันด้วย flag:
- `app.config['DB_ROUTES_ENABLED']` default=**False** ทุกครั้งที่ server restart
- Admin กดปุ่ม **"เปิด Upload/Download DB"** ใน sidebar → routes เปิด
- หลังใช้งานเสร็จ กดปิด หรือปล่อยให้ Railway redeploy ปิดให้อัตโนมัติ

**ขั้นตอน upload local DB ขึ้น Railway:**
1. Login production เป็น admin
2. กด **"เปิด Upload/Download DB"** ใน sidebar
3. กด **"Upload Database"** → เลือกไฟล์ `inventory_app/instance/inventory.db`
4. กด **"ปิด Upload/Download DB"** หลังเสร็จ

---

## Emergency Admin Reset

ถ้า login ไม่ได้ เพิ่ม route ชั่วคราว:

```python
@app.route('/admin/reset-admin/<token>')
def reset_admin(token):
    if token != 'sendai-reset-2026':
        abort(404)
    conn = get_connection()
    existing = conn.execute("SELECT id FROM users WHERE username='admin'").fetchone()
    if existing:
        conn.execute("UPDATE users SET password_hash=?, is_active=1 WHERE username='admin'",
                     (generate_password_hash('admin1234'),))
    else:
        conn.execute("INSERT INTO users(username,password_hash,display_name,role) VALUES(?,?,?,?)",
                     ('admin', generate_password_hash('admin1234'), 'Administrator', 'admin'))
    conn.commit()
    conn.close()
    return '<h2>Reset สำเร็จ — username: admin / password: admin1234</h2><a href="/login">Login</a>'
```

เข้า URL: `/admin/reset-admin/sendai-reset-2026` → login ด้วย `admin` / `admin1234` → **ลบ route ทิ้งทันที**

---

## Push to GitHub

### ปัญหาที่พบบ่อย

**1. Token ไม่มี scope `repo`**
- ไปสร้างใหม่ที่ Settings → Developer settings → Personal access tokens → Tokens (classic)
- ต้องติ๊ก ✅ **repo** (ทั้ง checkbox ใหญ่)

**2. GitHub Push Protection block**
- เกิดจากมี token/secret ใน `.claude/settings.local.json` (จาก allowed commands)
- Railway/GitHub จะให้ URL เพื่อ unblock → ไปกด "Allow secret" (token เก่าที่ revoke แล้วไม่มีความเสี่ยง)
- อย่าแชร์ token ใน chat

**3. Push command**
```bash
git remote set-url origin https://TOKEN@github.com/Zyringe/sendai-boonsawat-erp.git
git push -u origin main
```

---

## Temporary Routes Checklist

หลัง migration เสร็จ ต้องลบออกและ redeploy:
- [ ] `/admin/upload-db` — upload database
- [ ] `/admin/reset-admin/<token>` — reset admin password
