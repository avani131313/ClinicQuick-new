"""Database access. Works on Tiger Cloud (TimescaleDB + pgvector) and on plain Postgres."""
from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from .config import DATABASE_URL

log = logging.getLogger("prelude.db")
DB_DIR = Path(__file__).resolve().parent.parent / "db"

_pool: ConnectionPool | None = None
FEATURES = {"timescaledb": False, "vector": False}


def pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(DATABASE_URL, min_size=1, max_size=8, kwargs={"row_factory": dict_row}, open=True)
    return _pool


@contextmanager
def conn():
    with pool().connection() as c:
        yield c


def q(sql: str, params=None) -> list[dict]:
    with conn() as c:
        cur = c.execute(sql, params)
        return cur.fetchall() if cur.description else []


def q1(sql: str, params=None) -> dict | None:
    rows = q(sql, params)
    return rows[0] if rows else None


def exe(sql: str, params=None) -> None:
    with conn() as c:
        c.execute(sql, params)


def close() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


def J(v):
    """Wrap a Python object for a jsonb parameter."""
    return Jsonb(v)


def _try_extension(c, name: str) -> bool:
    try:
        avail = c.execute("SELECT 1 FROM pg_available_extensions WHERE name = %s", (name,)).fetchone()
        if not avail:
            return False
        c.execute(f"CREATE EXTENSION IF NOT EXISTS {name}")
        return True
    except psycopg.Error as e:
        log.warning("extension %s unavailable: %s", name, e)
        c.rollback()
        return False


def init_schema() -> dict:
    """Create tables, then switch on Tiger features if the extensions exist."""
    with psycopg.connect(DATABASE_URL, autocommit=True) as c:
        c.execute((DB_DIR / "schema.sql").read_text())
        FEATURES["timescaledb"] = _try_extension(c, "timescaledb")
        FEATURES["vector"] = _try_extension(c, "vector")
        if FEATURES["timescaledb"] and FEATURES["vector"]:
            exists = c.execute("SELECT 1 FROM pg_class WHERE relname = 'daily_obs'").fetchone()
            if not exists:
                for stmt in _statements((DB_DIR / "tiger.sql").read_text()):
                    c.execute(stmt)
        elif FEATURES["timescaledb"]:
            # hypertables + cagg without the vector part
            exists = c.execute("SELECT 1 FROM pg_class WHERE relname = 'daily_obs'").fetchone()
            if not exists:
                for stmt in _statements((DB_DIR / "tiger.sql").read_text()):
                    if "vector" in stmt or "embedding" in stmt:
                        continue
                    c.execute(stmt)
        else:
            c.execute((DB_DIR / "plain_fallback.sql").read_text())
    log.info("schema ready, features=%s", FEATURES)
    return dict(FEATURES)


def detect_features() -> dict:
    rows = q("SELECT extname FROM pg_extension WHERE extname IN ('timescaledb','vector')")
    names = {r["extname"] for r in rows}
    FEATURES["timescaledb"] = "timescaledb" in names
    FEATURES["vector"] = "vector" in names and bool(
        q1("SELECT 1 FROM information_schema.columns WHERE table_name='memory_chunks' AND column_name='embedding'"))
    return dict(FEATURES)


def refresh_daily_obs() -> None:
    """After bulk-loading old data, materialise the continuous aggregate immediately."""
    if not FEATURES["timescaledb"]:
        return
    with psycopg.connect(DATABASE_URL, autocommit=True) as c:
        c.execute("CALL refresh_continuous_aggregate('daily_obs', NULL, NULL)")


def _statements(sql: str) -> list[str]:
    lines = [l for l in sql.splitlines() if not l.strip().startswith("--")]
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]
