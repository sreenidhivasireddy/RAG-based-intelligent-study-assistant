"""
SQLAlchemy database configuration and Base declarative class.
Provides engine, SessionLocal, and Base for ORM models.

Usage:
    from app.database import Base, SessionLocal, engine
    
    # Define models:
    class MyModel(Base):
        __tablename__ = "my_table"
        ...
    
    # Create tables:
    Base.metadata.create_all(bind=engine)
    
    # Get session:
    db = SessionLocal()
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv

from app.utils.logging import get_logger

# Load environment variables
load_dotenv()

# Initialize logger
logger = get_logger(__name__)

# Build database URL from environment variables (reuse same vars as mysql.py client)
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", 3306))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "rag")

# You can also use a DATABASE_URL env var directly if preferred:
# DATABASE_URL = os.getenv("DATABASE_URL", f"mysql+mysqlconnector://...")
DATABASE_URL = f"mysql+mysqlconnector://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}"

# Create SQLAlchemy engine
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # verify connections before using
    pool_recycle=3600,   # recycle connections after 1 hour
    echo=False,          # set to True to log all SQL statements
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for ORM models
Base = declarative_base()

logger.info(f"SQLAlchemy configured: {MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}")
