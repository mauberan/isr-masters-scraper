# db/migrate.py
#
# Minimal migration runner for isr-masters-scraper.
#
# Applies any unapplied migrations from the migrations/ folder,
# in filename order. Skips migrations already recorded in schema_migrations.
#
# Usage:
#   python -m db.migrate
#
# Design notes:
#   - No external dependencies — pure psycopg3
#   - Each migration runs in its own transaction
#   - If a migration fails, it rolls back and stops — later migrations
#     are NOT applied. Fix the failing migration and re-run.
#   - Migration filenames must sort correctly — use zero-padded numbers:
#     001_..., 002_..., 003_... not 1_..., 2_..., 10_...

import os
import sys
from pathlib import Path
from db.connection import get_conn

MIGRATIONS_DIR = Path(__file__).parent.parent / "migrations"


def get_applied_migrations(conn) -> set[str]:
    """Returns the set of migration versions already in schema_migrations."""
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    return {row[0] for row in rows}


def get_pending_migrations(applied: set[str]) -> list[Path]:
    """
    Returns migration files that haven't been applied yet, in order.
    Skips files that don't end in .sql or start with a dot.
    """
    all_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    return [f for f in all_files if not f.stem.startswith("util_") and f.stem not in applied]


def run_migration(conn, filepath: Path) -> None:
    """
    Executes a single migration file within the current connection.
    The caller is responsible for transaction management.
    """
    sql = filepath.read_text(encoding="utf-8")
    conn.execute(sql)


def migrate() -> None:
    """
    Main entry point. Applies all pending migrations in order.
    """
    with get_conn() as conn:
        applied = get_applied_migrations(conn)
        pending = get_pending_migrations(applied)

        if not pending:
            print("No pending migrations.")
            return

        print(f"Found {len(pending)} pending migration(s):")
        for f in pending:
            print(f"  - {f.name}")

        for filepath in pending:
            print(f"\nApplying: {filepath.name} ...", end=" ")
            try:
                # Each migration gets its own transaction.
                # On failure: rolls back this migration, stops the runner.
                with conn.transaction():
                    run_migration(conn, filepath)
                print("✓")
            except Exception as e:
                print(f"✗ FAILED")
                print(f"\nError in {filepath.name}:\n  {e}")
                print("\nMigration stopped. Fix the error and re-run.")
                sys.exit(1)

        print(f"\nAll migrations applied successfully.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="ISR migration runner")
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show migration status without applying anything"
    )
    args = parser.parse_args()

    if args.status:
        with get_conn() as conn:
            applied = get_applied_migrations(conn)
            pending = get_pending_migrations(applied)
            all_files = [f for f in sorted(MIGRATIONS_DIR.glob("*.sql")) if not f.stem.startswith("util_")]
            print(f"\nMigration status ({len(all_files)} total):\n")
            for f in all_files:
                status = "✓ applied" if f.stem in applied else "✗ pending"
                print(f"  {status}  {f.name}")
            print()
    else:
        migrate()
