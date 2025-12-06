from flask import Flask, render_template, redirect, url_for, flash, request, abort, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from functools import wraps
import time 

app = Flask(__name__)
app.config['SECRET_KEY'] = 'change-this-to-a-secure-random-value' 
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///farmers.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Models
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # farmer, customer, or admin
    name = db.Column(db.String(100))
    contact_number = db.Column(db.String(20))

    products = db.relationship('Product', backref='farmer', lazy=True)
    orders = db.relationship('Order', backref='customer', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_farmer(self):
        return self.role == 'farmer'

    def is_customer(self):
        return self.role == 'customer'
        
    def is_admin(self):
        return self.role == 'admin'

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    farmer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text)
    quantity = db.Column(db.Integer, nullable=False, default=0)
    price = db.Column(db.Float, nullable=False, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    image_url = db.Column(db.String(255))

    orders = db.relationship('Order', backref='product', lazy=True)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    total_price = db.Column(db.Float, nullable=False)
    order_date = db.Column(db.DateTime, default=datetime.utcnow)
    is_new = db.Column(db.Boolean, default=True)

# User loader for flask-login
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Role-based access decorator
def role_required(role):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return login_manager.unauthorized()
            if current_user.role != role:
                abort(403)
            return f(*args, **kwargs)
        return wrapped
    return decorator

# --- AI FEATURE: Image Generation Logic ---
def generate_product_image_url(product_name):
    """
    Simulates calling an AI image generation API based on the product name.
    """
    name_lower = product_name.lower()
    
    if 'tomato' in name_lower:
        base_path = '/static/images/ai_tomatoes.jpg'
    elif 'spinach' in name_lower:
        base_path = '/static/images/ai_spinach.jpg'
    elif 'cabbage' in name_lower:
        base_path = '/static/images/ai_cabbage.jpg'
    else:
        # Fallback for all other products
        base_path = '/static/images/default_ai_product.jpg' 

    return base_path
# --- END AI FEATURE ---

# Routes
@app.route('/')
def index():
    # --- FIX: Ensure homepage is default view if not authenticated ---
    if not current_user.is_authenticated:
        return render_template('index.html')
        
    # If authenticated, redirect based on role
    if current_user.is_admin():
        return redirect(url_for('admin_dashboard'))
    elif current_user.is_farmer():
        return redirect(url_for('farmer_dashboard'))
    else:
        # Default for authenticated customer
        return redirect(url_for('products'))
# --- END FIX ---


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username').strip()
        password = request.form.get('password')
        role = request.form.get('role')
        name = request.form.get('name', '').strip()
        contact_number = request.form.get('contact_number', '').strip()
        
        if not username or not password or role not in ('farmer', 'customer') or not name or not contact_number:
            flash('All required fields must be filled', 'danger')
            return redirect(url_for('register'))
        if User.query.filter_by(username=username).first():
            flash('Username already taken', 'warning')
            return redirect(url_for('register'))
            
        user = User(
            username=username, 
            role=role, 
            name=name,
            contact_number=contact_number
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash('Registration successful. Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username').strip()
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            flash('Logged in successfully.', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        flash('Invalid username or password.', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out', 'info')
    return redirect(url_for('index'))

# =========================================================
# Farmer Routes
# =========================================================
@app.route('/farmer/dashboard')
@role_required('farmer')
def farmer_dashboard():
    products = Product.query.filter_by(farmer_id=current_user.id).order_by(Product.created_at.desc()).all()
    
    orders = Order.query.join(Product).join(User, Order.customer_id == User.id).filter(
        Product.farmer_id == current_user.id
    ).with_entities(
        Order.id, 
        Order.quantity, 
        Order.total_price, 
        Order.order_date,
        Order.is_new,
        Product.name.label('product_name'),
        User.name.label('customer_name')
    ).order_by(Order.order_date.desc()).all()

    new_orders = Order.query.join(Product).filter(
        Product.farmer_id == current_user.id, 
        Order.is_new == True
    ).all()
    
    for order in new_orders:
        order.is_new = False
    
    db.session.commit()
    return render_template('farmer_dashboard.html', products=products, orders=orders)

@app.route('/api/farmer/new_orders_count')
@role_required('farmer')
def new_orders_count():
    count = Order.query.join(Product).filter(
        Product.farmer_id == current_user.id, 
        Order.is_new == True
    ).count()
    return jsonify({'new_orders_count': count})

@app.route('/farmer/add_product', methods=['GET', 'POST'])
@role_required('farmer')
def add_product():
    if request.method == 'POST':
        name = request.form.get('name').strip()
        description = request.form.get('description', '').strip()
        quantity = int(request.form.get('quantity') or 0)
        price = float(request.form.get('price') or 0.0)
        image_url = request.form.get('image_url', '').strip()
        
        if not name:
            flash('Product name required', 'danger')
            return redirect(url_for('add_product'))
        
        if not image_url:
            image_url = generate_product_image_url(name)
            
        p = Product(farmer_id=current_user.id, name=name, description=description, quantity=quantity, price=price, image_url=image_url)
        db.session.add(p)
        db.session.commit()
        flash('Product added', 'success')
        return redirect(url_for('farmer_dashboard'))
    return render_template('add_edit_product.html', action='Add')

@app.route('/farmer/edit_product/<int:product_id>', methods=['GET', 'POST'])
@role_required('farmer')
def edit_product(product_id):
    product = Product.query.get_or_404(product_id)
    if product.farmer_id != current_user.id:
        abort(403)
    if request.method == 'POST':
        product.name = request.form.get('name').strip()
        product.description = request.form.get('description', '').strip()
        product.quantity = int(request.form.get('quantity') or 0)
        product.price = float(request.form.get('price') or 0.0)
        
        new_image_url = request.form.get('image_url', '').strip()
        regenerate_ai = request.form.get('regenerate_ai')
        
        if new_image_url:
            product.image_url = new_image_url
        elif regenerate_ai:
            product.image_url = generate_product_image_url(product.name)
        
        db.session.commit()
        flash('Product updated', 'success')
        return redirect(url_for('farmer_dashboard'))
    return render_template('add_edit_product.html', product=product, action='Edit')

@app.route('/farmer/delete_product/<int:product_id>', methods=['POST'])
@role_required('farmer')
def delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    if product.farmer_id != current_user.id:
        abort(403)
    db.session.delete(product)
    db.session.commit()
    flash('Product deleted', 'info')
    return redirect(url_for('farmer_dashboard'))


# =========================================================
# Customer Routes
# =========================================================
@app.route('/products')
def products():
    products = Product.query.filter(Product.quantity > 0).order_by(Product.created_at.desc()).all()
    return render_template('products.html', products=products)

@app.route('/product/<int:product_id>')
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    return render_template('product_detail.html', product=product)

@app.route('/order/<int:product_id>', methods=['GET', 'POST'])
@login_required
def order_product(product_id):
    product = Product.query.get_or_404(product_id)
    if not current_user.is_customer():
        flash('Only customers can place orders', 'warning')
        return redirect(url_for('products'))
    if request.method == 'POST':
        qty = int(request.form.get('quantity') or 0)
        if qty <= 0:
            flash('Invalid quantity', 'danger')
            return redirect(url_for('order_product', product_id=product_id))
        if qty > product.quantity:
            flash('Not enough stock available', 'danger')
            return redirect(url_for('order_product', product_id=product_id))
        total = qty * product.price
        order = Order(customer_id=current_user.id, product_id=product.id, quantity=qty, total_price=total, is_new=True)
        product.quantity -= qty
        db.session.add(order)
        db.session.commit()
        flash('Order placed successfully', 'success')
        return redirect(url_for('my_orders'))
    return render_template('order_form.html', product=product)

@app.route('/my_orders')
@login_required
def my_orders():
    if current_user.is_customer():
        orders = Order.query.join(Product).filter(Order.customer_id == current_user.id).order_by(Order.order_date.desc()).all()
    else:
        orders = Order.query.join(Product).filter(Product.farmer_id == current_user.id).order_by(Order.order_date.desc()).all()
    return render_template('my_orders.html', orders=orders)


# =========================================================
# Admin Routes
# =========================================================
@app.route('/admin/dashboard')
@role_required('admin')
def admin_dashboard():
    total_users = User.query.count()
    total_products = Product.query.count()
    total_orders = Order.query.count()
    recent_orders = Order.query.order_by(Order.order_date.desc()).limit(10).all()
    return render_template('admin_dashboard.html', total_users=total_users, total_products=total_products, total_orders=total_orders, recent_orders=recent_orders)

@app.route('/admin/users')
@role_required('admin')
def admin_users():
    users = User.query.filter(User.id != current_user.id).order_by(User.id.asc()).all()
    return render_template('admin_users.html', users=users)

@app.route('/admin/edit_user/<int:user_id>', methods=['GET', 'POST'])
@role_required('admin')
def admin_edit_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.username == 'admin':
        flash('Cannot modify the primary system administrator account.', 'danger')
        return redirect(url_for('admin_users'))
    if request.method == 'POST':
        user.name = request.form.get('name').strip()
        user.username = request.form.get('username').strip()
        user.contact_number = request.form.get('contact_number').strip()
        user.role = request.form.get('role')
        new_password = request.form.get('password')
        if new_password:
            user.set_password(new_password)
        db.session.commit()
        flash(f'User {user.username} updated successfully.', 'success')
        return redirect(url_for('admin_users'))
    return render_template('admin_edit_user.html', user=user)

@app.route('/admin/products')
@role_required('admin')
def admin_products():
    products = Product.query.order_by(Product.created_at.desc()).all()
    return render_template('admin_products.html', products=products)

# Create demo data if DB is empty
def create_demo_data():
    if User.query.first():
        return
    
    # Admin User (Troubleshooting password is '123')
    admin = User(username='admin', role='admin', name='System Admin', contact_number='0000000000')
    admin.set_password('123') 

    # Farmer User
    farmer = User(username='farmer1', role='farmer', name='Alice Farmer', contact_number='9876543210')
    farmer.set_password('farmerpass')
    
    # Customer User
    customer = User(username='cust1', role='customer', name='Bob Customer', contact_number='9998887776')
    customer.set_password('custpass')
    
    db.session.add_all([admin, farmer, customer])
    db.session.commit()
    
    # Demo Products (using AI image simulation)
    p1 = Product(farmer_id=farmer.id, name='Tomatoes', description='Fresh red tomatoes', quantity=100, price=30.0, image_url=generate_product_image_url('Tomatoes'))
    p2 = Product(farmer_id=farmer.id, name='Spinach', description='Leafy spinach', quantity=50, price=20.0, image_url=generate_product_image_url('Spinach'))
    p3 = Product(farmer_id=farmer.id, name='Cabbage', description='Crisp green cabbage', quantity=40, price=25.0, image_url=generate_product_image_url('Cabbage'))
    db.session.add_all([p1, p2, p3])
    db.session.commit()
    
    # Demo Orders
    o1 = Order(customer_id=customer.id, product_id=p1.id, quantity=5, total_price=150.0, is_new=False)
    db.session.add(o1)
    db.session.commit()

    print('Demo data created: admin/farmer1/cust1 with passwords, and products.')

if __name__ == '__main__':
    with app.app_context():
        db.create_all() 
        create_demo_data()
    app.run(debug=True)