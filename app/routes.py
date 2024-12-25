from flask import Blueprint, render_template, request, session, redirect, url_for, flash
from functools import wraps
from db.engine import get_session
from app.models import User, Order, Product, OrderProduct, Category, ShoppingCart
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.orm import joinedload
from sqlalchemy import or_
import os

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

            # Handle image upload
            if image and allowed_file(image.filename):
                image_filename = secure_filename(image.filename)
                image.save(os.path.join(UPLOAD_FOLDER, image_filename))  # Save only in 'uploads' folder
                image_url = image_filename  # Save relative path

            # Ensure category is selected or created
            if not category_id and not new_category:
                flash('Please select a category or create a new one.', 'danger')
                categories = session_db.query(Category).all()
                session_db.close()
                return render_template('add_product.html', categories=categories)

            # Add new category if needed
            if new_category:
                existing_category = session_db.query(Category).filter(Category.category_name == new_category).first()
                if not existing_category:
                    new_cat = Category(category_name=new_category)
                    session_db.add(new_cat)
                    session_db.commit()
                    category_id = new_cat.category_id
                else:
                    category_id = existing_category.category_id

            # Create and add new product
            new_product = Product(
                product_name=product_name,
                product_description=product_description,
                product_price=product_price,
                product_quantity=product_quantity,
                category_id=category_id,
                image_url=image_url  # Corrected image URL
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

    # Query all categories for selection
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

            # Handle image upload for product update
            image = request.files.get('product_image')
            if image and allowed_file(image.filename):
                image_filename = secure_filename(image.filename)
                image.save(os.path.join(UPLOAD_FOLDER, image_filename))  # Save the image in the uploads folder
                product.image_url = image_filename  # Save the relative path (no 'static/' prefix)


            session_db.commit()  # Commit changes
            flash('Product updated successfully!', 'success')
            return redirect(url_for('admin.products'))

        except Exception as e:
            session_db.rollback()  # Rollback if any error occurs
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

    finally:
        session_db.close()

    return render_template('home.html', products=products)



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
