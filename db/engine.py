from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

DATABASE_URI = 'sqlite:///database.db'

engine = create_engine(DATABASE_URI, echo=True)

Base = declarative_base()

Session = sessionmaker(bind=engine)

def init_db():
    """Create all tables in the database (if they don't exist already)."""
    Base.metadata.create_all(engine)

def get_session():
    """Return a new session for database operations."""
    return Session()

