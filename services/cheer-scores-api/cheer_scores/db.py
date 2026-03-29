from __future__ import annotations

import os
from functools import lru_cache

from sqlalchemy import create_engine, inspect, text


@lru_cache(maxsize=1)
def engine():
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return create_engine(url, pool_pre_ping=True, pool_size=2, max_overflow=3)


def fetch_all(sql: str, params: dict | None = None) -> list[dict]:
    with engine().connect() as conn:
        res = conn.execute(text(sql), params or {})
        cols = list(res.keys())
        return [dict(zip(cols, row)) for row in res.fetchall()]


def fetch_one(sql: str, params: dict | None = None) -> dict | None:
    rows = fetch_all(sql, params=params)
    return rows[0] if rows else None


def ensure_cheer_mvp_meet_datetime_columns() -> None:
    """Idempotent Postgres DDL for ``starts_at`` / ``ends_at`` on ``cheer_mvp_meets``."""
    eng = engine()
    if eng.dialect.name not in ("postgresql", "postgres"):
        return
    insp = inspect(eng)
    if "cheer_mvp_meets" not in insp.get_table_names():
        return
    existing = {c["name"] for c in insp.get_columns("cheer_mvp_meets")}
    stmts: list[str] = []
    if "starts_at" not in existing:
        stmts.append("ALTER TABLE cheer_mvp_meets ADD COLUMN starts_at TIMESTAMPTZ")
    if "ends_at" not in existing:
        stmts.append("ALTER TABLE cheer_mvp_meets ADD COLUMN ends_at TIMESTAMPTZ")
    if not stmts:
        return
    with eng.begin() as conn:
        for ddl in stmts:
            conn.execute(text(ddl))

