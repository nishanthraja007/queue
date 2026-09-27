"""
database.py
------------
Database engine + session configuration.

Uses SQLite by default so the assignment runs out-of-the-box with zero
external services. Swap DATABASE_URL to a Postgres connection string
(e.g. "postgresql://user:pass@localhost:5432/hams") for production —
no other code changes are required because we only use portable
SQLAlchemy Core/ORM features.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./hams.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency that yields a DB session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
