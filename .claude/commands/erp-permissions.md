# ERP Permission System — Sendai Boonsawat

คู่มือระบบสิทธิ์ใช้งาน, pattern การเพิ่มสิทธิ์, และ gotchas ที่พบบ่อย

---

## Role Hierarchy

```
admin > manager > staff
```

| สิทธิ์ | Staff | Manager | Admin |
|--------|:-----:|:-------:|:-----:|
| ดูสต็อก/ยอดขาย | ✅ | ✅ | ✅ |
| Import ไฟล์ / อัพเดทข้อมูล | ✅ | ✅ | ✅ |
| ผูกรหัส BSN / แปลงหน่วย | ✅ | ✅ | ✅ |
| กำหนดสถานที่เก็บสินค้า | ✅ | ✅ | ✅ |
| เพิ่ม/แก้ไขสูตรแปลงสินค้า | ✅ | ✅ | ✅ |
| เห็นราคาทุน / GP | ❌ | ✅ | ✅ |
| สถานะชำระหนี้ | ❌ | ✅ | ✅ |
| ลบสูตรแปลงสินค้า | ❌ | ✅ | ✅ |
| แก้ไขข้อมูลสินค้า | ❌ | ❌ | ✅ |
| จัดการผู้ใช้ | ❌ | ❌ | ✅ |
| จำลอง role (simulate) | ❌ | ❌ | ✅ |

---

## POST Whitelist (app.py บรรทัด ~41)

```python
_STAFF_POST_OK = frozenset([
    'login', 'logout',
    'import_weekly', 'mapping_save',
    'unit_conversions_save', 'unit_conversions_edit',
    'product_location_save',
    'admin_exit_simulate',
    'conversion_new', 'conversion_edit',
])
_MANAGER_POST_OK = _STAFF_POST_OK | frozenset([
    'import_payments', 'product_online_stock',
    'conversion_run', 'conversion_edit', 'conversion_delete',
])
# admin: POST ได้ทุก route
```

`require_login` (before_request) ตรวจ POST เท่านั้น — GET ไม่โดน whitelist

---

## Context Processor (`inject_auth`)

ทุก template เข้าถึง variables เหล่านี้:

| Variable | ค่า |
|----------|-----|
| `is_admin` | `role == 'admin'` |
| `is_manager` | `role in ('admin', 'manager')` |
| `current_role` | `'admin'` / `'manager'` / `'staff'` |
| `current_user` | display_name |
| `simulating_as` | role ที่จำลองอยู่ (None ถ้าไม่ได้จำลอง) |
| `real_role` | role จริงของ admin ขณะ simulate |

---

## Pattern: เพิ่มสิทธิ์ให้ Route ใหม่

### 1. เพิ่ม endpoint ใน whitelist (ถ้าเป็น POST)

```python
# ถ้าต้องการให้ staff POST ได้
_STAFF_POST_OK = frozenset([
    ...,
    'my_new_route',
])

# ถ้าต้องการให้ manager+ POST ได้
_MANAGER_POST_OK = _STAFF_POST_OK | frozenset([
    ...,
    'my_new_route',
])
```

### 2. Route guard ใน function

```python
# เฉพาะ admin
if session.get('role') != 'admin':
    abort(403)

# manager ขึ้นไป
if session.get('role') not in ('admin', 'manager'):
    abort(403)

# ทุก role ที่ login แล้ว (ไม่ต้อง guard เพิ่ม เพราะ require_login จัดการแล้ว)
if not session.get('role'):
    abort(403)
```

### 3. Template guard

```jinja
{% if is_admin %}      {# admin เท่านั้น #}
{% if is_manager %}    {# manager + admin #}
{% if current_role %}  {# ทุก role ที่ login #}
```

---

## Features ที่เพิ่มใน Session นี้

| Feature | Route / Endpoint | สิทธิ์ |
|---------|-----------------|--------|
| แก้ไขสถานที่เก็บสินค้า | `POST /products/<id>/location` | staff+ |
| ลบผู้ใช้ | `POST /users/<id>/delete` | admin (ห้ามลบ admin) |
| จำลอง role | `POST /admin/simulate-role` | admin |
| ออกจาก simulate | `POST /admin/exit-simulate` | ทุก role (อยู่ใน STAFF_POST_OK) |
| ลบสูตรแปลงสินค้า | `POST /conversions/<id>/delete` | manager+ |
| รายชื่อ Supplier | `GET /suppliers` | ทุก role |
| สรุป Supplier | `GET /supplier/<name>` | ทุก role |

---

## Simulate Role (Admin Feature)

Admin กดปุ่ม 🪪 ข้างชื่อ user ในหน้า `/users` เพื่อจำลองดูระบบในฐานะ role นั้น

- session `_real_role` = 'admin' (เก็บ role จริง)
- session `role` = role ที่จำลอง
- Banner สีเหลืองปรากฏทุกหน้า
- กด "ออกจากโหมดจำลอง" → `POST /admin/exit-simulate` → คืน role เป็น admin

---

## ⚠️ Gotcha: werkzeug BuildError หลังเพิ่ม Route ใหม่

**อาการ**: `werkzeug.routing.exceptions.BuildError` บนหน้าที่เพิ่ม `url_for('new_endpoint')` ใน template

**สาเหตุ**: Flask auto-reloader reload template ได้ทันที แต่ reload `app.py` ไม่สำเร็จ
→ template บน disk มี endpoint ใหม่ แต่ URL map ใน memory ยังเป็นเวอร์ชันเก่า

**แก้ไข**: **Restart server ด้วยมือทุกครั้งที่เพิ่ม route ใหม่** (Ctrl+C แล้ว start ใหม่)

---

## Template Pattern: ปุ่มที่ต้องการ Confirm

```jinja
<form method="post" action="{{ url_for('endpoint', id=item.id) }}"
      class="d-inline"
      onsubmit="return confirm('คุณแน่ใจ?')">
  <button type="submit" class="btn btn-sm btn-danger">
    <i class="bi bi-trash"></i>
  </button>
</form>
```

## Template Pattern: Inline Edit (collapse)

```jinja
<button data-bs-toggle="collapse" data-bs-target="#edit-{{ item.id }}">แก้ไข</button>
<tr class="collapse" id="edit-{{ item.id }}">
  <td colspan="N">
    <form method="post" action="...">...</form>
  </td>
</tr>
```
