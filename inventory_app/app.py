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
from blueprints.products import bp_products

app = Flask(__name__)
app.config['SECRET_KEY'] = config.SECRET_KEY
app.config['JSON_AS_ASCII'] = False
app.config['UPLOAD_FOLDER'] = config.UPLOAD_FOLDER
app.config['ITEMS_PER_PAGE'] = config.ITEMS_PER_PAGE
app.config['DB_ROUTES_ENABLED'] = False

os.makedirs(config.UPLOAD_FOLDER, exist_ok=True)

app.register_blueprint(bp_products)

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
    'import_weekly', 'mapping_save', 'unit_conversions_save', 'unit_conversions_edit',
    'products.product_location_save',
    'admin_exit_simulate',
    'conversion_new', 'conversion_edit',
])
_MANAGER_POST_OK = _STAFF_POST_OK | frozenset([
    'import_payments', 'products.product_online_stock',
    'conversion_run', 'conversion_new', 'conversion_edit', 'conversion_delete',
])
# admin can POST anything


@app.context_processor
def inject_auth():
    role = session.get('role', '')
    real_role = session.get('_real_role')
    return {
        'is_admin':      role == 'admin',
        'is_manager':    role in ('admin', 'manager'),
        'current_user':  session.get('display_name', ''),
        'current_role':  role,
        'simulating_as': role if real_role else None,
        'real_role':     real_role,
        'alert_count':   models.count_stock_alerts(),
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


@app.route('/users/<int:uid>/delete', methods=['POST'])
def user_delete(uid):
    if session.get('role') != 'admin':
        abort(403)
    conn = get_connection()
    target = conn.execute("SELECT id, role, username FROM users WHERE id=?", (uid,)).fetchone()
    if not target:
        flash('ไม่พบผู้ใช้', 'danger')
    elif target['role'] == 'admin':
        flash('ไม่สามารถลบบัญชี Admin ได้', 'danger')
    elif target['id'] == session.get('user_id'):
        flash('ไม่สามารถลบบัญชีของตัวเองได้', 'danger')
    else:
        conn.execute("DELETE FROM users WHERE id=?", (uid,))
        conn.commit()
        flash(f'ลบผู้ใช้ {target["username"]} สำเร็จ', 'success')
    conn.close()
    return redirect(url_for('user_list'))


@app.route('/admin/simulate-role', methods=['POST'])
def admin_simulate_role():
    if session.get('role') != 'admin' and not session.get('_real_role'):
        abort(403)
    target_role = request.form.get('role', '')
    if target_role not in ('manager', 'staff'):
        flash('Role ไม่ถูกต้อง', 'danger')
        return redirect(url_for('user_list'))
    session['_real_role'] = session.get('_real_role') or 'admin'
    session['role'] = target_role
    flash(f'กำลังจำลองเป็น {target_role} — คลิก "ออกจากโหมดจำลอง" เพื่อกลับ', 'info')
    return redirect(url_for('dashboard'))


@app.route('/admin/exit-simulate', methods=['POST'])
def admin_exit_simulate():
    real_role = session.pop('_real_role', None)
    if real_role:
        session['role'] = real_role
        flash('ออกจากโหมดจำลองแล้ว กลับเป็น Admin', 'success')
    return redirect(url_for('dashboard'))


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


# ── Products — moved to blueprints/products.py ──────────────────────────────
# Routes: /products, /products/new, /products/<id>, /products/<id>/cost-history,
#         /products/<id>/pricing, /products/<id>/edit, /products/<id>/location,
#         /products/<id>/online-stock, /products/<id>/deactivate,
#         /products/<id>/trade, /products/<id>/promotions/new,
#         /promotions/<id>/deactivate, /import, /import/confirm
# (registered via bp_products above)


# ── Stock In / Out ────────────────────────────────────────────────────────────

@app.route('/products/<int:product_id>/stock-in', methods=['GET', 'POST'])
def stock_in(product_id):
    product = models.get_product(product_id)
    if not product:
        flash('ไม่พบสินค้า', 'danger')
        return redirect(url_for('products.product_list'))

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
        return redirect(url_for('products.product_detail', product_id=product_id))

    return render_template('transactions/stock_form.html', product=product, txn_type='IN')


@app.route('/products/<int:product_id>/stock-out', methods=['GET', 'POST'])
def stock_out(product_id):
    product = models.get_product(product_id)
    if not product:
        flash('ไม่พบสินค้า', 'danger')
        return redirect(url_for('products.product_list'))

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
        return redirect(url_for('products.product_detail', product_id=product_id))

    return render_template('transactions/stock_form.html', product=product, txn_type='OUT')


@app.route('/products/<int:product_id>/adjust', methods=['GET', 'POST'])
def stock_adjust(product_id):
    product = models.get_product(product_id)
    if not product:
        flash('ไม่พบสินค้า', 'danger')
        return redirect(url_for('products.product_list'))

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
            return redirect(url_for('products.product_detail', product_id=product_id))

        models.add_transaction(product_id, 'ADJUST', diff, 'unit', note=note)
        flash(f'ปรับยอดสต็อกเป็น {new_qty} {product["unit_type"]} เรียบร้อย', 'success')
        return redirect(url_for('products.product_detail', product_id=product_id))

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


# ── Promotions and CSV Import — moved to blueprints/products.py ─────────────


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

        parts = [f'นำเข้าสำเร็จ {stats["imported"]} รายการ']
        if stats['overwritten']:
            parts.append(f'อัพเดทข้อมูลเก่า {stats["overwritten"]} รายการ')
        if stats['skipped_dup']:
            parts.append(f'ข้าม {stats["skipped_dup"]} รายการ')
        if stats['new_unmapped']:
            parts.append(f'สินค้าไม่มีในระบบ {stats["new_unmapped"]} รายการ')
        flash('  |  '.join(parts), 'success' if stats['new_unmapped'] == 0 else 'warning')
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
    pending = models.get_pending_unit_conversions(search=search or None)
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


@app.route('/suppliers')
def supplier_list():
    search   = request.args.get('q', '').strip()
    page     = int(request.args.get('page', 1))
    per_page = app.config['ITEMS_PER_PAGE']
    suppliers, total = models.get_suppliers(
        search=search or None, page=page, per_page=per_page
    )
    pages = (total + per_page - 1) // per_page
    return render_template('suppliers.html',
                           suppliers=suppliers, total=total,
                           page=page, pages=pages, search=search)


@app.route('/supplier/<path:supplier_name>')
def supplier_summary(supplier_name):
    date_from = request.args.get('date_from') or None
    date_to   = request.args.get('date_to')   or None
    data = models.get_supplier_summary(supplier_name, date_from, date_to)
    return render_template('supplier_summary.html', data=data)


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



# ── Product Conversions (สูตรแปลงสินค้า) ─────────────────────────────────────

@app.route('/conversions')
def conversion_list():
    formulas = models.get_conversion_formulas()
    return render_template('conversions/list.html', formulas=formulas)


def _get_active_products():
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, sku, product_name, unit_type FROM products WHERE is_active=1 ORDER BY product_name"
    ).fetchall()
    conn.close()
    return rows


@app.route('/conversions/new', methods=['GET', 'POST'])
def conversion_new():
    if not session.get('role'):
        abort(403)
    products = _get_active_products()
    if request.method == 'POST':
        name              = request.form.get('name', '').strip()
        output_product_id = request.form.get('output_product_id', '').strip()
        output_qty        = request.form.get('output_qty', '1').strip()
        note              = request.form.get('note', '').strip()
        input_pids        = request.form.getlist('input_product_id[]')
        input_qtys        = request.form.getlist('input_quantity[]')

        inputs = [{'product_id': int(p), 'quantity': int(q)}
                  for p, q in zip(input_pids, input_qtys) if p and q]
        if not name or not output_product_id or not inputs:
            flash('กรุณากรอกชื่อสูตร สินค้าที่ได้ และวัตถุดิบอย่างน้อย 1 รายการ', 'danger')
            return render_template('conversions/form.html', products=products, formula=None, inputs=[])

        models.create_conversion_formula(
            name, int(output_product_id), int(output_qty), inputs, note
        )
        flash(f'สร้างสูตร "{name}" สำเร็จ', 'success')
        return redirect(url_for('conversion_list'))

    return render_template('conversions/form.html', products=products, formula=None, inputs=[])


@app.route('/conversions/<int:formula_id>/edit', methods=['GET', 'POST'])
def conversion_edit(formula_id):
    if not session.get('role'):
        abort(403)
    formula, inputs = models.get_conversion_formula(formula_id)
    if not formula:
        abort(404)
    products = _get_active_products()
    if request.method == 'POST':
        name              = request.form.get('name', '').strip()
        output_product_id = request.form.get('output_product_id', '').strip()
        output_qty        = request.form.get('output_qty', '1').strip()
        note              = request.form.get('note', '').strip()
        input_pids        = request.form.getlist('input_product_id[]')
        input_qtys        = request.form.getlist('input_quantity[]')

        new_inputs = [{'product_id': int(p), 'quantity': int(q)}
                      for p, q in zip(input_pids, input_qtys) if p and q]
        if not name or not output_product_id or not new_inputs:
            flash('กรุณากรอกข้อมูลให้ครบ', 'danger')
            return render_template('conversions/form.html', products=products, formula=formula, inputs=inputs)

        models.update_conversion_formula(
            formula_id, name, int(output_product_id), int(output_qty), new_inputs, note
        )
        flash(f'อัปเดตสูตร "{name}" สำเร็จ', 'success')
        return redirect(url_for('conversion_list'))

    return render_template('conversions/form.html', products=products, formula=formula, inputs=inputs)


@app.route('/conversions/<int:formula_id>/run', methods=['GET', 'POST'])
def conversion_run(formula_id):
    formula, inputs = models.get_conversion_formula(formula_id)
    if not formula or not formula['is_active']:
        abort(404)
    if request.method == 'POST':
        if session.get('role') not in ('admin', 'manager'):
            flash('ต้องใช้บัญชี Admin หรือ Manager เท่านั้น', 'danger')
            return redirect(url_for('conversion_list'))
        try:
            multiplier   = max(1, int(request.form.get('multiplier', 1)))
        except (ValueError, TypeError):
            multiplier   = 1
        reference_no = request.form.get('reference_no', '').strip()
        extra_note   = request.form.get('note', '').strip()

        success, message, _ = models.run_conversion(formula_id, multiplier, reference_no, extra_note)
        flash(message, 'success' if success else 'danger')
        if success:
            return redirect(url_for('conversion_list'))

    return render_template('conversions/run.html', formula=formula, inputs=inputs)


@app.route('/conversions/<int:formula_id>/delete', methods=['POST'])
def conversion_delete(formula_id):
    if session.get('role') not in ('admin', 'manager'):
        abort(403)
    models.delete_conversion_formula(formula_id)
    flash('ลบสูตรเรียบร้อยแล้ว', 'success')
    return redirect(url_for('conversion_list'))


@app.route('/conversions/<int:formula_id>/deactivate', methods=['POST'])
def conversion_deactivate(formula_id):
    if session.get('role') != 'admin':
        abort(403)
    conn = get_connection()
    conn.execute("UPDATE conversion_formulas SET is_active=0 WHERE id=?", (formula_id,))
    conn.commit()
    conn.close()
    flash('ปิดใช้งานสูตรแล้ว', 'success')
    return redirect(url_for('conversion_list'))


# ── Customer Map ──────────────────────────────────────────────────────────────

def _parse_bsn_customers():
    import re
    csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            '..', 'data', 'source', 'bsn_customer_info.csv')
    with open(csv_path, encoding='cp874', errors='replace') as f:
        content = f.read()
    lines = [l.strip('"').replace('\xa0', ' ') for l in content.split('\n')]

    customers = []
    current_type = ''
    i = 0
    while i < len(lines):
        line = lines[i]
        type_match = re.match(r'\s+ประเภท\s*:\s*(.+)', line)
        if type_match:
            current_type = type_match.group(1).strip()
            i += 1; continue

        cust_match = re.match(r'  (\d{2}[ก-ฮA-Za-z]\d{2,3})\s+(.+?)\s{3,}(\S+)\s+(\S+)\s+\d+', line)
        if cust_match:
            code = cust_match.group(1)
            name = cust_match.group(2).strip()
            salesperson = cust_match.group(3)
            zone = cust_match.group(4)
            customer = {
                'code': code, 'name': name, 'salesperson': salesperson,
                'zone': zone, 'customer_type': current_type,
                'address': '', 'phone': '', 'tax_id': '',
                'credit_days': 0, 'contact': '',
            }
            addr_parts = []
            j = i + 1
            while j < len(lines) and j < i + 10:
                nl = lines[j]
                if re.match(r'  \d{2}[ก-ฮA-Za-z]\d{2,3}\s', nl): break
                if re.match(r'\(BSN\)', nl.strip()): j += 5; break
                am = re.match(r'\s+ที่อยู่\s*:\s*(.*?)\s+ผู้ติดต่อ\s*:\s*(.*)', nl)
                if am:
                    a = am.group(1).strip()
                    if a: addr_parts.append(a)
                    customer['contact'] = am.group(2).strip()
                elif re.match(r'\s{17,}[^\s]', nl):
                    a = re.sub(r'\s+เลขที่.*', '', re.sub(r'\s+เครดิต.*', '', nl)).strip()
                    if a and not a.startswith('(BSN)'): addr_parts.append(a)
                cm = re.search(r'เครดิต\s*:\s*(\d+)', nl)
                if cm: customer['credit_days'] = int(cm.group(1))
                pm = re.match(r'\s+โทร\.\s*:\s*(.*?)\s+เงื่อนไข', nl)
                if pm: customer['phone'] = pm.group(1).strip()
                tm = re.match(r'\s+Tax ID\s*:\s*(\d+)', nl)
                if tm: customer['tax_id'] = tm.group(1)
                j += 1
            customer['address'] = ' '.join(addr_parts)
            customers.append(customer)
            i = j; continue
        i += 1
    return customers


@app.route('/customers/map')
def customer_map():
    zone   = request.args.get('zone', '').strip()
    ctype  = request.args.get('type', '').strip()
    total, geocoded = models.get_geocode_progress()
    zones  = models.get_customer_zones()
    ctypes = models.get_customer_types()
    customers_json = models.get_customers_for_map(
        zone=zone or None, customer_type=ctype or None
    )
    return render_template('customer_map.html',
                           customers_json=customers_json,
                           zones=zones, ctypes=ctypes,
                           sel_zone=zone, sel_type=ctype,
                           total=total, geocoded=geocoded)


@app.route('/customers/import-bsn', methods=['POST'])
def customer_import_bsn():
    if session.get('role') != 'admin':
        abort(403)
    customers = _parse_bsn_customers()
    inserted, updated = models.import_customers_from_bsn(customers)
    flash(f'นำเข้าสำเร็จ: เพิ่มใหม่ {inserted} รายการ, อัปเดต {updated} รายการ', 'success')
    return redirect(url_for('customer_map'))


@app.route('/customers/geocode/<code>', methods=['POST'])
def customer_geocode(code):
    import urllib.request, urllib.parse, json as _json
    conn = get_connection()
    row = conn.execute("SELECT address, name FROM customers WHERE code=?", (code,)).fetchone()
    conn.close()
    if not row:
        return jsonify({'error': 'not found'}), 404
    address = row['address'] or row['name']
    query = urllib.parse.urlencode({'q': address + ' ประเทศไทย', 'format': 'json',
                                    'limit': 1, 'accept-language': 'th'})
    url = f'https://nominatim.openstreetmap.org/search?{query}'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'SendaiBoonswat-ERP/1.0'})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = _json.loads(resp.read())
        if data:
            lat, lng = float(data[0]['lat']), float(data[0]['lon'])
            models.save_customer_geocode(code, lat, lng)
            return jsonify({'ok': True, 'lat': lat, 'lng': lng, 'display': data[0].get('display_name','')})
        return jsonify({'ok': False, 'reason': 'no result'})
    except Exception as e:
        return jsonify({'ok': False, 'reason': str(e)}), 500


@app.route('/api/customers/geojson')
def customer_geojson():
    zone  = request.args.get('zone') or None
    ctype = request.args.get('type') or None
    rows  = models.get_customers_for_map(zone=zone, customer_type=ctype, geocoded_only=True)
    features = []
    for r in rows:
        features.append({
            'type': 'Feature',
            'geometry': {'type': 'Point', 'coordinates': [r['lng'], r['lat']]},
            'properties': {k: r[k] for k in ('code','name','zone','customer_type',
                                              'address','phone','salesperson','credit_days')}
        })
    return jsonify({'type': 'FeatureCollection', 'features': features})


if __name__ == '__main__':
    app.run(debug=True, port=5001, use_reloader=False)
