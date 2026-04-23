import csv
import io
import os
import sys
from datetime import date

from flask import (Flask, render_template, request, redirect, url_for,
                   flash, session, jsonify, abort, send_file)
from werkzeug.security import generate_password_hash, check_password_hash

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
import models
from database import init_db, get_connection
from parse_weekly import parse_sales, parse_purchases, detect_file_type
from parse_platform import (parse_shopee, parse_lazada, export_shopee, export_lazada,
                            export_mapping, parse_mapping)

app = Flask(__name__)
app.config['SECRET_KEY'] = config.SECRET_KEY
app.config['JSON_AS_ASCII'] = False
app.config['UPLOAD_FOLDER'] = config.UPLOAD_FOLDER
app.config['ITEMS_PER_PAGE'] = config.ITEMS_PER_PAGE
app.config['DB_ROUTES_ENABLED'] = False

os.makedirs(config.UPLOAD_FOLDER, exist_ok=True)

with app.app_context():
    init_db()


# ── Auth ──────────────────────────────────────────────────────────────────────
#
# Roles: admin > manager > staff
#   admin   – full access + user management
#   manager – see cost/GP/payments; cannot edit products/users
#   staff   – import weekly flow + read-only views (no cost/GP)
#
# POST whitelist by role
_STAFF_POST_OK = frozenset([
    'login', 'logout',
    'import_weekly', 'mapping_save', 'unit_conversions_save',
])
_MANAGER_POST_OK = _STAFF_POST_OK | frozenset([
    'import_payments', 'product_online_stock',
])
# admin can POST anything


@app.context_processor
def inject_auth():
    role = session.get('role', '')
    return {
        'is_admin':    role == 'admin',
        'is_manager':  role in ('admin', 'manager'),
        'current_user': session.get('display_name', ''),
        'current_role': role,
        'alert_count': models.count_stock_alerts(),
        'db_routes_enabled': app.config['DB_ROUTES_ENABLED'],
    }


@app.before_request
def require_login():
    endpoint = request.endpoint
    # Allow static files and login page without authentication
    if endpoint in ('login', 'static'):
        return
    role = session.get('role', '')
    if not role:
        flash('กรุณาเข้าสู่ระบบก่อน', 'warning')
        return redirect(url_for('login', next=request.url))
    if request.method != 'POST':
        return
    if role == 'staff' and endpoint not in _STAFF_POST_OK:
        flash('ไม่มีสิทธิ์ดำเนินการนี้', 'danger')
        return redirect(url_for('dashboard'))
    if role == 'manager' and endpoint not in _MANAGER_POST_OK:
        flash('ต้องใช้บัญชี Admin เท่านั้น', 'danger')
        return redirect(url_for('dashboard'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        conn = get_connection()
        user = conn.execute(
            "SELECT * FROM users WHERE username=? AND is_active=1", (username,)
        ).fetchone()
        conn.close()
        if user and check_password_hash(user['password_hash'], password):
            session.clear()
            session['user_id']      = user['id']
            session['username']     = user['username']
            session['display_name'] = user['display_name'] or user['username']
            session['role']         = user['role']
            flash(f'ยินดีต้อนรับ {session["display_name"]}', 'success')
            return redirect(request.args.get('next') or url_for('dashboard'))
        flash('ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง', 'danger')
    return render_template('login.html')


@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    flash('ออกจากระบบแล้ว', 'success')
    return redirect(url_for('dashboard'))


# ── User management (admin only) ──────────────────────────────────────────────

@app.route('/users')
def user_list():
    if session.get('role') != 'admin':
        abort(403)
    conn = get_connection()
    users = conn.execute("SELECT * FROM users ORDER BY role, username").fetchall()
    conn.close()
    return render_template('users.html', users=users)


@app.route('/users/new', methods=['POST'])
def user_new():
    if session.get('role') != 'admin':
        abort(403)
    username     = request.form.get('username', '').strip()
    display_name = request.form.get('display_name', '').strip()
    role         = request.form.get('role', 'staff')
    password     = request.form.get('password', '')
    if not username or not password:
        flash('กรุณากรอกชื่อผู้ใช้และรหัสผ่าน', 'danger')
        return redirect(url_for('user_list'))
    if role not in ('admin', 'manager', 'staff'):
        role = 'staff'
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO users(username, password_hash, display_name, role) VALUES (?,?,?,?)",
            (username, generate_password_hash(password), display_name or username, role)
        )
        conn.commit()
        flash(f'เพิ่มผู้ใช้ {username} ({role}) สำเร็จ', 'success')
    except Exception:
        flash(f'ชื่อผู้ใช้ "{username}" ซ้ำในระบบ', 'danger')
    finally:
        conn.close()
    return redirect(url_for('user_list'))


@app.route('/users/<int:uid>/edit', methods=['POST'])
def user_edit(uid):
    if session.get('role') != 'admin':
        abort(403)
    display_name = request.form.get('display_name', '').strip()
    role         = request.form.get('role', 'staff')
    is_active    = 1 if request.form.get('is_active') else 0
    new_password = request.form.get('password', '').strip()
    if role not in ('admin', 'manager', 'staff'):
        role = 'staff'
    conn = get_connection()
    if new_password:
        conn.execute(
            "UPDATE users SET display_name=?, role=?, is_active=?, password_hash=? WHERE id=?",
            (display_name, role, is_active, generate_password_hash(new_password), uid)
        )
    else:
        conn.execute(
            "UPDATE users SET display_name=?, role=?, is_active=? WHERE id=?",
            (display_name, role, is_active, uid)
        )
    conn.commit()
    conn.close()
    flash('อัปเดตผู้ใช้สำเร็จ', 'success')
    return redirect(url_for('user_list'))


# ── Temp: Download DB (ลบออกหลังใช้) ─────────────────────────────────────────

@app.route('/admin/toggle-db-routes', methods=['POST'])
def toggle_db_routes():
    if session.get('role') != 'admin':
        abort(403)
    app.config['DB_ROUTES_ENABLED'] = not app.config['DB_ROUTES_ENABLED']
    state = 'เปิด' if app.config['DB_ROUTES_ENABLED'] else 'ปิด'
    flash(f'{state}การเข้าถึง Upload/Download Database แล้ว', 'success')
    return redirect(request.referrer or url_for('dashboard'))


@app.route('/admin/download-db')
def download_db():
    if session.get('role') != 'admin':
        abort(403)
    if not app.config['DB_ROUTES_ENABLED']:
        abort(403)
    return send_file(config.DATABASE_PATH, as_attachment=True, download_name='inventory.db')


@app.route('/admin/upload-db', methods=['GET', 'POST'])
def upload_db():
    if session.get('role') != 'admin':
        abort(403)
    if not app.config['DB_ROUTES_ENABLED']:
        abort(403)
    if request.method == 'POST':
        f = request.files.get('db_file')
        if not f or not f.filename.endswith('.db'):
            flash('กรุณาเลือกไฟล์ .db', 'danger')
            return redirect(request.url)
        import shutil, tempfile
        tmp = tempfile.mktemp(suffix='.db')
        f.save(tmp)
        shutil.move(tmp, config.DATABASE_PATH)
        flash('อัปโหลด database สำเร็จ', 'success')
        return redirect(url_for('dashboard'))
    return render_template('admin_upload_db.html')

# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.route('/')
def dashboard():
    low_stock_count = models.count_low_stock()
    recent_txns = models.get_recent_transactions(10)
    return render_template('dashboard.html',
                           low_stock_count=low_stock_count,
                           recent_txns=recent_txns)


# ── Alerts ────────────────────────────────────────────────────────────────────

@app.route('/alerts')
def alerts_view():
    alerts = models.get_stock_alerts()
    return render_template('alerts.html', alerts=alerts)


# ── Products ──────────────────────────────────────────────────────────────────

@app.route('/products')
def product_list():
    search = request.args.get('q', '').strip()
    low_stock = request.args.get('low_stock') == '1'
    hard_to_sell = request.args.get('hard_to_sell') == '1'
    page = int(request.args.get('page', 1))
    per_page = app.config['ITEMS_PER_PAGE']

    products, total = models.get_products(
        search=search or None,
        low_stock=low_stock,
        hard_to_sell=hard_to_sell,
        page=page,
        per_page=per_page,
    )
    pages = (total + per_page - 1) // per_page
    return render_template('products/list.html',
                           products=products, total=total,
                           page=page, pages=pages,
                           search=search, low_stock=low_stock,
                           hard_to_sell=hard_to_sell)


@app.route('/products/new', methods=['GET', 'POST'])
def product_new():
    if request.method == 'POST':
        f = request.form
        try:
            data = {
                'sku': int(f['sku']),
                'product_name': f['product_name'].strip(),
                'units_per_carton': int(f['units_per_carton']) if f.get('units_per_carton') else None,
                'units_per_box': int(f['units_per_box']) if f.get('units_per_box') else None,
                'unit_type': f.get('unit_type', 'ตัว').strip() or 'ตัว',
                'hard_to_sell': 1 if f.get('hard_to_sell') else 0,
                'cost_price': float(f.get('cost_price') or 0),
                'base_sell_price': float(f.get('base_sell_price') or 0),
                'low_stock_threshold': int(f.get('low_stock_threshold') or config.LOW_STOCK_DEFAULT_THRESHOLD),
                'shopee_stock': int(f.get('shopee_stock') or 0),
                'lazada_stock': int(f.get('lazada_stock') or 0),
            }
        except ValueError as e:
            flash(f'ข้อมูลไม่ถูกต้อง: {e}', 'danger')
            return render_template('products/form.html', product=f, action='new')

        if models.get_product_by_sku(data['sku']):
            flash(f'SKU {data["sku"]} มีในระบบแล้ว', 'danger')
            return render_template('products/form.html', product=f, action='new')

        pid = models.create_product(data)
        locations = request.form.getlist('floor_no')
        models.save_product_locations(pid, locations)
        flash('เพิ่มสินค้าเรียบร้อย', 'success')
        return redirect(url_for('product_detail', product_id=pid))

    return render_template('products/form.html', product={}, action='new', locations=[])


@app.route('/products/<int:product_id>')
def product_detail(product_id):
    product = models.get_product(product_id)
    if not product:
        flash('ไม่พบสินค้า', 'danger')
        return redirect(url_for('product_list'))
    promotions = models.get_promotions(product_id)
    active_promo = models.get_active_promotion(product_id)
    sell_price = models.effective_price(product)
    txn_page = int(request.args.get('txn_page', 1))
    per_page = 20
    txns, txn_total = models.get_transactions(product_id=product_id, page=txn_page, per_page=per_page)
    txn_pages = (txn_total + per_page - 1) // per_page
    locations = models.get_product_locations(product_id)
    bsn_pricing = models.get_product_pricing_summary(product_id)
    return render_template('products/detail.html',
                           product=product,
                           promotions=promotions,
                           active_promo=active_promo,
                           sell_price=sell_price,
                           txns=txns,
                           txn_page=txn_page,
                           txn_pages=txn_pages,
                           txn_total=txn_total,
                           locations=locations,
                           bsn_pricing=bsn_pricing)


@app.route('/products/<int:product_id>/pricing')
def product_pricing(product_id):
    product = models.get_product(product_id)
    if not product:
        abort(404)
    pricing = models.get_product_pricing(product_id)
    return render_template('products/pricing.html', product=product, pricing=pricing)


@app.route('/products/<int:product_id>/edit', methods=['GET', 'POST'])
def product_edit(product_id):
    product = models.get_product(product_id)
    if not product:
        flash('ไม่พบสินค้า', 'danger')
        return redirect(url_for('product_list'))

    if request.method == 'POST':
        f = request.form
        try:
            data = {
                'sku': int(f['sku']),
                'product_name': f['product_name'].strip(),
                'units_per_carton': int(f['units_per_carton']) if f.get('units_per_carton') else None,
                'units_per_box': int(f['units_per_box']) if f.get('units_per_box') else None,
                'unit_type': f.get('unit_type', 'ตัว').strip() or 'ตัว',
                'hard_to_sell': 1 if f.get('hard_to_sell') else 0,
                'cost_price': float(f.get('cost_price') or 0),
                'base_sell_price': float(f.get('base_sell_price') or 0),
                'low_stock_threshold': int(f.get('low_stock_threshold') or config.LOW_STOCK_DEFAULT_THRESHOLD),
                'shopee_stock': int(f.get('shopee_stock') or 0),
                'lazada_stock': int(f.get('lazada_stock') or 0),
            }
        except ValueError as e:
            flash(f'ข้อมูลไม่ถูกต้อง: {e}', 'danger')
            return render_template('products/form.html', product=f, action='edit', product_id=product_id)

        existing = models.get_product_by_sku(data['sku'])
        if existing and existing['id'] != product_id:
            flash(f'SKU {data["sku"]} ถูกใช้งานโดยสินค้าอื่น', 'danger')
            return render_template('products/form.html', product=f, action='edit', product_id=product_id)

        models.update_product(product_id, data)
        locations = request.form.getlist('floor_no')
        models.save_product_locations(product_id, locations)
        flash('แก้ไขสินค้าเรียบร้อย', 'success')
        return redirect(url_for('product_detail', product_id=product_id))

    locations = models.get_product_locations(product_id)
    return render_template('products/form.html', product=product, action='edit', product_id=product_id, locations=locations)


@app.route('/products/<int:product_id>/online-stock', methods=['POST'])
def product_online_stock(product_id):
    platform = request.form.get('platform')
    try:
        qty = float(request.form.get('quantity', 0))
    except ValueError:
        qty = 0
    conn = get_connection()
    if platform == 'shopee':
        conn.execute('UPDATE products SET shopee_stock=? WHERE id=?', (qty, product_id))
    elif platform == 'lazada':
        conn.execute('UPDATE products SET lazada_stock=? WHERE id=?', (qty, product_id))
    conn.commit()
    conn.close()
    flash(f'อัปเดตสต็อก {"Shopee" if platform=="shopee" else "Lazada"} เรียบร้อย', 'success')
    return redirect(url_for('product_detail', product_id=product_id))


@app.route('/products/<int:product_id>/deactivate', methods=['POST'])
def product_deactivate(product_id):
    models.deactivate_product(product_id)
    flash('ปิดใช้งานสินค้าเรียบร้อย', 'success')
    return redirect(url_for('product_list'))


# ── Stock In / Out ────────────────────────────────────────────────────────────

@app.route('/products/<int:product_id>/stock-in', methods=['GET', 'POST'])
def stock_in(product_id):
    product = models.get_product(product_id)
    if not product:
        flash('ไม่พบสินค้า', 'danger')
        return redirect(url_for('product_list'))

    if request.method == 'POST':
        f = request.form
        try:
            qty = int(f['quantity'])
            if qty <= 0:
                raise ValueError('จำนวนต้องมากกว่า 0')
        except ValueError as e:
            flash(str(e), 'danger')
            return render_template('transactions/stock_form.html',
                                   product=product, txn_type='IN')

        unit_mode = f.get('unit_mode', 'unit')
        base_qty = models.to_base_units(qty, unit_mode, product)
        models.add_transaction(product_id, 'IN', base_qty, unit_mode,
                               reference_no=f.get('reference_no'),
                               note=f.get('note'))
        flash(f'รับสินค้าเข้า {base_qty} {product["unit_type"]} เรียบร้อย', 'success')
        return redirect(url_for('product_detail', product_id=product_id))

    return render_template('transactions/stock_form.html', product=product, txn_type='IN')


@app.route('/products/<int:product_id>/stock-out', methods=['GET', 'POST'])
def stock_out(product_id):
    product = models.get_product(product_id)
    if not product:
        flash('ไม่พบสินค้า', 'danger')
        return redirect(url_for('product_list'))

    if request.method == 'POST':
        f = request.form
        try:
            qty = int(f['quantity'])
            if qty <= 0:
                raise ValueError('จำนวนต้องมากกว่า 0')
        except ValueError as e:
            flash(str(e), 'danger')
            return render_template('transactions/stock_form.html',
                                   product=product, txn_type='OUT')

        unit_mode = f.get('unit_mode', 'unit')
        base_qty = models.to_base_units(qty, unit_mode, product)
        current = models.get_current_stock(product_id)
        if base_qty > current:
            flash(f'สต็อกไม่พอ (มี {current} {product["unit_type"]})', 'danger')
            return render_template('transactions/stock_form.html',
                                   product=product, txn_type='OUT')

        models.add_transaction(product_id, 'OUT', -base_qty, unit_mode,
                               reference_no=f.get('reference_no'),
                               note=f.get('note'))
        flash(f'จ่ายสินค้าออก {base_qty} {product["unit_type"]} เรียบร้อย', 'success')
        return redirect(url_for('product_detail', product_id=product_id))

    return render_template('transactions/stock_form.html', product=product, txn_type='OUT')


@app.route('/products/<int:product_id>/adjust', methods=['GET', 'POST'])
def stock_adjust(product_id):
    product = models.get_product(product_id)
    if not product:
        flash('ไม่พบสินค้า', 'danger')
        return redirect(url_for('product_list'))

    if request.method == 'POST':
        f = request.form
        try:
            new_qty = int(f['new_quantity'])
            if new_qty < 0:
                raise ValueError('จำนวนต้องไม่ติดลบ')
        except ValueError as e:
            flash(str(e), 'danger')
            return render_template('transactions/adjust_form.html', product=product)

        note = f.get('note', '').strip()
        if not note:
            flash('กรุณาระบุหมายเหตุสำหรับการปรับยอด', 'danger')
            return render_template('transactions/adjust_form.html', product=product)

        current = models.get_current_stock(product_id)
        diff = new_qty - current
        if diff == 0:
            flash('จำนวนเท่าเดิม ไม่มีการเปลี่ยนแปลง', 'info')
            return redirect(url_for('product_detail', product_id=product_id))

        models.add_transaction(product_id, 'ADJUST', diff, 'unit', note=note)
        flash(f'ปรับยอดสต็อกเป็น {new_qty} {product["unit_type"]} เรียบร้อย', 'success')
        return redirect(url_for('product_detail', product_id=product_id))

    return render_template('transactions/adjust_form.html', product=product)


# ── Transaction History ───────────────────────────────────────────────────────

@app.route('/transactions')
def transaction_history():
    product_id = request.args.get('product_id', type=int)
    txn_type = request.args.get('type', '').strip() or None
    date_from = request.args.get('date_from', '').strip() or None
    date_to = request.args.get('date_to', '').strip() or None
    page = int(request.args.get('page', 1))

    txns, total = models.get_transactions(
        product_id=product_id, txn_type=txn_type,
        date_from=date_from, date_to=date_to,
        page=page, per_page=app.config['ITEMS_PER_PAGE']
    )
    pages = (total + app.config['ITEMS_PER_PAGE'] - 1) // app.config['ITEMS_PER_PAGE']
    return render_template('transactions/history.html',
                           txns=txns, total=total, page=page, pages=pages,
                           product_id=product_id, txn_type=txn_type,
                           date_from=date_from, date_to=date_to)


# ── Promotions ────────────────────────────────────────────────────────────────

@app.route('/products/<int:product_id>/promotions/new', methods=['GET', 'POST'])
def promotion_new(product_id):
    product = models.get_product(product_id)
    if not product:
        flash('ไม่พบสินค้า', 'danger')
        return redirect(url_for('product_list'))

    if request.method == 'POST':
        f = request.form
        try:
            data = {
                'product_id': product_id,
                'promo_name': f['promo_name'].strip(),
                'promo_type': f['promo_type'],
                'discount_value': float(f['discount_value']),
                'date_start': f.get('date_start') or None,
                'date_end': f.get('date_end') or None,
            }
        except ValueError as e:
            flash(f'ข้อมูลไม่ถูกต้อง: {e}', 'danger')
            return render_template('promotions/form.html', product=product)

        if data['promo_type'] == 'percent' and not (0 < data['discount_value'] <= 100):
            flash('ส่วนลด % ต้องอยู่ระหว่าง 1–100', 'danger')
            return render_template('promotions/form.html', product=product)

        models.create_promotion(data)
        flash('เพิ่มโปรโมชันเรียบร้อย', 'success')
        return redirect(url_for('product_detail', product_id=product_id))

    return render_template('promotions/form.html', product=product)


@app.route('/promotions/<int:promo_id>/deactivate', methods=['POST'])
def promotion_deactivate(promo_id):
    from database import get_connection
    conn = get_connection()
    row = conn.execute("SELECT product_id FROM promotions WHERE id = ?", (promo_id,)).fetchone()
    conn.close()
    product_id = row['product_id'] if row else None
    models.deactivate_promotion(promo_id)
    flash('ยกเลิกโปรโมชันเรียบร้อย', 'success')
    return redirect(url_for('product_detail', product_id=product_id) if product_id else url_for('product_list'))


# ── CSV Import ────────────────────────────────────────────────────────────────

def parse_csv_content(text: str) -> list:
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for r in reader:
        try:
            sku = int(str(r.get('SKU', '')).strip())
        except ValueError:
            continue
        name = r.get('Product_Name', '').strip()
        if not name:
            continue

        def parse_int(v):
            v = str(v).strip()
            return int(v) if v else None

        rows.append({
            'sku': sku,
            'product_name': name,
            'units_per_carton': parse_int(r.get('บรรจุ/ลัง', '')),
            'units_per_box': parse_int(r.get('บรรจุ/กล่อง', '')),
            'unit_type': r.get('หน่วย', 'ตัว').strip() or 'ตัว',
            'hard_to_sell': 1 if str(r.get('ขายยาก', '')).strip().upper() == 'TRUE' else 0,
        })
    return rows


@app.route('/import', methods=['GET', 'POST'])
def csv_import():
    if request.method == 'POST':
        if 'csv_file' not in request.files:
            flash('กรุณาเลือกไฟล์', 'danger')
            return redirect(url_for('csv_import'))

        f = request.files['csv_file']
        if not f.filename.endswith('.csv'):
            flash('รองรับเฉพาะไฟล์ .csv', 'danger')
            return redirect(url_for('csv_import'))

        content = f.read().decode('utf-8-sig')
        rows = parse_csv_content(content)
        if not rows:
            flash('ไม่พบข้อมูลในไฟล์', 'warning')
            return redirect(url_for('csv_import'))

        # Store in session for confirmation step
        session['import_rows'] = rows
        session['import_filename'] = f.filename
        return render_template('import.html', preview=rows[:20],
                               total=len(rows), step='confirm',
                               filename=f.filename)

    return render_template('import.html', step='upload')


@app.route('/import/confirm', methods=['POST'])
def csv_import_confirm():
    rows = session.pop('import_rows', None)
    filename = session.pop('import_filename', 'unknown.csv')
    if not rows:
        flash('หมดเวลา กรุณาอัปโหลดใหม่', 'warning')
        return redirect(url_for('csv_import'))

    overwrite = request.form.get('overwrite') == '1'
    imported, skipped = models.bulk_import_products(rows, overwrite=overwrite)

    from database import get_connection
    conn = get_connection()
    conn.execute("""
        INSERT INTO import_log (filename, rows_imported, rows_skipped, notes)
        VALUES (?, ?, ?, ?)
    """, (filename, imported, skipped, f'overwrite={overwrite}'))
    conn.commit()
    conn.close()

    flash(f'นำเข้าสำเร็จ {imported} รายการ, ข้าม {skipped} รายการ', 'success')
    return redirect(url_for('product_list'))


# ── Weekly Import (ขาย / ซื้อ) ───────────────────────────────────────────────

ALLOWED_WEEKLY = {'cp874'}

@app.route('/import-weekly', methods=['GET', 'POST'])
def import_weekly():
    if request.method == 'POST':
        f = request.files.get('weekly_file')
        if not f or not f.filename.endswith('.csv'):
            flash('กรุณาเลือกไฟล์ .csv', 'danger')
            return redirect(url_for('import_weekly'))

        # Save temp file
        tmp_path = os.path.join(config.UPLOAD_FOLDER, f.filename)
        f.save(tmp_path)

        file_type = detect_file_type(tmp_path)
        if file_type == 'unknown':
            flash('ไม่สามารถระบุประเภทไฟล์ (ขาย/ซื้อ)', 'danger')
            return redirect(url_for('import_weekly'))

        entries = parse_sales(tmp_path) if file_type == 'sales' else parse_purchases(tmp_path)
        if not entries:
            flash('ไม่พบข้อมูลในไฟล์', 'warning')
            return redirect(url_for('import_weekly'))

        stats = models.import_weekly(entries, file_type, f.filename)

        flash(
            f'นำเข้าสำเร็จ {stats["imported"]} รายการ  |  '
            f'ข้ามซ้ำ {stats["skipped_dup"]} รายการ  |  '
            f'สินค้าไม่มีในระบบ {stats["new_unmapped"]} รายการ',
            'success' if stats['new_unmapped'] == 0 else 'warning'
        )
        if models.get_pending_unit_conversions():
            return redirect(url_for('unit_conversions'))
        if stats['new_unmapped'] > 0:
            return redirect(url_for('mapping'))
        return redirect(url_for('sales_view') if file_type == 'sales' else url_for('purchases_view'))

    recent_imports = models.get_recent_imports(limit=5)
    return render_template('import_weekly.html', recent_imports=recent_imports)


# ── Unit Conversions ──────────────────────────────────────────────────────────

@app.route('/unit-conversions')
def unit_conversions():
    search = request.args.get('q', '').strip()
    page = int(request.args.get('page', 1))
    per_page = app.config['ITEMS_PER_PAGE']
    pending = models.get_pending_unit_conversions()
    existing, total = models.get_all_unit_conversions(
        search=search or None, page=page, per_page=per_page
    )
    pages = (total + per_page - 1) // per_page
    return render_template('unit_conversions.html',
                           pending=pending, existing=existing,
                           search=search, page=page, pages=pages, total=total)


@app.route('/unit-conversions/save', methods=['POST'])
def unit_conversions_save():
    items = []
    for key, val in request.form.items():
        # key format: "ratio_<product_id>_<bsn_unit>"
        if key.startswith('ratio_'):
            parts = key[6:].split('_', 1)
            if len(parts) == 2:
                try:
                    ratio = float(val)
                    if ratio > 0:
                        items.append({'product_id': int(parts[0]), 'bsn_unit': parts[1], 'ratio': ratio})
                except (ValueError, IndexError):
                    pass
    if items:
        models.save_unit_conversions(items)
        flash(f'บันทึกการแปลงหน่วย {len(items)} รายการเรียบร้อย', 'success')
    return redirect(url_for('unit_conversions'))


@app.route('/unit-conversions/edit', methods=['POST'])
def unit_conversions_edit():
    product_id = request.form.get('product_id', type=int)
    bsn_unit   = request.form.get('bsn_unit', '').strip()
    new_ratio  = request.form.get('ratio', type=float)
    if product_id and bsn_unit and new_ratio and new_ratio > 0:
        models.update_unit_conversion_ratio(product_id, bsn_unit, new_ratio)
        flash(f'อัปเดต ratio สำหรับ {bsn_unit} เรียบร้อย (re-sync แล้ว)', 'success')
    return redirect(url_for('unit_conversions'))


# ── Review uncertain no-ref transactions ──────────────────────────────────────

@app.route('/review-transactions')
def review_transactions():
    rows = models.get_uncertain_no_ref_transactions()
    return render_template('review_transactions.html', rows=rows)


@app.route('/review-transactions/delete', methods=['POST'])
def review_transactions_delete():
    ids_str = request.form.getlist('delete_ids')
    ids = []
    for v in ids_str:
        try:
            ids.append(int(v))
        except ValueError:
            pass
    if ids:
        models.delete_transactions_by_ids(ids)
        flash(f'ลบ {len(ids)} รายการเรียบร้อย', 'success')
    else:
        flash('ไม่ได้เลือกรายการที่จะลบ', 'info')
    return redirect(url_for('review_transactions'))


# ── Product Code Mapping ──────────────────────────────────────────────────────

@app.route('/mapping')
def mapping():
    pending = models.get_pending_mappings()
    conn = get_connection()
    all_products = conn.execute(
        "SELECT id, sku, product_name FROM products WHERE is_active=1 ORDER BY sku"
    ).fetchall()
    next_sku = conn.execute("SELECT COALESCE(MAX(sku),0)+1 FROM products").fetchone()[0]
    conn.close()
    return render_template('mapping.html', pending=pending, all_products=all_products, next_sku=next_sku)


@app.route('/mapping/save', methods=['POST'])
def mapping_save():
    data = request.get_json()
    for item in data.get('mappings', []):
        bsn_code = item.get('bsn_code')
        action   = item.get('action')       # 'map', 'new', 'ignore'
        if action == 'map':
            models.upsert_mapping(bsn_code, item['bsn_name'],
                                  product_id=int(item['product_id']))
        elif action == 'new':
            # ใช้ SKU ที่ user กำหนดจาก UI หรือ auto MAX+1
            try:
                sku_to_use = int(item.get('new_sku') or 0)
            except (ValueError, TypeError):
                sku_to_use = 0
            if not sku_to_use:
                sku_to_use = get_connection().execute(
                    "SELECT COALESCE(MAX(sku),0)+1 FROM products"
                ).fetchone()[0]
            pid = models.create_product({
                'sku': sku_to_use,
                'product_name': item.get('new_name') or item['bsn_name'],
                'units_per_carton': None,
                'units_per_box': None,
                'unit_type': 'ตัว',
                'hard_to_sell': 0,
                'cost_price': 0.0,
                'base_sell_price': 0.0,
                'low_stock_threshold': config.LOW_STOCK_DEFAULT_THRESHOLD,
                'shopee_stock': 0,
                'lazada_stock': 0,
            })
            models.upsert_mapping(bsn_code, item['bsn_name'], product_id=pid)
        elif action == 'ignore':
            models.upsert_mapping(bsn_code, item['bsn_name'], is_ignored=1)

    # Backfill product_id on existing unlinked rows
    conn = get_connection()
    models.resolve_pending_mappings(conn)
    conn.close()

    pending_left = len(models.get_pending_mappings())
    return jsonify({'ok': True, 'pending_left': pending_left})


# ── Sales View ────────────────────────────────────────────────────────────────

@app.route('/trade-dashboard')
def trade_dashboard():
    date_from = request.args.get('date_from') or None
    date_to   = request.args.get('date_to')   or None
    stats = models.get_trade_dashboard(date_from, date_to)
    return render_template('trade_dashboard.html', stats=stats)


@app.route('/products/<int:product_id>/trade')
def product_trade_summary(product_id):
    date_from = request.args.get('date_from') or None
    date_to   = request.args.get('date_to')   or None
    data = models.get_product_trade_summary(product_id, date_from, date_to)
    if not data['product']:
        flash('ไม่พบสินค้า', 'danger')
        return redirect(url_for('trade_dashboard'))
    return render_template('products/trade_summary.html', data=data)


@app.route('/customers')
def customer_list():
    search  = request.args.get('q', '').strip()
    region  = request.args.get('region', '').strip()
    page    = int(request.args.get('page', 1))
    per_page = app.config['ITEMS_PER_PAGE']
    customers, total = models.get_customers(
        search=search or None,
        region=region or None,
        page=page, per_page=per_page
    )
    pages   = (total + per_page - 1) // per_page
    regions = models.get_regions()
    return render_template('customers.html',
                           customers=customers, total=total,
                           page=page, pages=pages,
                           search=search, region=region, regions=regions)


@app.route('/customer/<path:customer_name>')
def customer_summary(customer_name):
    date_from = request.args.get('date_from') or None
    date_to   = request.args.get('date_to')   or None
    data = models.get_customer_summary(customer_name, date_from, date_to)
    unpaid_bills = models.get_customer_unpaid_bills(customer_name)
    unpaid_total = sum(b['total_net'] or 0 for b in unpaid_bills)
    return render_template('customer_summary.html', data=data,
                           unpaid_bills=unpaid_bills, unpaid_total=unpaid_total)


@app.route('/sales')
def sales_view():
    today = date.today()
    default_from = today.replace(day=1).isoformat()
    default_to   = today.isoformat()
    pid_raw   = request.args.get('product_id', '').strip()
    product_id = int(pid_raw) if pid_raw.isdigit() else None
    if product_id:
        default_from = '2020-01-01'
        default_to   = today.isoformat()
    date_from = request.args.get('date_from', '').strip() or default_from
    date_to   = request.args.get('date_to',   '').strip() or default_to
    vat_raw   = request.args.get('vat_type',  '').strip()
    vat_type  = int(vat_raw) if vat_raw.isdigit() else None
    page      = int(request.args.get('page', 1))
    per_page  = app.config['ITEMS_PER_PAGE']

    filter_product = models.get_product(product_id) if product_id else None

    rows, total = models.get_sales(
        product_id=product_id, date_from=date_from, date_to=date_to,
        vat_type=vat_type, page=page, per_page=per_page
    )
    summary = models.get_sales_summary(date_from=date_from, date_to=date_to)
    pages   = (total + per_page - 1) // per_page

    # Build summary dict keyed by vat_type (convert Row → plain dict)
    vat_summary = {r['vat_type']: dict(r) for r in summary}

    return render_template('sales.html',
                           rows=rows, total=total, pages=pages, page=page,
                           date_from=date_from, date_to=date_to,
                           vat_type=vat_type, vat_summary=vat_summary,
                           product_id=product_id, filter_product=filter_product,
                           pending_map=len(models.get_pending_mappings()))


# ── Sales Doc Detail ─────────────────────────────────────────────────────────

@app.route('/sales/doc/<doc_base>')
def sales_doc(doc_base):
    rows = models.get_sales_by_doc(doc_base)
    if not rows:
        return "ไม่พบเอกสาร", 404
    total_net = sum(r['net'] or 0 for r in rows)
    return render_template('sales_doc.html', rows=rows, doc_base=doc_base,
                           total_net=total_net,
                           pending_map=len(models.get_pending_mappings()))


# ── Purchases View ────────────────────────────────────────────────────────────

@app.route('/purchases')
def purchases_view():
    today = date.today()
    default_from = today.replace(day=1).isoformat()
    default_to   = today.isoformat()
    date_from = request.args.get('date_from', '').strip() or default_from
    date_to   = request.args.get('date_to',   '').strip() or default_to
    page      = int(request.args.get('page', 1))
    per_page  = app.config['ITEMS_PER_PAGE']

    rows, total = models.get_purchases(
        date_from=date_from, date_to=date_to,
        page=page, per_page=per_page
    )
    pages = (total + per_page - 1) // per_page

    return render_template('purchases.html',
                           rows=rows, total=total, pages=pages, page=page,
                           date_from=date_from, date_to=date_to,
                           pending_map=len(models.get_pending_mappings()))


# ── Purchases Doc Detail ─────────────────────────────────────────────────────

@app.route('/purchases/doc/<doc_base>')
def purchases_doc(doc_base):
    rows = models.get_purchases_by_doc(doc_base)
    if not rows:
        return "ไม่พบเอกสาร", 404
    total_net = sum(r['net'] or 0 for r in rows)
    return render_template('purchases_doc.html', rows=rows, doc_base=doc_base,
                           total_net=total_net,
                           pending_map=len(models.get_pending_mappings()))


# ── Payment Status ────────────────────────────────────────────────────────────

@app.route('/payment-status')
def payment_status():
    status   = request.args.get('status', 'all')   # all | paid | unpaid
    search   = request.args.get('q', '').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to   = request.args.get('date_to',   '').strip()
    page      = int(request.args.get('page', 1))
    per_page  = app.config['ITEMS_PER_PAGE']

    rows, total = models.get_payment_status(
        status=status, search=search,
        date_from=date_from, date_to=date_to,
        page=page, per_page=per_page
    )
    summary = models.get_payment_summary()
    total_pages = max(1, (total + per_page - 1) // per_page)
    return render_template(
        'payment_status.html',
        rows=rows, total=total,
        summary=summary,
        status=status, search=search,
        date_from=date_from, date_to=date_to,
        page=page, total_pages=total_pages,
    )


@app.route('/payment-status/customers')
def payment_customers():
    search       = request.args.get('q', '').strip()
    match_str    = request.args.get('match', '').strip()
    rows         = models.get_customer_debt_summary(search=search)
    total_outstanding = sum(r['outstanding_amount'] or 0 for r in rows)

    candidates = []
    match_amount = None
    if match_str:
        try:
            match_amount = float(match_str.replace(',', ''))
            candidates = models.find_payment_candidates(match_amount)
        except ValueError:
            pass

    return render_template(
        'payment_customers.html',
        rows=rows,
        search=search,
        total_outstanding=total_outstanding,
        match_str=match_str,
        match_amount=match_amount,
        candidates=candidates,
    )


@app.route('/payment-status/customer/<path:customer_name>')
def payment_customer_detail(customer_name):
    bills = models.get_customer_unpaid_bills(customer_name)
    total = sum(b['total_net'] or 0 for b in bills)
    return render_template(
        'payment_customer_detail.html',
        customer_name=customer_name,
        bills=bills,
        total=total,
    )


@app.route('/import-payments', methods=['POST'])
def import_payments():
    if session.get('role') not in ('admin', 'manager'):
        flash('ต้องเป็น Admin หรือ Manager', 'danger')
        return redirect(url_for('payment_status'))
    f = request.files.get('payment_file')
    if not f or not f.filename.endswith('.csv'):
        flash('กรุณาเลือกไฟล์ .csv', 'danger')
        return redirect(url_for('payment_status'))
    tmp_path = os.path.join(config.UPLOAD_FOLDER, f.filename)
    f.save(tmp_path)
    result = models.import_payments(tmp_path)
    flash(
        f'นำเข้าสำเร็จ {result["imported"]} ใบเสร็จ  |  ข้ามซ้ำ {result["skipped"]} รายการ',
        'success'
    )
    return redirect(url_for('payment_status'))


# ── Template filters ──────────────────────────────────────────────────────────

@app.template_filter('fmt_price')
def fmt_price(v):
    if v is None:
        return '-'
    return f'{v:,.2f}'


@app.template_filter('fmt_qty')
def fmt_qty(v):
    if v is None:
        return '-'
    return f'{v:,}'


# ── E-commerce ────────────────────────────────────────────────────────────────

@app.route('/ecommerce')
def ecommerce():
    tab      = request.args.get('tab', 'shopee')
    search   = request.args.get('q', '').strip()
    page     = int(request.args.get('page', 1))
    per_page = app.config['ITEMS_PER_PAGE']

    platform = tab if tab in ('shopee', 'lazada') else 'shopee'
    rows, total = models.get_platform_skus(platform, search or None, page, per_page)
    pages   = max(1, (total + per_page - 1) // per_page)
    summary = models.get_platform_summary()

    return render_template('ecommerce.html',
                           tab=tab, rows=rows, total=total,
                           search=search, page=page, pages=pages,
                           summary=summary)


@app.route('/ecommerce/import', methods=['POST'])
def ecommerce_import():
    platform = request.form.get('platform', '').lower()
    if platform not in ('shopee', 'lazada'):
        flash('ระบุ platform ไม่ถูกต้อง', 'danger')
        return redirect(url_for('ecommerce'))

    f = request.files.get('platform_file')
    if not f or not f.filename.endswith('.xlsx'):
        flash('กรุณาเลือกไฟล์ .xlsx', 'danger')
        return redirect(url_for('ecommerce', tab=platform))

    try:
        file_bytes = io.BytesIO(f.read())
        if platform == 'shopee':
            records = parse_shopee(file_bytes)
        else:
            records = parse_lazada(file_bytes)

        if not records:
            flash('ไม่พบข้อมูลในไฟล์', 'warning')
            return redirect(url_for('ecommerce', tab=platform))

        count = models.import_platform_skus(platform, records)
        flash(f'นำเข้าข้อมูล {platform.capitalize()} สำเร็จ {count} รายการ', 'success')
    except Exception as e:
        flash(f'เกิดข้อผิดพลาด: {e}', 'danger')

    return redirect(url_for('ecommerce', tab=platform))


@app.route('/ecommerce/export/<platform>')
def ecommerce_export(platform):
    if platform not in ('shopee', 'lazada'):
        abort(404)

    rows = models.get_platform_skus_all(platform)
    if not rows:
        flash(f'ยังไม่มีข้อมูล {platform.capitalize()} ในระบบ', 'warning')
        return redirect(url_for('ecommerce', tab=platform))

    from flask import send_file
    import datetime
    date_str = datetime.date.today().strftime('%Y%m%d')

    if platform == 'shopee':
        buf = export_shopee([dict(r) for r in rows])
        fname = f'Shopee_mass_update_{date_str}.xlsx'
        mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    else:
        buf = export_lazada([dict(r) for r in rows])
        fname = f'Lazada_pricestock_{date_str}.xlsx'
        mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

    return send_file(buf, mimetype=mimetype,
                     as_attachment=True, download_name=fname)


@app.route('/ecommerce/mapping/export')
def ecommerce_mapping_export():
    rows = models.get_platform_mapping_data()
    if not rows:
        flash('ยังไม่มีข้อมูล platform ในระบบ', 'warning')
        return redirect(url_for('ecommerce'))

    from flask import send_file
    import datetime

    # Compute AI suggestions (~6s)
    suggestions = models.suggest_platform_mapping()

    buf = export_mapping(rows, suggestions=suggestions)
    fname = f'ecommerce_mapping_{datetime.date.today().strftime("%Y%m%d")}.xlsx'

    # บันทึกลง data/exports/ ด้วยทุกครั้ง
    exports_dir = os.path.join(os.path.dirname(config.BASE_DIR), 'data', 'exports')
    os.makedirs(exports_dir, exist_ok=True)
    save_path = os.path.join(exports_dir, fname)
    with open(save_path, 'wb') as f:
        f.write(buf.getvalue())
    buf.seek(0)

    return send_file(buf,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     as_attachment=True, download_name=fname)


@app.route('/ecommerce/mapping/import', methods=['POST'])
def ecommerce_mapping_import():
    f = request.files.get('mapping_file')
    if not f or not f.filename.endswith('.xlsx'):
        flash('กรุณาเลือกไฟล์ .xlsx', 'danger')
        return redirect(url_for('ecommerce'))

    try:
        file_bytes = io.BytesIO(f.read())
        records = parse_mapping(file_bytes)
        updated, not_found = models.apply_platform_mapping(records)
        flash(f'Mapping สำเร็จ {updated} รายการ'
              + (f' | ไม่พบ SKU ในระบบ {not_found} รายการ' if not_found else ''),
              'success' if not_found == 0 else 'warning')
    except Exception as e:
        flash(f'เกิดข้อผิดพลาด: {e}', 'danger')

    return redirect(url_for('ecommerce'))


@app.route('/ecommerce/sku/<int:sku_id>/edit', methods=['POST'])
def ecommerce_sku_edit(sku_id):
    platform = request.form.get('platform', 'shopee')
    try:
        models.update_platform_sku(
            sku_id,
            price       = float(request.form['price']) if request.form.get('price') else None,
            special_price = float(request.form['special_price']) if request.form.get('special_price') else None,
            stock       = int(request.form['stock']) if request.form.get('stock') else None,
            qty_per_sale = float(request.form.get('qty_per_sale') or 1),
        )
        flash('อัปเดตเรียบร้อย', 'success')
    except Exception as e:
        flash(f'เกิดข้อผิดพลาด: {e}', 'danger')
    return redirect(url_for('ecommerce', tab=platform,
                            page=request.form.get('page', 1),
                            q=request.form.get('q', '')))



if __name__ == '__main__':
    app.run(debug=True, port=5001, use_reloader=False)
