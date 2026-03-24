"""Database engine, session factory, and Base declaration."""

import os
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/usag_meets")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI dependency that yields a DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    """Create all tables defined in models."""
    from db import models  # noqa: F401 - ensure models are imported before create_all
    from db import mvp_models  # noqa: F401 - cheer MVP tables

    Base.metadata.create_all(bind=engine)
    _ensure_meets_optional_columns()


def _ensure_meets_optional_columns():
    """
    Backfill columns added after initial deploy for existing databases.
    Safe to run repeatedly.
    """
    inspector = inspect(engine)
    if "meets" not in inspector.get_table_names():
        return

    existing = {c["name"] for c in inspector.get_columns("meets")}
    alters: list[str] = []
    if "facility" not in existing:
        alters.append("ALTER TABLE meets ADD COLUMN facility VARCHAR(255)")

    if not alters:
        return

    with engine.begin() as conn:
        for ddl in alters:
            conn.execute(text(ddl))
