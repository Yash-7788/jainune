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


if __name__ == "__main__":
    asyncio.run(run_migrations())
