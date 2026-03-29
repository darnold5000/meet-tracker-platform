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
    _ensure_cheer_mvp_audit_columns()
    _ensure_cheer_mvp_performance_score_columns()
    _ensure_cheer_mvp_meet_start_end_datetimes()
    _ensure_cheer_mvp_meet_hub_results_snapshot_hash()
    _ensure_cheer_mvp_performance_source_row_hash()


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


def _ensure_cheer_mvp_audit_columns() -> None:
    """Add ``created_at`` / ``updated_at`` to cheer MVP tables (Postgres ``TIMESTAMPTZ``)."""
    inspector = inspect(engine)
    dialect = engine.dialect.name
    if dialect not in ("postgresql", "postgres"):
        return
    for table in (
        "cheer_mvp_meets",
        "cheer_mvp_sessions",
        "cheer_mvp_teams",
        "cheer_mvp_performances",
    ):
        if table not in inspector.get_table_names():
            continue
        existing = {c["name"] for c in inspector.get_columns(table)}
        alters: list[str] = []
        if "created_at" not in existing:
            alters.append(
                f"ALTER TABLE {table} ADD COLUMN created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
            )
        if "updated_at" not in existing:
            alters.append(
                f"ALTER TABLE {table} ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
            )
        if not alters:
            continue
        with engine.begin() as conn:
            for ddl in alters:
                conn.execute(text(ddl))


def _ensure_cheer_mvp_meet_start_end_datetimes() -> None:
    """Add ``starts_at`` / ``ends_at`` on meets (Varsity schedule card datetimes)."""
    inspector = inspect(engine)
    dialect = engine.dialect.name
    if dialect not in ("postgresql", "postgres"):
        return
    if "cheer_mvp_meets" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("cheer_mvp_meets")}
    alters: list[str] = []
    if "starts_at" not in existing:
        alters.append("ALTER TABLE cheer_mvp_meets ADD COLUMN starts_at TIMESTAMPTZ")
    if "ends_at" not in existing:
        alters.append("ALTER TABLE cheer_mvp_meets ADD COLUMN ends_at TIMESTAMPTZ")
    if not alters:
        return
    with engine.begin() as conn:
        for ddl in alters:
            conn.execute(text(ddl))


def _ensure_cheer_mvp_meet_hub_results_snapshot_hash() -> None:
    """SHA-256 of canonical hub results payload; unchanged → skip delete/reinsert on sync."""
    inspector = inspect(engine)
    dialect = engine.dialect.name
    if dialect not in ("postgresql", "postgres"):
        return
    if "cheer_mvp_meets" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("cheer_mvp_meets")}
    if "hub_results_snapshot_hash" in existing:
        return
    with engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE cheer_mvp_meets ADD COLUMN hub_results_snapshot_hash VARCHAR(64)"
            )
        )


def _ensure_cheer_mvp_performance_score_columns() -> None:
    """Add ``raw_score`` / ``performance_score`` on performances (Varsity RS/PS); ES stays ``final_score``."""
    inspector = inspect(engine)
    dialect = engine.dialect.name
    if dialect not in ("postgresql", "postgres"):
        return
    if "cheer_mvp_performances" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("cheer_mvp_performances")}
    alters: list[str] = []
    if "raw_score" not in existing:
        alters.append(
            "ALTER TABLE cheer_mvp_performances ADD COLUMN raw_score DOUBLE PRECISION"
        )
    if "performance_score" not in existing:
        alters.append(
            "ALTER TABLE cheer_mvp_performances ADD COLUMN performance_score DOUBLE PRECISION"
        )
    if not alters:
        return
    with engine.begin() as conn:
        for ddl in alters:
            conn.execute(text(ddl))


def _ensure_cheer_mvp_performance_source_row_hash() -> None:
    """Add ``source_row_hash`` and unique index for idempotent performance upserts."""
    inspector = inspect(engine)
    dialect = engine.dialect.name
    if dialect not in ("postgresql", "postgres"):
        return
    if "cheer_mvp_performances" not in inspector.get_table_names():
        return

    existing = {c["name"] for c in inspector.get_columns("cheer_mvp_performances")}
    with engine.begin() as conn:
        if "source_row_hash" not in existing:
            conn.execute(
                text(
                    "ALTER TABLE cheer_mvp_performances ADD COLUMN source_row_hash VARCHAR(64)"
                )
            )
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_cheer_mvp_perf_source_row_hash "
                "ON cheer_mvp_performances (source_row_hash) "
                "WHERE source_row_hash IS NOT NULL"
            )
        )
