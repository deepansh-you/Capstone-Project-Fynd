from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime
from datetime import datetime
import pytz
from db.engine import Base
from sqlalchemy.orm import relationship
from werkzeug.security import check_password_hash, generate_password_hash

def get_ist_time():
    utc_time = datetime.now(pytz.utc)
    ist_time = utc_time.astimezone(pytz.timezone('Asia/Kolkata'))
    return ist_time

class User(Base):
    __tablename__ = 'users'
    user_id = Column(Integer, primary_key=True, autoincrement=True)
    user_name = Column(String(100), nullable=False)
    user_email = Column(String(100), nullable=False, unique=True)
    user_password = Column(String(100), nullable=False)
    user_phone_number = Column(String(100), nullable=False)
    user_address = Column(String(200))
    user_role = Column(String(50), default='user', nullable = False)
    
    orders = relationship('Order', backref='user')
    shopping_carts = relationship('ShoppingCart')
    @property
    def password(self):
        raise ArithmeticError("Password is not a readable attribute")
    
    @password.setter
    def password(self, password):
        self.user_password = generate_password_hash(password)
        
    def verify_password(self, password):
        return check_password_hash(self.user_password, password)


class Category(Base):
    __tablename__ = 'categories'
    category_id = Column(Integer, primary_key=True, autoincrement=True)
    category_name = Column(String(100), nullable=False, unique=True)
    category_description = Column(String(500))
    
    products = relationship('Product', backref='category')


class Product(Base):
    __tablename__ = 'products'
    product_id = Column(Integer, primary_key=True, autoincrement=True)
    product_name = Column(String(100), nullable=False)
    product_description = Column(String(500), nullable=True)
    product_price = Column(Float, nullable=False)
    product_quantity = Column(Integer, nullable=False)
    category_id = Column(Integer, ForeignKey('categories.category_id'))


class Order(Base):
    __tablename__ = 'orders'
    order_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.user_id'))
    order_date = Column(DateTime, default=get_ist_time)
    order_status = Column(String, nullable=False)
    order_total_amount = Column(Float, nullable=False)
    
    products = relationship('OrderProduct', backref='order')


class OrderProduct(Base):
    __tablename__ = 'order_products'
    order_id = Column(Integer, ForeignKey('orders.order_id'), primary_key=True)
    product_id = Column(Integer, ForeignKey('products.product_id'), primary_key=True)
    order_product_quantity = Column(Integer, nullable=False)
    order_product_price = Column(Float, nullable=False)


class ShoppingCart(Base):
    __tablename__ = 'shopping_carts'
    cart_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.user_id'))
    product_id = Column(Integer, ForeignKey('products.product_id'))
    cart_quantity = Column(Integer, default=1)

    user = relationship("User", backref="cart_user")
    product = relationship("Product", backref="shopping_carts")
