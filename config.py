import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'your_secret_key')
    SQLALCHEMY_DATABASE_URI = 'sqlite:///app.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    BABEL_DEFAULT_LOCALE = 'en_IN'
    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 465
    MAIL_USE_TLS = False
    MAIL_USE_SSL = True
    MAIL_USERNAME = 'dpanshyou@gmail.com'
    MAIL_PASSWORD = 'ahktorkxptvojdrn'
    MAIL_DEFAULT_SENDER = 'dpanshyou@gmail.com'
    CASHFREE_APP_ID = 'TEST10400989cc914104df4af9926ff098900401'
    CASHFREE_SECRET_KEY = 'cfsk_ma_test_ba02bb37d277c5b4019c0432569fceec_2d081f0f'