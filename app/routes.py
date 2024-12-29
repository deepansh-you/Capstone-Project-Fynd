from flask import Blueprint, render_template, request, session, redirect, url_for, flash, g, current_app
from functools import wraps
from db.engine import get_session
from app.models import User, Order, Product, OrderProduct, Category, ShoppingCart
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.orm import joinedload
from sqlalchemy import or_
import os
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
    total_sales_query = session_db.query(Product.product_price).join(OrderProduct).join(Order).filter(Order.order_status == 'completed').all()
    total_sales = sum(price[0] for price in total_sales_query)
    pending_orders = session_db.query(Order).filter(Order.order_status == 'pending').count()
    current_user = session_db.query(User).filter(User.user_id == session.get('user_id')).first()
    users = session_db.query(User).all()

    notifications = [
        "New product added.",
        "New user registered.",
        "Order #123 pending."
    ]

    session_db.close()

    return render_template('admin_dashboard.html', 
                           total_users=total_users, 
                           total_sales=total_sales, 
                           pending_orders=pending_orders,
                           users=users,
                           notifications=notifications,
                           current_user=current_user)

@admin.route('/user/delete/<int:user_id>', methods=['POST'])
@admin_required
@login_required
def delete_user(user_id):
    session_db = get_session()
    try:
        user = session_db.query(User).get(user_id)
        if user:
            session_db.delete(user)
            session_db.commit()
            flash('User deleted successfully!', 'success')
        else:
            flash('User not found.', 'danger')
    except Exception as e:
        session_db.rollback()
        flash(f'Error deleting user: {e}', 'danger')
    finally:
        session_db.close()

    return redirect(url_for('admin.dashboard'))


@admin.route('/user/edit/<int:user_id>', methods=['GET', 'POST'])
@admin_required
@login_required
def edit_user(user_id):
    session_db = get_session()
    user = session_db.query(User).get(user_id)

    if request.method == 'POST':
        try:
            user.user_name = request.form['user_name']
            user.user_email = request.form['user_email']
            user.user_role = request.form['user_role']
            user.user_status = request.form['user_status']
            session_db.commit()
            flash('User details updated successfully!', 'success')
            return redirect(url_for('admin.dashboard'))
        except Exception as e:
            session_db.rollback()
            flash(f'Error updating user: {e}', 'danger')
        finally:
            session_db.close()

    session_db.close()
    return render_template('edit_user.html', user=user)



@admin.route('/products/')
@admin_required
@login_required
def products():
    session_db = get_session()
    all_products = session_db.query(Product).options(joinedload(Product.category)).all()
    session_db.close()
    return render_template('products.html', products=all_products)


@admin.route('/products/add', methods=['GET', 'POST'])
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
    return render_template('add_product.html', categories=categories)





@admin.route('/products/update/<int:product_id>', methods=['GET', 'POST'])
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
    return render_template('update_product.html', product=product, categories=categories)



@admin.route('/products/delete/<int:product_id>', methods=['POST'])
@admin_required
@login_required
def delete_product(product_id):
    session_db = get_session()
    try:
        product = session_db.query(Product).get(product_id)
        if product:
            session_db.delete(product)
            session_db.commit()
            flash('Product deleted successfully!', 'success')
        else:
            flash('Product not found.', 'danger')
    except Exception as e:
        session_db.rollback()
        flash(f'Error deleting product: {e}', 'danger')
    finally:
        session_db.close()
    
    return redirect(url_for('admin.products'))


@auth.route('/login/', methods=['POST', 'GET'])
def login():
    session.pop('user_id', None)
    session.pop('role', None)

    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        session_db = get_session()
        user = session_db.query(User).filter(User.user_email == email.lower()).first()

        if user and check_password_hash(user.user_password, password):
            if user.user_status == 'inactive':
                flash('Your account is deactivated. Please contact the admin.', 'danger')
                return redirect(url_for('auth.login'))

            session['user_id'] = user.user_id
            session['role'] = user.user_role

            if user.user_role == 'admin':
                return redirect(url_for('admin.dashboard'))
            else:
                return redirect(url_for('main.home'))
        else:
            flash('Invalid credentials. Please try again.', 'danger')

    return render_template('login.html')


@auth.route('/register', methods=['GET', 'POST'])
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

@auth.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('role', None)
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

    return redirect(url_for('admin.dashboard'))

@admin.route('/user/deactivate/<int:user_id>', methods=['POST'])
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

    return redirect(url_for('admin.dashboard'))









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



@main.route('/search', methods=['GET'])
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
    session_db = get_session() # Using Flask-SQLAlchemy session

    # Fetch the category by ID
    category = session_db.query(Category).get(category_id)

    # If category doesn't exist, flash a message and redirect to home
    if not category:
        flash("Category not found.", "danger")
        return redirect(url_for('main.home'))

    # Fetch all products in this category
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


@main.route('/remove_from_cart/<int:cart_id>', methods=['POST'])
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
        # Get user details from the form
        user_name = request.form.get('user_name')
        user_phone_number = request.form.get('user_phone_number')
        user_address = request.form.get('user_address')
        user_email = request.form.get('user_email')

        # Store these details in session or database if needed
        session['user_name'] = user_name
        session['user_phone_number'] = user_phone_number
        session['user_address'] = user_address
        session['user_email'] = user_email

        # Flash success message
        flash("Your details have been saved. Proceed to payment.", "success")

        # Redirect to the payment page
        return redirect(url_for('main.payment'))

    # Pre-fill form with existing user data (if available)
    user_details = {
        'user_name': user.user_name if user else '',
        'user_phone_number': user.user_phone_number if user else '',
        'user_address': user.user_address if user else '',
        'user_email': user.user_email if user else '',
    }

    return render_template('checkout.html', user_details=user_details)


@main.route('/payment/', methods=['GET', 'POST'])
def payment():
    user_id = session.get('user_id')
    
    # Ensure the user is logged in before proceeding
    if not user_id:
        flash("Please log in to proceed to payment.", "warning")
        return redirect(url_for('auth.login'))

    db_session = get_session()
    
    # Fetch the products in the user's shopping cart
    products_in_cart = db_session.query(ShoppingCart).filter_by(user_id=user_id).all()
    total_price = sum(item.product.product_price * item.cart_quantity for item in products_in_cart)

    # Handle the POST request when the user submits the payment form
    if request.method == 'POST':
        # Extract user data (from session or from the form if it's not stored)
        user_name = request.form.get('user_name', session.get('user_name'))
        user_phone_number = request.form.get('user_phone_number', session.get('user_phone_number'))
        user_address = request.form.get('user_address', session.get('user_address'))
        user_email = request.form.get('user_email', session.get('user_email'))

        # Store or update user data in session
        session['user_name'] = user_name
        session['user_phone_number'] = user_phone_number
        session['user_address'] = user_address
        session['user_email'] = user_email

        # Validate card details
        card_number = request.form.get('card_number')
        expiry_date = request.form.get('expiry_date')
        cvv = request.form.get('cvv')

        if not card_number or not expiry_date or not cvv:
            flash("Please fill in all payment details.", "danger")
            return redirect(url_for('main.payment'))

        # Create a new order record
        order = Order(user_id=user_id, order_status='confirmed', order_total_amount=total_price)
        db_session.add(order)
        db_session.commit()

        # Add each product in the cart to the order
        for item in products_in_cart:
            product = item.product
            order_product = OrderProduct(
                order_id=order.order_id,
                product_id=item.product_id,
                order_product_quantity=item.cart_quantity,
                order_product_price=product.product_price
            )
            db_session.add(order_product)

        # Clear the user's shopping cart
        db_session.query(ShoppingCart).filter_by(user_id=user_id).delete()
        db_session.commit()

        # Send the order confirmation email
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



@main.route('/order-confirmation-page')
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
            session['profile_updated'] = True  # Set session flag for profile update
        else:
            db_session.commit()

        return redirect(url_for('main.profile'))

    # Remove the flag once it's used to show flash message
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

    orders = db_session.query(Order).filter_by(user_id=user_id).options(
        joinedload(Order.products).joinedload(OrderProduct.product)
    ).all()

    if not orders:
        flash("You have no order history.", 'info')
    db_session.close()
    return render_template('order_history.html', orders=orders)