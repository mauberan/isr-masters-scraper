# db/connection.py
#
# Manages the PostgreSQL connection pool for isrscraper.
#
# Why a pool?
#   Opening a database connection is expensive (~5-50ms, OS + auth overhead).
#   A pool keeps connections open and reuses them across calls, paying that
#   cost once at startup rather than on every write operation.
#
# Why a module-level singleton?
#   The pool is created once when first accessed and shared for the lifetime
#   of the process. This is the standard pattern for long-running scrapers
#   and pipeline workers.

import os
import psycopg
from psycopg_pool import ConnectionPool

# Read from environment so the same code works locally and in production.
# Local default assumes a Postgres database named 'isr_masters' on localhost.
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://isr:isr@localhost:5432/isr_masters"
)

# Module-level pool instance — None until first call to get_pool()
_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    """
    Returns the shared connection pool, creating it on first call.

    min_size=1 — always keep at least one connection open.
    max_size=5 — never open more than 5 simultaneous connections.
                 For a scraper this is generous; a single connection
                 would work, but 5 leaves room if you parallelize later.
    """
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            DATABASE_URL,
            min_size=1,
            max_size=5,
            kwargs={"autocommit": False}  # explicit transaction control
        )
    return _pool


def get_conn():
    """
    Context manager that borrows a connection from the pool.

    Usage:
        with get_conn() as conn:
            conn.execute("SELECT ...")

    The connection is automatically returned to the pool when the
    'with' block exits — whether normally or via exception.
    Uncommitted transactions are rolled back on exception.
    """
    return get_pool().connection()


def close_pool() -> None:
    """
    Closes all connections in the pool.
    Call this on clean shutdown (e.g. end of scraper run).
    """
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


# =============================================================================
# Quick connection test — run this file directly to verify setup:
#   python -m db.connection
# =============================================================================
if __name__ == "__main__":
    print(f"Connecting to: {DATABASE_URL}")
    try:
        with get_conn() as conn:
            row = conn.execute("SELECT version()").fetchone()
            print(f"Connected: {row[0]}")
            row = conn.execute(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            ).fetchone()
            print(f"Tables in public schema: {row[0]}")
    except Exception as e:
        print(f"Connection failed: {e}")
    finally:
        close_pool()