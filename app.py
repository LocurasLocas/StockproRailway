from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from functools import wraps
from threading import Thread
import os
import json

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'stockpro-secret-2024')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///stockpro.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# ─── EMAIL CONFIG ─────────────────────────────────────────────────────────────
app.config['MAIL_SERVER']   = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT']     = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS']  = os.environ.get('MAIL_USE_TLS', 'true').lower() == 'true'
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', '')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', '')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER', os.environ.get('MAIL_USERNAME', ''))
app.config['MAIL_ENABLED']  = bool(os.environ.get('MAIL_USERNAME', ''))

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
mail = Mail(app)
# ─── MODELS ───────────────────────────────────────────────────────────────────

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), default='viewer')  # admin, editor, viewer
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active_user = db.Column(db.Boolean, default=True)
    notify_low_stock = db.Column(db.Boolean, default=True)
    notify_new_budget = db.Column(db.Boolean, default=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_admin(self):
        return self.role == 'admin'

    def can_edit(self):
        return self.role in ['admin', 'editor']


class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.String(200))
    color = db.Column(db.String(7), default='#6366f1')
    products = db.relationship('Product', backref='category', lazy=True)


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    sku = db.Column(db.String(50), unique=True)
    description = db.Column(db.Text)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'))
    price = db.Column(db.Float, default=0.0)
    cost = db.Column(db.Float, default=0.0)
    stock = db.Column(db.Integer, default=0)
    min_stock = db.Column(db.Integer, default=5)
    unit = db.Column(db.String(20), default='unidad')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)

    @property
    def low_stock(self):
        return self.stock <= self.min_stock

    @property
    def stock_value(self):
        return self.stock * self.cost


class StockMovement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    product = db.relationship('Product', backref='movements')
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref='movements')
    movement_type = db.Column(db.String(20), nullable=False)  # entrada, salida, ajuste
    quantity = db.Column(db.Integer, nullable=False)
    previous_stock = db.Column(db.Integer)
    new_stock = db.Column(db.Integer)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Budget(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    budget_number = db.Column(db.String(20), unique=True)
    client_name = db.Column(db.String(200), nullable=False)
    client_email = db.Column(db.String(120))
    client_phone = db.Column(db.String(30))
    client_address = db.Column(db.Text)
    notes = db.Column(db.Text)
    discount = db.Column(db.Float, default=0.0)
    tax = db.Column(db.Float, default=21.0)
    status = db.Column(db.String(20), default='borrador')  # borrador, enviado, aprobado, rechazado
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    user = db.relationship('User', backref='budgets')
    items = db.relationship('BudgetItem', backref='budget', lazy=True, cascade='all, delete-orphan')

    def generate_number(self):
        last = Budget.query.order_by(Budget.id.desc()).first()
        num = (last.id + 1) if last else 1
        self.budget_number = f"PRES-{datetime.now().year}-{num:04d}"

    @property
    def subtotal(self):
        return sum(item.subtotal for item in self.items)

    @property
    def discount_amount(self):
        return self.subtotal * (self.discount / 100)

    @property
    def tax_amount(self):
        return (self.subtotal - self.discount_amount) * (self.tax / 100)

    @property
    def total(self):
        return self.subtotal - self.discount_amount + self.tax_amount


class BudgetItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    budget_id = db.Column(db.Integer, db.ForeignKey('budget.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'))
    product = db.relationship('Product')
    description = db.Column(db.String(300), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    unit_price = db.Column(db.Float, nullable=False)

    @property
    def subtotal(self):
        return self.quantity * self.unit_price


# ─── DECORATORS ───────────────────────────────────────────────────────────────

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_admin():
            flash('Acceso denegado. Se requieren permisos de administrador.', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated


def editor_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.can_edit():
            flash('Acceso denegado. Se requieren permisos de editor.', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ─── EMAIL HELPERS ────────────────────────────────────────────────────────────

def send_async_email(app, msg):
    with app.app_context():
        try:
            mail.send(msg)
        except Exception as e:
            print(f"[EMAIL ERROR] {e}")


def send_email(subject, recipients, html_body, attachments=None):
    if not app.config.get('MAIL_ENABLED'):
        print(f"[EMAIL DISABLED] To: {recipients} | Subject: {subject}")
        return
    if not recipients:
        return
    msg = Message(subject=subject, recipients=recipients, html=html_body)
    if attachments:
        for name, data, mime in attachments:
            msg.attach(name, mime, data)
    Thread(target=send_async_email, args=(app, msg)).start()


def email_template(title, content, color='#6366f1'):
    """Wrap content in a clean branded HTML email template."""
    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:'Segoe UI',Arial,sans-serif">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;padding:32px 16px">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%">
        <!-- Header -->
        <tr><td style="background:{color};border-radius:12px 12px 0 0;padding:28px 32px">
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
              <td>
                <div style="font-size:22px;font-weight:700;color:white;letter-spacing:-0.5px">
                  📦 StockPro
                </div>
                <div style="font-size:13px;color:rgba(255,255,255,0.75);margin-top:4px">Sistema de Gestión de Inventario</div>
              </td>
            </tr>
          </table>
        </td></tr>
        <!-- Body -->
        <tr><td style="background:#ffffff;padding:32px;border-left:1px solid #e2e8f0;border-right:1px solid #e2e8f0">
          <h2 style="margin:0 0 16px;font-size:20px;color:#1e293b;font-weight:700">{title}</h2>
          {content}
        </td></tr>
        <!-- Footer -->
        <tr><td style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:0 0 12px 12px;padding:20px 32px;text-align:center">
          <p style="margin:0;font-size:12px;color:#94a3b8">
            Este email fue enviado automáticamente por StockPro.<br>
            Por favor no respondas este mensaje.
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def notify_low_stock_alert(product):
    """Send low stock alert to all admins and editors with notifications enabled."""
    recipients = [
        u.email for u in User.query.filter(
            User.is_active_user == True,
            User.role.in_(['admin', 'editor']),
            User.notify_low_stock == True
        ).all()
        if u.email
    ]
    content = f"""
    <div style="background:#fff7ed;border:1px solid #fed7aa;border-radius:8px;padding:20px;margin-bottom:20px">
      <div style="font-size:28px;margin-bottom:8px">⚠️</div>
      <div style="font-size:16px;font-weight:600;color:#c2410c;margin-bottom:4px">Stock bajo detectado</div>
      <div style="font-size:14px;color:#92400e">El producto llegó al nivel mínimo de stock</div>
    </div>
    <table style="width:100%;border-collapse:collapse;margin-bottom:20px">
      <tr style="background:#f8fafc"><td style="padding:10px 14px;font-size:12px;font-weight:600;text-transform:uppercase;color:#64748b;border-bottom:1px solid #e2e8f0">Producto</td><td style="padding:10px 14px;font-size:14px;color:#1e293b;font-weight:600;border-bottom:1px solid #e2e8f0">{product.name}</td></tr>
      <tr><td style="padding:10px 14px;font-size:12px;font-weight:600;text-transform:uppercase;color:#64748b;border-bottom:1px solid #e2e8f0">SKU</td><td style="padding:10px 14px;font-size:14px;color:#1e293b;border-bottom:1px solid #e2e8f0">{product.sku or '—'}</td></tr>
      <tr style="background:#f8fafc"><td style="padding:10px 14px;font-size:12px;font-weight:600;text-transform:uppercase;color:#64748b;border-bottom:1px solid #e2e8f0">Stock actual</td><td style="padding:10px 14px;font-size:18px;font-weight:700;color:#ef4444;border-bottom:1px solid #e2e8f0">{product.stock} {product.unit}</td></tr>
      <tr><td style="padding:10px 14px;font-size:12px;font-weight:600;text-transform:uppercase;color:#64748b">Stock mínimo</td><td style="padding:10px 14px;font-size:14px;color:#1e293b">{product.min_stock} {product.unit}</td></tr>
    </table>
    <p style="font-size:14px;color:#64748b;margin:0">Ingresá al sistema para reponer el stock de este producto.</p>
    """
    send_email(
        subject=f"⚠️ StockPro — Stock bajo: {product.name}",
        recipients=recipients,
        html_body=email_template(f"Stock bajo: {product.name}", content, '#f59e0b')
    )


def notify_budget_created(budget):
    """Notify admins when a new budget is created."""
    recipients = [
        u.email for u in User.query.filter(
            User.is_active_user == True,
            User.role == 'admin',
            User.notify_new_budget == True
        ).all()
        if u.email
    ]
    content = f"""
    <div style="background:#eef2ff;border:1px solid #c7d2fe;border-radius:8px;padding:20px;margin-bottom:20px">
      <div style="font-size:28px;margin-bottom:8px">💰</div>
      <div style="font-size:16px;font-weight:600;color:#4338ca">Nuevo presupuesto generado</div>
    </div>
    <table style="width:100%;border-collapse:collapse;margin-bottom:20px">
      <tr style="background:#f8fafc"><td style="padding:10px 14px;font-size:12px;font-weight:600;text-transform:uppercase;color:#64748b;border-bottom:1px solid #e2e8f0">N° Presupuesto</td><td style="padding:10px 14px;font-size:14px;color:#6366f1;font-weight:700;border-bottom:1px solid #e2e8f0">{budget.budget_number}</td></tr>
      <tr><td style="padding:10px 14px;font-size:12px;font-weight:600;text-transform:uppercase;color:#64748b;border-bottom:1px solid #e2e8f0">Cliente</td><td style="padding:10px 14px;font-size:14px;color:#1e293b;font-weight:600;border-bottom:1px solid #e2e8f0">{budget.client_name}</td></tr>
      <tr style="background:#f8fafc"><td style="padding:10px 14px;font-size:12px;font-weight:600;text-transform:uppercase;color:#64748b;border-bottom:1px solid #e2e8f0">Total</td><td style="padding:10px 14px;font-size:20px;font-weight:700;color:#10b981;border-bottom:1px solid #e2e8f0">${budget.total:,.2f}</td></tr>
      <tr><td style="padding:10px 14px;font-size:12px;font-weight:600;text-transform:uppercase;color:#64748b;border-bottom:1px solid #e2e8f0">Ítems</td><td style="padding:10px 14px;font-size:14px;color:#1e293b;border-bottom:1px solid #e2e8f0">{len(budget.items)}</td></tr>
      <tr style="background:#f8fafc"><td style="padding:10px 14px;font-size:12px;font-weight:600;text-transform:uppercase;color:#64748b">Creado por</td><td style="padding:10px 14px;font-size:14px;color:#1e293b">{budget.user.username}</td></tr>
    </table>
    """
    send_email(
        subject=f"💰 StockPro — Nuevo presupuesto {budget.budget_number} para {budget.client_name}",
        recipients=recipients,
        html_body=email_template(f"Nuevo presupuesto: {budget.budget_number}", content)
    )


def send_budget_to_client(budget, pdf_bytes):
    """Send budget PDF to the client via email."""
    if not budget.client_email:
        return False
    items_html = ''.join([
        f"<tr><td style='padding:8px 12px;border-bottom:1px solid #e2e8f0'>{item.description}</td>"
        f"<td style='padding:8px 12px;border-bottom:1px solid #e2e8f0;text-align:right'>{item.quantity:g}</td>"
        f"<td style='padding:8px 12px;border-bottom:1px solid #e2e8f0;text-align:right'>${item.unit_price:,.2f}</td>"
        f"<td style='padding:8px 12px;border-bottom:1px solid #e2e8f0;text-align:right;font-weight:600'>${item.subtotal:,.2f}</td></tr>"
        for item in budget.items
    ])
    content = f"""
    <p style="font-size:15px;color:#475569;margin:0 0 20px">Estimado/a <strong>{budget.client_name}</strong>,</p>
    <p style="font-size:14px;color:#64748b;margin:0 0 24px">Adjuntamos el presupuesto solicitado. A continuación encontrará el detalle:</p>
    <table style="width:100%;border-collapse:collapse;margin-bottom:20px;font-size:14px">
      <thead><tr style="background:#6366f1">
        <th style="padding:10px 12px;color:white;text-align:left;font-weight:600">Descripción</th>
        <th style="padding:10px 12px;color:white;text-align:right;font-weight:600">Cant.</th>
        <th style="padding:10px 12px;color:white;text-align:right;font-weight:600">Precio</th>
        <th style="padding:10px 12px;color:white;text-align:right;font-weight:600">Subtotal</th>
      </tr></thead>
      <tbody>{items_html}</tbody>
    </table>
    <table style="width:100%;margin-bottom:24px">
      {'<tr><td style="text-align:right;padding:4px 12px;color:#64748b;font-size:13px">Subtotal:</td><td style="text-align:right;padding:4px 12px;font-weight:600;font-size:13px">$'+f"{budget.subtotal:,.2f}"+'</td></tr>' }
      {'<tr><td style="text-align:right;padding:4px 12px;color:#64748b;font-size:13px">Descuento ('+str(int(budget.discount))+'%):</td><td style="text-align:right;padding:4px 12px;color:#ef4444;font-size:13px">-$'+f"{budget.discount_amount:,.2f}"+'</td></tr>' if budget.discount > 0 else ''}
      {'<tr><td style="text-align:right;padding:4px 12px;color:#64748b;font-size:13px">IVA ('+str(int(budget.tax))+'%):</td><td style="text-align:right;padding:4px 12px;font-size:13px">$'+f"{budget.tax_amount:,.2f}"+'</td></tr>' if budget.tax > 0 else ''}
      <tr style="border-top:2px solid #6366f1"><td style="text-align:right;padding:10px 12px;font-weight:700;color:#6366f1;font-size:16px">TOTAL:</td><td style="text-align:right;padding:10px 12px;font-weight:700;color:#6366f1;font-size:18px">${budget.total:,.2f}</td></tr>
    </table>
    {'<div style="background:#f8fafc;border-radius:8px;padding:16px;margin-bottom:20px"><p style="margin:0;font-size:13px;color:#64748b"><strong>Notas:</strong> '+budget.notes+'</p></div>' if budget.notes else ''}
    <p style="font-size:13px;color:#94a3b8;margin:0">El presupuesto adjunto en PDF tiene validez de 30 días desde su emisión. Para cualquier consulta no dude en contactarnos.</p>
    """
    send_email(
        subject=f"Presupuesto {budget.budget_number} — StockPro",
        recipients=[budget.client_email],
        html_body=email_template(f"Su presupuesto N° {budget.budget_number}", content),
        attachments=[(f"presupuesto_{budget.budget_number}.pdf", pdf_bytes, 'application/pdf')]
    )
    return True



@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and user.check_password(request.form['password']) and user.is_active_user:
            login_user(user, remember=request.form.get('remember'))
            return redirect(url_for('dashboard'))
        flash('Usuario o contraseña incorrectos.', 'error')
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


# ─── DASHBOARD ────────────────────────────────────────────────────────────────

@app.route('/')
@login_required
def dashboard():
    total_products = Product.query.filter_by(is_active=True).count()
    total_categories = Category.query.count()
    low_stock_products = Product.query.filter(
        Product.stock <= Product.min_stock, Product.is_active == True
    ).all()
    total_stock_value = db.session.query(
        db.func.sum(Product.stock * Product.cost)
    ).filter(Product.is_active == True).scalar() or 0

    recent_movements = StockMovement.query.order_by(
        StockMovement.created_at.desc()
    ).limit(8).all()

    recent_budgets = Budget.query.order_by(Budget.created_at.desc()).limit(5).all()

    # Stock by category
    categories = Category.query.all()
    cat_data = []
    for c in categories:
        total = sum(p.stock for p in c.products if p.is_active)
        cat_data.append({'name': c.name, 'stock': total, 'color': c.color})

    return render_template('dashboard.html',
        total_products=total_products,
        total_categories=total_categories,
        low_stock_products=low_stock_products,
        total_stock_value=total_stock_value,
        recent_movements=recent_movements,
        recent_budgets=recent_budgets,
        cat_data=json.dumps(cat_data)
    )


# ─── PRODUCTS ─────────────────────────────────────────────────────────────────

@app.route('/productos')
@login_required
def products():
    q = request.args.get('q', '')
    cat_id = request.args.get('cat', '')
    query = Product.query.filter_by(is_active=True)
    if q:
        query = query.filter(Product.name.ilike(f'%{q}%'))
    if cat_id:
        query = query.filter_by(category_id=cat_id)
    products = query.order_by(Product.name).all()
    categories = Category.query.all()
    return render_template('products.html', products=products, categories=categories, q=q, cat_id=cat_id)


@app.route('/productos/nuevo', methods=['GET', 'POST'])
@login_required
@editor_required
def new_product():
    if request.method == 'POST':
        product = Product(
            name=request.form['name'],
            sku=request.form['sku'] or None,
            description=request.form['description'],
            category_id=request.form['category_id'] or None,
            price=float(request.form['price'] or 0),
            cost=float(request.form['cost'] or 0),
            stock=int(request.form['stock'] or 0),
            min_stock=int(request.form['min_stock'] or 5),
            unit=request.form['unit']
        )
        db.session.add(product)
        db.session.flush()
        if product.stock > 0:
            movement = StockMovement(
                product_id=product.id,
                user_id=current_user.id,
                movement_type='entrada',
                quantity=product.stock,
                previous_stock=0,
                new_stock=product.stock,
                notes='Stock inicial'
            )
            db.session.add(movement)
        db.session.commit()
        flash('Producto creado exitosamente.', 'success')
        return redirect(url_for('products'))
    categories = Category.query.all()
    return render_template('product_form.html', product=None, categories=categories)


@app.route('/productos/<int:id>/editar', methods=['GET', 'POST'])
@login_required
@editor_required
def edit_product(id):
    product = Product.query.get_or_404(id)
    if request.method == 'POST':
        product.name = request.form['name']
        product.sku = request.form['sku'] or None
        product.description = request.form['description']
        product.category_id = request.form['category_id'] or None
        product.price = float(request.form['price'] or 0)
        product.cost = float(request.form['cost'] or 0)
        product.min_stock = int(request.form['min_stock'] or 5)
        product.unit = request.form['unit']
        product.updated_at = datetime.utcnow()
        db.session.commit()
        flash('Producto actualizado.', 'success')
        return redirect(url_for('products'))
    categories = Category.query.all()
    return render_template('product_form.html', product=product, categories=categories)


@app.route('/productos/<int:id>/stock', methods=['POST'])
@login_required
@editor_required
def update_stock(id):
    product = Product.query.get_or_404(id)
    data = request.get_json()
    movement_type = data.get('type')
    quantity = int(data.get('quantity', 0))
    notes = data.get('notes', '')

    prev = product.stock
    if movement_type == 'entrada':
        product.stock += quantity
    elif movement_type == 'salida':
        if product.stock < quantity:
            return jsonify({'error': 'Stock insuficiente'}), 400
        product.stock -= quantity
    elif movement_type == 'ajuste':
        product.stock = quantity

    movement = StockMovement(
        product_id=product.id,
        user_id=current_user.id,
        movement_type=movement_type,
        quantity=quantity,
        previous_stock=prev,
        new_stock=product.stock,
        notes=notes
    )
    db.session.add(movement)
    product.updated_at = datetime.utcnow()
    db.session.commit()
    # Notify if stock just dropped to or below minimum
    if product.low_stock and not (prev <= product.min_stock):
        notify_low_stock_alert(product)
    return jsonify({'stock': product.stock, 'low_stock': product.low_stock})


@app.route('/productos/<int:id>/eliminar', methods=['POST'])
@login_required
@admin_required
def delete_product(id):
    product = Product.query.get_or_404(id)
    product.is_active = False
    db.session.commit()
    flash('Producto eliminado.', 'success')
    return redirect(url_for('products'))


# ─── CATEGORIES ───────────────────────────────────────────────────────────────

@app.route('/categorias')
@login_required
def categories():
    cats = Category.query.all()
    return render_template('categories.html', categories=cats)


@app.route('/categorias/nueva', methods=['POST'])
@login_required
@editor_required
def new_category():
    cat = Category(
        name=request.form['name'],
        description=request.form['description'],
        color=request.form['color']
    )
    db.session.add(cat)
    db.session.commit()
    flash('Categoría creada.', 'success')
    return redirect(url_for('categories'))


@app.route('/categorias/<int:id>/eliminar', methods=['POST'])
@login_required
@admin_required
def delete_category(id):
    cat = Category.query.get_or_404(id)
    db.session.delete(cat)
    db.session.commit()
    flash('Categoría eliminada.', 'success')
    return redirect(url_for('categories'))


# ─── MOVEMENTS ────────────────────────────────────────────────────────────────

@app.route('/movimientos')
@login_required
def movements():
    page = request.args.get('page', 1, type=int)
    mvs = StockMovement.query.order_by(
        StockMovement.created_at.desc()
    ).paginate(page=page, per_page=20)
    return render_template('movements.html', movements=mvs)


# ─── BUDGETS ──────────────────────────────────────────────────────────────────

@app.route('/presupuestos')
@login_required
def budgets():
    bgs = Budget.query.order_by(Budget.created_at.desc()).all()
    return render_template('budgets.html', budgets=bgs)


@app.route('/presupuestos/nuevo', methods=['GET', 'POST'])
@login_required
def new_budget():
    if request.method == 'POST':
        data = request.get_json()
        budget = Budget(
            client_name=data['client_name'],
            client_email=data.get('client_email', ''),
            client_phone=data.get('client_phone', ''),
            client_address=data.get('client_address', ''),
            notes=data.get('notes', ''),
            discount=float(data.get('discount', 0)),
            tax=float(data.get('tax', 21)),
            user_id=current_user.id
        )
        budget.generate_number()
        db.session.add(budget)
        db.session.flush()
        for item_data in data.get('items', []):
            item = BudgetItem(
                budget_id=budget.id,
                product_id=item_data.get('product_id') or None,
                description=item_data['description'],
                quantity=float(item_data['quantity']),
                unit_price=float(item_data['unit_price'])
            )
            db.session.add(item)
        db.session.commit()
        notify_budget_created(budget)
        return jsonify({'id': budget.id, 'number': budget.budget_number})
    products = Product.query.filter_by(is_active=True).order_by(Product.name).all()
    return render_template('budget_form.html', products=products)


@app.route('/presupuestos/<int:id>')
@login_required
def view_budget(id):
    budget = Budget.query.get_or_404(id)
    return render_template('budget_view.html', budget=budget)


@app.route('/presupuestos/<int:id>/pdf')
@login_required
def budget_pdf(id):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
    import io

    budget = Budget.query.get_or_404(id)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
        rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)

    styles = getSampleStyleSheet()
    story = []

    # Header
    title_style = ParagraphStyle('title', fontSize=28, textColor=colors.HexColor('#1e293b'),
        spaceAfter=2, fontName='Helvetica-Bold')
    sub_style = ParagraphStyle('sub', fontSize=11, textColor=colors.HexColor('#64748b'),
        spaceAfter=4)
    story.append(Paragraph("PRESUPUESTO", title_style))
    story.append(Paragraph(f"N° {budget.budget_number}", sub_style))
    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#6366f1')))
    story.append(Spacer(1, 0.4*cm))

    # Info grid
    info_data = [
        ['CLIENTE', '', 'DATOS DEL PRESUPUESTO', ''],
        [budget.client_name, '', f'Fecha: {budget.created_at.strftime("%d/%m/%Y")}', ''],
        [budget.client_email or '-', '', f'Estado: {budget.status.upper()}', ''],
        [budget.client_phone or '-', '', f'Válido por: 30 días', ''],
    ]
    info_table = Table(info_data, colWidths=[8*cm, 1*cm, 6*cm, 2.5*cm])
    info_table.setStyle(TableStyle([
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 8),
        ('TEXTCOLOR', (0,0), (-1,0), colors.HexColor('#6366f1')),
        ('FONTSIZE', (0,1), (-1,-1), 10),
        ('TEXTCOLOR', (0,1), (-1,-1), colors.HexColor('#1e293b')),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 0.6*cm))

    # Items table
    headers = ['#', 'Descripción', 'Cant.', 'Precio Unit.', 'Subtotal']
    rows = [headers]
    for i, item in enumerate(budget.items, 1):
        rows.append([
            str(i),
            item.description,
            f"{item.quantity:g}",
            f"${item.unit_price:,.2f}",
            f"${item.subtotal:,.2f}"
        ])

    col_widths = [0.8*cm, 9*cm, 1.5*cm, 3*cm, 3*cm]
    items_table = Table(rows, colWidths=col_widths)
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#6366f1')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 9),
        ('ALIGN', (2,0), (-1,-1), 'RIGHT'),
        ('FONTSIZE', (0,1), (-1,-1), 9),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f8fafc')]),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#e2e8f0')),
        ('PADDING', (0,0), (-1,-1), 6),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 0.5*cm))

    # Totals
    totals_style = ParagraphStyle('tot', fontSize=10, textColor=colors.HexColor('#1e293b'))
    totals_bold = ParagraphStyle('totb', fontSize=13, fontName='Helvetica-Bold',
        textColor=colors.HexColor('#6366f1'))
    totals_data = [
        ['', 'Subtotal:', f"${budget.subtotal:,.2f}"],
    ]
    if budget.discount > 0:
        totals_data.append(['', f'Descuento ({budget.discount:.0f}%):', f"-${budget.discount_amount:,.2f}"])
    if budget.tax > 0:
        totals_data.append(['', f'IVA ({budget.tax:.0f}%):', f"${budget.tax_amount:,.2f}"])
    totals_data.append(['', 'TOTAL:', f"${budget.total:,.2f}"])

    totals_table = Table(totals_data, colWidths=[10.8*cm, 3.5*cm, 3*cm])
    totals_table.setStyle(TableStyle([
        ('ALIGN', (1,0), (-1,-1), 'RIGHT'),
        ('FONTSIZE', (0,0), (-1,-2), 10),
        ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold'),
        ('FONTSIZE', (0,-1), (-1,-1), 13),
        ('TEXTCOLOR', (0,-1), (-1,-1), colors.HexColor('#6366f1')),
        ('LINEABOVE', (1,-1), (-1,-1), 1.5, colors.HexColor('#6366f1')),
        ('PADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(totals_table)

    if budget.notes:
        story.append(Spacer(1, 0.6*cm))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#e2e8f0')))
        story.append(Spacer(1, 0.3*cm))
        note_style = ParagraphStyle('note', fontSize=9, textColor=colors.HexColor('#64748b'))
        story.append(Paragraph('<b>Notas:</b>', note_style))
        story.append(Paragraph(budget.notes, note_style))

    doc.build(story)
    buffer.seek(0)
    return send_file(buffer, mimetype='application/pdf',
        download_name=f"presupuesto_{budget.budget_number}.pdf")


@app.route('/presupuestos/<int:id>/estado', methods=['POST'])
@login_required
def update_budget_status(id):
    budget = Budget.query.get_or_404(id)
    budget.status = request.form['status']
    db.session.commit()
    flash('Estado actualizado.', 'success')
    return redirect(url_for('view_budget', id=id))


@app.route('/presupuestos/<int:id>/enviar-email', methods=['POST'])
@login_required
def send_budget_email(id):
    """Generate PDF and email it directly to the client."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    import io

    budget = Budget.query.get_or_404(id)
    if not budget.client_email:
        flash('El cliente no tiene email registrado.', 'error')
        return redirect(url_for('view_budget', id=id))

    # Build PDF in memory
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
        rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    story = []
    title_style = ParagraphStyle('title', fontSize=28, textColor=colors.HexColor('#1e293b'), spaceAfter=2, fontName='Helvetica-Bold')
    sub_style = ParagraphStyle('sub', fontSize=11, textColor=colors.HexColor('#64748b'), spaceAfter=4)
    story.append(Paragraph("PRESUPUESTO", title_style))
    story.append(Paragraph(f"N° {budget.budget_number}", sub_style))
    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#6366f1')))
    story.append(Spacer(1, 0.4*cm))
    info_data = [
        ['CLIENTE', '', 'DATOS DEL PRESUPUESTO', ''],
        [budget.client_name, '', f'Fecha: {budget.created_at.strftime("%d/%m/%Y")}', ''],
        [budget.client_email or '-', '', f'Estado: {budget.status.upper()}', ''],
        [budget.client_phone or '-', '', 'Válido por: 30 días', ''],
    ]
    info_table = Table(info_data, colWidths=[8*cm, 1*cm, 6*cm, 2.5*cm])
    info_table.setStyle(TableStyle([
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'), ('FONTSIZE', (0,0), (-1,0), 8),
        ('TEXTCOLOR', (0,0), (-1,0), colors.HexColor('#6366f1')),
        ('FONTSIZE', (0,1), (-1,-1), 10), ('TEXTCOLOR', (0,1), (-1,-1), colors.HexColor('#1e293b')),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 0.6*cm))
    headers = ['#', 'Descripción', 'Cant.', 'Precio Unit.', 'Subtotal']
    rows = [headers] + [[str(i), item.description, f"{item.quantity:g}", f"${item.unit_price:,.2f}", f"${item.subtotal:,.2f}"] for i, item in enumerate(budget.items, 1)]
    items_table = Table(rows, colWidths=[0.8*cm, 9*cm, 1.5*cm, 3*cm, 3*cm])
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#6366f1')), ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'), ('FONTSIZE', (0,0), (-1,0), 9),
        ('ALIGN', (2,0), (-1,-1), 'RIGHT'), ('FONTSIZE', (0,1), (-1,-1), 9),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f8fafc')]),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#e2e8f0')), ('PADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 0.5*cm))
    totals_data = [['', 'Subtotal:', f"${budget.subtotal:,.2f}"]]
    if budget.discount > 0:
        totals_data.append(['', f'Descuento ({budget.discount:.0f}%):', f"-${budget.discount_amount:,.2f}"])
    if budget.tax > 0:
        totals_data.append(['', f'IVA ({budget.tax:.0f}%):', f"${budget.tax_amount:,.2f}"])
    totals_data.append(['', 'TOTAL:', f"${budget.total:,.2f}"])
    totals_table = Table(totals_data, colWidths=[10.8*cm, 3.5*cm, 3*cm])
    totals_table.setStyle(TableStyle([
        ('ALIGN', (1,0), (-1,-1), 'RIGHT'), ('FONTSIZE', (0,0), (-1,-2), 10),
        ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold'), ('FONTSIZE', (0,-1), (-1,-1), 13),
        ('TEXTCOLOR', (0,-1), (-1,-1), colors.HexColor('#6366f1')),
        ('LINEABOVE', (1,-1), (-1,-1), 1.5, colors.HexColor('#6366f1')), ('PADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(totals_table)
    doc.build(story)
    pdf_bytes = buffer.getvalue()

    ok = send_budget_to_client(budget, pdf_bytes)
    if ok:
        budget.status = 'enviado'
        db.session.commit()
        flash(f'Presupuesto enviado por email a {budget.client_email}.', 'success')
    else:
        flash('No se pudo enviar el email. Verificá la configuración de correo.', 'error')
    return redirect(url_for('view_budget', id=id))


# ─── EMAIL SETTINGS ───────────────────────────────────────────────────────────

@app.route('/configuracion/email', methods=['GET', 'POST'])
@login_required
@admin_required
def email_settings():
    if request.method == 'POST':
        # These are saved as env vars note — in a real deployment use .env or hosting panel
        flash('Configuración guardada. Reiniciá el servidor para aplicar los cambios de SMTP.', 'info')
        return redirect(url_for('email_settings'))
    return render_template('email_settings.html',
        mail_server=app.config.get('MAIL_SERVER', ''),
        mail_port=app.config.get('MAIL_PORT', 587),
        mail_username=app.config.get('MAIL_USERNAME', ''),
        mail_enabled=app.config.get('MAIL_ENABLED', False)
    )


@app.route('/configuracion/email/test', methods=['POST'])
@login_required
@admin_required
def test_email():
    content = """
    <div style="background:#d1fae5;border:1px solid #6ee7b7;border-radius:8px;padding:20px;margin-bottom:16px">
      <div style="font-size:24px;margin-bottom:8px">✅</div>
      <div style="font-size:16px;font-weight:600;color:#065f46">¡Email de prueba exitoso!</div>
    </div>
    <p style="font-size:14px;color:#64748b">Si recibiste este email, la configuración de correo de StockPro está funcionando correctamente.</p>
    """
    send_email(
        subject="✅ StockPro — Email de prueba",
        recipients=[current_user.email],
        html_body=email_template("Email de prueba", content, '#10b981')
    )
    flash(f'Email de prueba enviado a {current_user.email}.', 'success')
    return redirect(url_for('email_settings'))


@app.route('/configuracion/notificaciones', methods=['POST'])
@login_required
def update_notifications():
    current_user.notify_low_stock = 'notify_low_stock' in request.form
    current_user.notify_new_budget = 'notify_new_budget' in request.form
    db.session.commit()
    flash('Preferencias de notificación actualizadas.', 'success')
    return redirect(url_for('email_settings') if current_user.is_admin() else url_for('dashboard'))




# ─── USERS ────────────────────────────────────────────────────────────────────

@app.route('/usuarios')
@login_required
@admin_required
def users():
    users = User.query.all()
    return render_template('users.html', users=users)


@app.route('/usuarios/nuevo', methods=['POST'])
@login_required
@admin_required
def new_user():
    if User.query.filter_by(username=request.form['username']).first():
        flash('El nombre de usuario ya existe.', 'error')
        return redirect(url_for('users'))
    user = User(
        username=request.form['username'],
        email=request.form['email'],
        role=request.form['role']
    )
    user.set_password(request.form['password'])
    db.session.add(user)
    db.session.commit()
    flash('Usuario creado exitosamente.', 'success')
    return redirect(url_for('users'))


@app.route('/usuarios/<int:id>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_user(id):
    user = User.query.get_or_404(id)
    if user.id != current_user.id:
        user.is_active_user = not user.is_active_user
        db.session.commit()
    return redirect(url_for('users'))


@app.route('/api/products/search')
@login_required
def api_search_products():
    q = request.args.get('q', '')
    products = Product.query.filter(
        Product.name.ilike(f'%{q}%'), Product.is_active == True
    ).limit(10).all()
    return jsonify([{
        'id': p.id, 'name': p.name, 'price': p.price,
        'stock': p.stock, 'unit': p.unit, 'sku': p.sku
    } for p in products])


# ─── INIT ─────────────────────────────────────────────────────────────────────

def init_db():
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', email='admin@stockpro.com', role='admin')
            admin.set_password('admin123')
            db.session.add(admin)
            cats = [
                Category(name='General', description='Productos generales', color='#6366f1'),
                Category(name='Electrónica', description='Equipos electrónicos', color='#06b6d4'),
                Category(name='Herramientas', description='Herramientas y equipamiento', color='#f59e0b'),
            ]
            for c in cats:
                db.session.add(c)
            db.session.commit()
            print("✅ Base de datos inicializada. Usuario admin/admin123 creado.")


if __name__ == '__main__':
    init_db()
    app.run(debug=True)
