from flask import Blueprint, render_template, request, session, redirect, url_for, flash
from functools import wraps
from db.engine import get_session
from app.models import User, Order, Product, OrderProduct
from werkzeug.security import generate_password_hash, check_password_hash

main = Blueprint('main', __name__)
admin = Blueprint('admin', __name__)
auth = Blueprint('auth', __name__)


@main.route('/')
def home():
    return "Hello!"

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

@admin.route('/dashboard/')
@admin_required
@login_required
def dashboard():
    session = get_session()
    total_users = session.query(User).count()
    total_sales = session.query(Product.product_price).join(OrderProduct).join(Order).filter(Order.order_status == 'completed').all()
    total_sales = sum(price[0] for price in total_sales)
    pending_orders = session.query(Order).filter(Order.order_status == 'pending').count()

    session.close()
    return render_template('admin_dashboard.html', total_users=total_users, total_sales=total_sales, pending_orders=pending_orders)

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
            session['user_id'] = user.user_id
            session['role'] = user.user_role

            if user.user_role == 'admin':
                return redirect(url_for('admin.dashboard'))
            else:
                return redirect(url_for('main.home'))
        else:
            flash('Invalid credentials. Please try again.')

    return render_template('login.html')


@auth.route('/register', methods=['GET', 'POST'])
def register():
    if request.method=='POST':
        email = request.form['email'].lower()
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        name = request.form['name']
        phone_number = request.form.get('phone_number')
        
        if password!=confirm_password:
            flash('Password does not match. Please try again!', 'Danger!')
            return redirect(url_for('auth.register'))
        session_db=get_session()
        existing_user=session_db.query(User).filter(User.user_email==email.lower()).first()
        if existing_user:
            flash('Email already in use. Please login!', 'Danger!')
            return redirect(url_for('auth.login'))
        
        hashed_password=generate_password_hash(password)
        
        if '@admin.com' in email.lower():
            role = 'admin'
        else:
            role = 'user'
            
        new_user=User(user_name=name, user_email=email, user_password=hashed_password, user_phone_number=phone_number, user_role = role)
        
        session_db.add(new_user)
        session_db.commit()
        session_db.close()
        
        flash("You've successfully registered! Please login again.")
        return redirect(url_for('auth.login'))

    return render_template('register.html')




@auth.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('auth.login'))