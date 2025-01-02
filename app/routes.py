from flask import Blueprint, render_template, request, session, redirect, url_for, flash, g, current_app
from functools import wraps
from db.engine import get_session
from app.models import User, Order, Product, OrderProduct, Category, ShoppingCart
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.orm import joinedload
from sqlalchemy import or_, func
import os, uuid
from flask_mail import Message


main = Blueprint('main', __name__)
admin = Blueprint('admin', __name__)
auth = Blueprint('auth', __name__)


UPLOAD_FOLDER = 'app/static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'admin':
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

@main.before_request
def before_request():
    user_id = session.get('user_id')
    if user_id:
        db_session = get_session()
        products_in_cart = db_session.query(ShoppingCart).filter_by(user_id=user_id).all()
        cart_count = sum(item.cart_quantity for item in products_in_cart)
        g.cart_count = cart_count
    else:
        g.cart_count = 0

@main.before_request
def load_categories():
    db_session = get_session()
    g.categories = db_session.query(Category).all()
    db_session.close()



@admin.route('/')
@admin_required
@login_required
def admin_redirect():
    return redirect(url_for('admin.dashboard'))


@admin.route('/dashboard/')
@admin_required
@login_required
def dashboard():
    session_db = get_session()
    
    total_users = session_db.query(User).count()
    total_sales_query = session_db.query(
        (Product.product_price * OrderProduct.order_product_quantity)
    ).join(OrderProduct).join(Order).filter(Order.order_status == 'confirmed').all()
    
    total_sales = sum(price[0] for price in total_sales_query)
    total_products = session_db.query(Product).count()
    
    pending_orders = session_db.query(Order).filter(Order.order_status == 'pending').count()
    current_user = session_db.query(User).filter(User.user_id == session.get('user_id')).first()
    users = session_db.query(User).all()

    notifications = [
        "New product added.",
        "New user registered.",
        "Order #123 pending."
    ]

    session_db.close()

    return render_template('admin/admin_dashboard.html', total_users=total_users, total_sales=total_sales, pending_orders=pending_orders, users=users,
                           notifications=notifications, current_user=current_user, total_products= total_products, sidebar_hidden=True)
    

@admin.route('/sales/', endpoint='sales_page')
@login_required
@admin_required
def sales_page():
    session_db = get_session()
    total_sales_query = session_db.query(
        (Product.product_price * OrderProduct.order_product_quantity)
    ).join(OrderProduct).join(Order).filter(Order.order_status == 'confirmed').all()
    
    total_sales = sum(price[0] for price in total_sales_query)

    top_products_query = (
        session_db.query(
            Product.product_name,
            func.sum(OrderProduct.order_product_quantity).label('total_quantity')
        )
        .join(OrderProduct)
        .group_by(Product.product_name)
        .order_by(func.sum(OrderProduct.order_product_quantity).desc())
        .all()
    )

    session_db.close()

    return render_template(
        'admin/sales_page.html',
        total_sales=total_sales,
        top_products=top_products_query,
        enumerate=enumerate
    )
    
    
@admin.route('/users/')
@admin_required
@login_required
def users_page():
    db_session = get_session()
    users = db_session.query(User).all()
    return render_template('admin/users_page.html', users=users)


@admin.route('/pending-orders/')
@admin_required
@login_required
def pending_orders_page():
    db_session = get_session()
    pending_orders = db_session.query(Order).filter_by(order_status='pending').all()
    for order in pending_orders:
        db_session.refresh(order)
    return render_template('admin/pending_orders_page.html', pending_orders=pending_orders)


@admin.route('/mark-order-complete/<int:order_id>', methods=['GET', 'POST'])
@admin_required
@login_required
def mark_order_complete(order_id):
    db_session = get_session()
    order = db_session.query(Order).get(order_id)

    if not order:
        flash("Order not found.", "danger")
        return redirect(url_for('admin.pending_orders_page'))

    if order.order_status != 'pending':
        flash("This order cannot be marked as complete because it is not pending.", "danger")
        return redirect(url_for('admin.pending_orders_page'))

    payment_id = generate_payment_id()

    order.order_status = 'confirmed'
    order.payment_status = 'completed'
    order.payment_id = payment_id
    
    try:
        db_session.commit()
        flash(f"Order {order_id} has been marked as complete. Payment ID: {payment_id}", "success")
    except Exception as e:
        db_session.rollback()
        flash(f"An error occurred while updating the order: {str(e)}", "danger")

    return redirect(url_for('admin.pending_orders_page'))


@admin.route('/products/')
@admin_required
@login_required
def products():
    session_db = get_session()
    all_products = session_db.query(Product).options(joinedload(Product.category)).all()
    session_db.close()
    return render_template('admin/products.html', products=all_products)


@admin.route('/products/add/', methods=['GET', 'POST'])
@admin_required
@login_required
def add_product():
    session_db = get_session()
    if request.method == 'POST':
        try:
            product_name = request.form['product_name']
            product_description = request.form['product_description']
            product_price = int(request.form['product_price'])
            product_quantity = int(request.form['product_quantity'])
            category_id = request.form.get('category_id')
            new_category = request.form.get('new_category')

            image = request.files.get('product_image')
            image_filename = None
            image_url = None

            if image and allowed_file(image.filename):
                image_filename = secure_filename(image.filename)
                image.save(os.path.join(UPLOAD_FOLDER, image_filename))
                image_url = image_filename

            if not category_id and not new_category:
                flash('Please select a category or create a new one.', 'danger')
                categories = session_db.query(Category).all()
                session_db.close()
                return render_template('add_product.html', categories=categories)

            if new_category:
                existing_category = session_db.query(Category).filter(Category.category_name == new_category).first()
                if not existing_category:
                    new_cat = Category(category_name=new_category)
                    session_db.add(new_cat)
                    session_db.commit()
                    category_id = new_cat.category_id
                else:
                    category_id = existing_category.category_id

            new_product = Product(
                product_name=product_name,
                product_description=product_description,
                product_price=product_price,
                product_quantity=product_quantity,
                category_id=category_id,
                image_url=image_url
            )
            session_db.add(new_product)
            session_db.commit()

            flash('Product added successfully!', 'success')
            return redirect(url_for('admin.products'))

        except Exception as e:
            session_db.rollback()
            flash(f'Error adding product: {e}', 'danger')
        finally:
            session_db.close()

    categories = session_db.query(Category).all()
    session_db.close()
    return render_template('admin/add_product.html', categories=categories)


@admin.route('/all-orders/')
@admin_required
@login_required
def all_orders_page():
    db_session = get_session()
    orders = db_session.query(Order).all()
    return render_template('admin/admin_orders.html', orders=orders)



@admin.route('/products/update/<int:product_id>/', methods=['GET', 'POST'])
@admin_required
@login_required
def update_product(product_id):
    session_db = get_session()
    product = session_db.query(Product).filter(Product.product_id == product_id).first()

    if not product:
        flash('Product not found.', 'danger')
        return redirect(url_for('admin.products'))

    if request.method == 'POST':
        try:
            product.product_name = request.form['product_name']
            product.product_description = request.form['product_description']
            product.product_price = float(request.form['product_price'])
            product.product_quantity = int(request.form['product_quantity'])
            category_id = int(request.form['category_id'])
            product.category_id = category_id

            image = request.files.get('product_image')
            if image and allowed_file(image.filename):
                image_filename = secure_filename(image.filename)
                image.save(os.path.join(UPLOAD_FOLDER, image_filename))
                product.image_url = image_filename


            session_db.commit()
            flash('Product updated successfully!', 'success')
            return redirect(url_for('admin.products'))

        except Exception as e:
            session_db.rollback()
            flash(f'Error updating product: {e}', 'danger')
        finally:
            session_db.close()

    categories = session_db.query(Category).all()
    session_db.close()
    return render_template('admin/update_product.html', product=product, categories=categories)


@admin.route('/products/mark_in_stock/<int:product_id>/', methods=['POST'])
@admin_required
@login_required
def mark_in_stock(product_id):
    session_db = get_session()
    try:
        product = session_db.query(Product).get(product_id)
        if product and not product.is_deleted:
            product.product_quantity = max(product.product_quantity, 1)
            session_db.commit()
            flash(f'Product "{product.product_name}" marked as In Stock.', 'success')
        else:
            flash('Product not found or has been deleted.', 'danger')
    except Exception as e:
        session_db.rollback()
        flash(f'Error marking product as In Stock: {e}', 'danger')
    finally:
        session_db.close()
    return redirect(url_for('admin.products'))

@admin.route('/products/mark_out_of_stock/<int:product_id>/', methods=['POST'])
@admin_required
@login_required
def mark_out_of_stock(product_id):
    session_db = get_session()
    try:
        product = session_db.query(Product).get(product_id)
        if product and not product.is_deleted:
            product.product_quantity = 0
            session_db.commit()
            flash(f'Product "{product.product_name}" marked as Out of Stock.', 'success')
        else:
            flash('Product not found or has been deleted.', 'danger')
    except Exception as e:
        session_db.rollback()
        flash(f'Error marking product as Out of Stock: {e}', 'danger')
    finally:
        session_db.close()
    return redirect(url_for('admin.products'))



@auth.route('/login/', methods=['POST', 'GET'])
def login():
    session.pop('user_id', None)
    session.pop('role', None)

    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        password = request.form['password']

        session_db = get_session()
        user = session_db.query(User).filter(User.user_email == email).first()

        if user:
            if check_password_hash(user.user_password, password):
                if user.user_status == 'inactive':
                    flash('Your account is deactivated. Please contact support!', 'danger')
                    return redirect(url_for('auth.login'))

                session['user_id'] = user.user_id
                session['role'] = user.user_role

                return redirect(url_for('admin.dashboard') if user.user_role == 'admin' else url_for('main.home'))
            else:
                flash('Invalid credentials. Please try again.', 'danger')
        else:
            flash('No account found with that email.', 'danger')

    return render_template('login.html')



@auth.route('/register/', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email'].lower()
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        name = request.form['name']
        phone_number = request.form.get('phone_number')

        if password != confirm_password:
            flash('Password does not match. Please try again!', 'danger')
            return redirect(url_for('auth.register'))

        session_db = get_session()
        existing_user = session_db.query(User).filter(User.user_email == email.lower()).first()
        if existing_user:
            flash('Email already in use. Please login!', 'danger')
            return redirect(url_for('auth.login'))

        hashed_password = generate_password_hash(password)

        if '@admin.com' in email.lower():
            role = 'admin'
        else:
            role = 'user'

        new_user = User(user_name=name, user_email=email, user_password=hashed_password, user_phone_number=phone_number, user_role=role)

        session_db.add(new_user)
        session_db.commit()
        session_db.close()

        flash("You've successfully registered! Please login again.")
        return redirect(url_for('auth.login'))

    return render_template('register.html')

@auth.route('/logout/')
def logout():
    session.pop('user_id', None)
    session.pop('role', None)
    session.pop('_flashes', None)
    return redirect(url_for('auth.login'))

@admin.route('/user/activate/<int:user_id>', methods=['POST'])
@admin_required
@login_required
def activate_user(user_id):
    session_db = get_session()
    try:
        user = session_db.query(User).get(user_id)
        if user:
            user.user_status = 'active'
            session_db.commit()
            flash('User activated successfully!', 'success')
        else:
            flash('User not found.', 'danger')
    except Exception as e:
        session_db.rollback()
        flash(f'Error activating user: {e}', 'danger')
    finally:
        session_db.close()

    return redirect(url_for('admin.users_page'))


@admin.route('/user/deactivate/<int:user_id>/', methods=['POST'])
@admin_required
@login_required
def deactivate_user(user_id):
    session_db = get_session()
    try:
        user = session_db.query(User).get(user_id)
        if user:
            user.user_status = 'inactive'
            session_db.commit()
            flash('User deactivated successfully!', 'success')
        else:
            flash('User not found.', 'danger')
    except Exception as e:
        session_db.rollback()
        flash(f'Error deactivating user: {e}', 'danger')
    finally:
        session_db.close()
    return redirect(url_for('admin.users_page'))









#<-------------------- USER SIDE APP ----------------->#









@main.route('/')
def home():
    session_db = get_session()
    try:
        products = session_db.query(Product).all()
        categories = session_db.query(Category).all()
        category_products = {}
        for category in categories:
            category_products[category.category_id] = category.products[:8]

    finally:
        session_db.close()

    return render_template('home.html', products=products, categories=categories, category_products=category_products)



@main.route('/product/<int:product_id>/')
def product_details(product_id):
    session = get_session()
    product = session.query(Product).options(joinedload(Product.category)).filter(Product.product_id == product_id).first()

    if not product:
        return "Product not found", 404
    return render_template('product_details.html', product=product)



@main.route('/search/', methods=['GET'])
def search():
    query = request.args.get('query', '').strip()
    results = []
    message = f"Search results for '{query}'"

    if query:
        session = get_session()
        results = session.query(Product).filter(
            (Product.product_name.ilike(f"%{query}%")) |
            (Product.category.has(Category.category_name.ilike(f"%{query}%")))
        ).options(joinedload(Product.category)).all()

        if not results:
            message = f"No results found for '{query}'"

    return render_template('search_results.html', query=query, results=results, message=message)


@main.route('/category/<int:category_id>/')
def category_products(category_id):
    session_db = get_session()
    category = session_db.query(Category).get(category_id)

    if not category:
        flash("Category not found.", "danger")
        return redirect(url_for('main.home'))

    products = session_db.query(Product).filter(Product.category_id == category_id).all()

    return render_template('category_products.html', category=category, products=products)


@main.route('/cart/')
def view_cart():
    user_id = session.get('user_id')

    if not user_id:
        flash("Please log in to view your cart", "warning")
        return redirect(url_for('auth.login'))

    db_session = get_session()
    products_in_cart = db_session.query(ShoppingCart).filter_by(user_id=user_id).all()
    total_price = sum(item.product.product_price * item.cart_quantity for item in products_in_cart)
    cart_count = sum(item.cart_quantity for item in products_in_cart)
    return render_template('cart.html', products_in_cart=products_in_cart, total_price=total_price, cart_count=cart_count)


@main.route('/add_to_cart/<int:product_id>/', methods=['POST'])
def add_to_cart(product_id):
    user_id = session.get('user_id')
    
    if not user_id:
        flash("You must be logged in to add items to the cart.", "warning")
        return redirect(url_for('auth.login'))

    quantity = int(request.form.get('quantity'))

    session_db = get_session()

    product = session_db.query(Product).get(product_id)
    if not product:
        flash("Product not found.", "error")
        return redirect(url_for('main.home'))

    if product.product_quantity < quantity:
        flash("Not enough stock available.", "warning")
        return redirect(url_for('main.product_detail', product_id=product_id))
    
    cart_item = session_db.query(ShoppingCart).filter_by(user_id=user_id, product_id=product_id).first()

    if cart_item:
        cart_item.cart_quantity += quantity
    else:
        cart_item = ShoppingCart(user_id=user_id, product_id=product_id, cart_quantity=quantity)
        session_db.add(cart_item)

    session_db.commit()
    flash("Item added to cart successfully.", "success")
    
    return redirect(url_for('main.view_cart'))



@main.route('/update_cart/<int:cart_id>/', methods=['POST'])
def update_cart(cart_id):
    user_id = session.get('user_id')

    if not user_id:
        flash("Please log in to update your cart", "warning")
        return redirect(url_for('auth.login'))

    action = request.form.get('action')

    db_session = get_session()

    cart_item = db_session.query(ShoppingCart).filter_by(cart_id=cart_id, user_id=user_id).first()

    if action == 'increase':
        cart_item.cart_quantity += 1
    elif action == 'decrease' and cart_item.cart_quantity > 1:
        cart_item.cart_quantity -= 1

    db_session.commit()
    return redirect(url_for('main.view_cart'))


@main.route('/remove_from_cart/<int:cart_id>/', methods=['POST'])
def remove_from_cart(cart_id):
    user_id = session.get('user_id')

    if not user_id:
        flash("Please log in to remove items from your cart", "warning")
        return redirect(url_for('auth.login'))

    db_session = get_session()
    cart_item = db_session.query(ShoppingCart).filter_by(cart_id=cart_id, user_id=user_id).first()

    if cart_item:
        db_session.delete(cart_item)
        db_session.commit()

    return redirect(url_for('main.view_cart'))

def get_cart_count(user_id):
    session = get_session()
    user_cart = session.query(ShoppingCart).filter(ShoppingCart.user_id == user_id).all()
    return len(user_cart)


@main.route('/checkout/', methods=['GET', 'POST'])
def checkout():
    user_id = session.get('user_id')

    if not user_id:
        flash("Please log in to proceed with checkout", "warning")
        return redirect(url_for('auth.login'))

    db_session = get_session()
    user = db_session.query(User).filter_by(user_id=user_id).first()

    if request.method == 'POST':
        user_name = request.form.get('user_name')
        user_phone_number = request.form.get('user_phone_number')
        user_address = request.form.get('user_address')
        user_email = request.form.get('user_email')

        session['user_name'] = user_name
        session['user_phone_number'] = user_phone_number
        session['user_address'] = user_address
        session['user_email'] = user_email

        flash("Your details have been saved. Proceed to payment.", "success")

        return redirect(url_for('main.payment'))

    user_details = {
        'user_name': user.user_name if user else '',
        'user_phone_number': user.user_phone_number if user else '',
        'user_address': user.user_address if user else '',
        'user_email': user.user_email if user else '',
    }

    return render_template('checkout.html', user_details=user_details)


def generate_payment_id():
    return str(uuid.uuid4())


@main.route('/payment/', methods=['GET', 'POST'])
def payment():
    user_id = session.get('user_id')

    if not user_id:
        flash("Please log in to proceed to payment.", "warning")
        return redirect(url_for('auth.login'))

    db_session = get_session()

    products_in_cart = db_session.query(ShoppingCart).filter_by(user_id=user_id).all()
    total_price = sum(item.product.product_price * item.cart_quantity for item in products_in_cart)

    if request.method == 'GET':
        pending_order = db_session.query(Order).filter_by(user_id=user_id, order_status='pending').first()
        if not pending_order:
            new_order = Order(
                user_id=user_id,
                order_status='pending',
                payment_status='pending',
                order_total_amount=total_price
            )
            db_session.add(new_order)
            db_session.commit()

            for item in products_in_cart:
                order_product = OrderProduct(
                    order_id=new_order.order_id,
                    product_id=item.product_id,
                    order_product_quantity=item.cart_quantity,
                    order_product_price=item.product.product_price * item.cart_quantity
                )
                db_session.add(order_product)

            db_session.commit()

    if request.method == 'POST':
        user_name = request.form.get('user_name', session.get('user_name'))
        user_phone_number = request.form.get('user_phone_number', session.get('user_phone_number'))
        user_address = request.form.get('user_address', session.get('user_address'))
        user_email = request.form.get('user_email', session.get('user_email'))

        session['user_name'] = user_name
        session['user_phone_number'] = user_phone_number
        session['user_address'] = user_address
        session['user_email'] = user_email

        card_number = request.form.get('card_number')
        expiry_date = request.form.get('expiry_date')
        cvv = request.form.get('cvv')

        if not card_number or not expiry_date or not cvv:
            flash("Please fill in all payment details.", "danger")
            return redirect(url_for('main.payment'))

        payment_id = generate_payment_id()

        order = db_session.query(Order).filter_by(user_id=user_id, order_status='pending').first()
        if order:
            order.order_status = 'confirmed'
            order.payment_status = 'completed'
            order.payment_id = payment_id
            db_session.commit()

            for item in products_in_cart:
                product = db_session.query(Product).get(item.product_id)
                if product and product.product_quantity >= item.cart_quantity:
                    product.product_quantity -= item.cart_quantity
                else:
                    flash(f"Not enough stock available for product: {item.product.product_name}. Please adjust your order.", "danger")
                    db_session.rollback()
                    return redirect(url_for('main.payment'))

            db_session.commit()

            db_session.query(ShoppingCart).filter_by(user_id=user_id).delete()
            db_session.commit()

            send_order_confirmation_email(user_email, order)

            flash("Your payment was successful! Your order has been confirmed.", "success")
            return redirect(url_for('main.order_confirmation_page'))

    return render_template('payment.html', products_in_cart=products_in_cart, total_price=total_price)



def send_order_confirmation_email(user_email, order):

    db_session = get_session()
    order_products = db_session.query(OrderProduct).filter_by(order_id=order.order_id).all()

    email_body = f"Your order (ID: {order.order_id}) has been successfully placed. We will notify you once it's shipped.\n\n"
    email_body += "Order Details:\n"

    for order_product in order_products:
        product = order_product.product  
        email_body += f"- {product.product_name} x {order_product.order_product_quantity}\n"

    msg = Message(
        'Order Confirmation - PrimeLane',
        recipients=[user_email],
        body=email_body
    )

    try:
        current_app.extensions['mail'].send(msg)
    except Exception as e:
        print(f"An error occurred while sending the email: {e}")



@main.route('/order-confirmation-page/')
def order_confirmation_page():
    user_id = session.get('user_id')

    if not user_id:
        flash("Please log in to view your order.", "warning")
        return redirect(url_for('auth.login'))

    db_session = get_session()

    products_in_cart = db_session.query(ShoppingCart).options(joinedload(ShoppingCart.product)).filter_by(user_id=user_id).all()

    total_price = 0
    for item in products_in_cart:
        if item.product:
            total_price += item.product.product_price * item.cart_quantity
        else:
            print(f"Warning: Missing product for cart item {item.cart_id}")

    return render_template('order_confirmation.html', products_in_cart=products_in_cart, total_price=total_price)


@main.route('/profile/', methods=['GET', 'POST'])
def profile():
    user_id = session.get('user_id')

    db_session = get_session()
    user = db_session.query(User).get(user_id)

    if request.method == 'POST':
        user_name = request.form['user_name']
        user_email = request.form['user_email']
        user_phone_number = request.form['user_phone_number']
        user_address = request.form['user_address']
        password = request.form['password']

        profile_updated = False
        
        if user.user_name != user_name:
            user.user_name = user_name
            profile_updated = True
        if user.user_email != user_email:
            user.user_email = user_email
            profile_updated = True
        if user.user_phone_number != user_phone_number:
            user.user_phone_number = user_phone_number
            profile_updated = True
        if user.user_address != user_address:
            user.user_address = user_address
            profile_updated = True
        if password:
            user.password = generate_password_hash(password)
            flash('Password changed successfully', 'success')
        if profile_updated:
            db_session.commit()
            flash('Profile updated successfully', 'success')
            session['profile_updated'] = True
        else:
            db_session.commit()

        return redirect(url_for('main.profile'))

    if 'profile_updated' in session:
        session.pop('profile_updated', None)

    return render_template('profile.html', user=user)


@main.route('/order-history/', methods=['GET'])
def order_history():
    user_id = session.get('user_id')
    
    if not user_id:
        flash("You need to be logged in to view your order history.", 'danger')
        return redirect(url_for('login'))
    
    db_session = get_session()
    orders = db_session.query(Order).filter_by(user_id=user_id, payment_status='completed').options(
        joinedload(Order.products).joinedload(OrderProduct.product)
    ).all()

    if not orders:
        flash("You have no order history with completed payments.", 'info')
    
    db_session.close()
    
    return render_template('order_history.html', orders=orders)