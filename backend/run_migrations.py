"""
Database migration runner for Jainune.
Applies all SQL migrations in backend/migrations in order, tracking applied versions in schema_migrations.
"""
import asyncio
import os
import sys
from pathlib import Path
import asyncpg

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/jainune_dev")
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
DOWN_MIGRATIONS_DIR = MIGRATIONS_DIR / "down"


async def run_migrations():
    print(f"Connecting to database: {DATABASE_URL.split('@')[-1]}")
    try:
        conn = await asyncpg.connect(DATABASE_URL)
    except Exception as exc:
        print(f"Error connecting to database: {exc}")
        sys.exit(1)

    try:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version VARCHAR(128) PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        """)

        applied_rows = await conn.fetch("SELECT version FROM schema_migrations")
        applied = {r["version"] for r in applied_rows}

        migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
        if not migration_files:
            print("No migration files found.")
            return

        for sql_file in migration_files:
            version = sql_file.name
            if version in applied:
                print(f"  [SKIPPED] {version} (already applied)")
                continue

            print(f"  [APPLYING] {version}...")
            with open(sql_file, "r", encoding="utf-8") as f:
                sql_content = f.read()

            async with conn.transaction():
                await conn.execute(sql_content)
                await conn.execute("INSERT INTO schema_migrations (version) VALUES ($1)", version)
            print(f"  [DONE] {version}")

        print("\nAll database migrations successfully reconciled!")
    finally:
        await conn.close()


async def rollback_migrations(steps: int = 1, target_version: str = None):
    print(f"Connecting to database for rollback: {DATABASE_URL.split('@')[-1]}")
    try:
        conn = await asyncpg.connect(DATABASE_URL)
    except Exception as exc:
        print(f"Error connecting to database: {exc}")
        sys.exit(1)

    try:
        applied_rows = await conn.fetch("SELECT version FROM schema_migrations ORDER BY applied_at DESC, version DESC")
        if not applied_rows:
            print("No applied migrations to rollback.")
            return

        applied_versions = [r["version"] for r in applied_rows]
        rolled_back_count = 0

        for version in applied_versions:
            if target_version and version == target_version:
                print(f"Reached target version {target_version}. Stopping rollback.")
                break
            if steps is not None and rolled_back_count >= steps:
                break

            base_stem = version.replace(".sql", "")
            down_file = DOWN_MIGRATIONS_DIR / f"{base_stem}.down.sql"
            if not down_file.exists():
                print(f"  [ERROR] Down migration not found for {version} at {down_file}")
                sys.exit(1)

            print(f"  [ROLLING BACK] {version} via {down_file.name}...")
            with open(down_file, "r", encoding="utf-8") as f:
                down_sql = f.read()

            async with conn.transaction():
                await conn.execute(down_sql)
                await conn.execute("DELETE FROM schema_migrations WHERE version = $1", version)

            print(f"  [ROLLED BACK] {version}")
            rolled_back_count += 1

        print(f"\nSuccessfully rolled back {rolled_back_count} migration(s)!")
    finally:
        await conn.close()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--rollback":
        count = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        asyncio.run(rollback_migrations(steps=count))
    else:
        asyncio.run(run_migrations())
