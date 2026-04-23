"""Ensure `job_name` column exists in `processing_jobs` table."""

import sys
from pathlib import Path

from sqlalchemy import inspect, text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scraper.database import DatabaseManager


def main() -> None:
    db = DatabaseManager()
    inspector = inspect(db.engine)

    if not inspector.has_table("processing_jobs"):
        print("Table processing_jobs does not exist yet. Nothing to patch.")
        return

    columns = {col["name"] for col in inspector.get_columns("processing_jobs")}
    if "job_name" in columns:
        print("Column job_name already exists.")
        return

    dialect_name = db.engine.dialect.name
    with db.engine.begin() as connection:
        if dialect_name == "postgresql":
            connection.execute(text("ALTER TABLE processing_jobs ADD COLUMN IF NOT EXISTS job_name TEXT"))
        elif dialect_name == "sqlite":
            connection.execute(text("ALTER TABLE processing_jobs ADD COLUMN job_name TEXT"))
        else:
            connection.execute(text("ALTER TABLE processing_jobs ADD COLUMN job_name TEXT"))

    print("Column job_name added successfully.")


if __name__ == "__main__":
    main()
