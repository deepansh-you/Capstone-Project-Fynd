from flask import Flask, g
from flask_migrate import Migrate
from db.engine import engine, Base, get_session, init_db
from app.routes import main, admin, auth


def create_app():
    app = Flask(__name__)
    app.config.from_object('config.Config')
    
    init_db()
    
    @app.before_request
    def before_request():
        g.rupee_symbol = '₹'

    Migrate(app, engine)

    app.register_blueprint(main)
    app.register_blueprint(admin, url_prefix='/admin')
    app.register_blueprint(auth)

    Base.metadata.create_all(engine)

    app.config['SECRET_KEY'] = 'secret_key'

    return app
