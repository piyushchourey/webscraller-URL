"""Widen legacy VARCHAR columns to TEXT in PostgreSQL for scraper tables."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text

from scraper.database import DatabaseManager


ALTER_STATEMENTS = [
    "ALTER TABLE processing_jobs ALTER COLUMN job_id TYPE TEXT",
    "ALTER TABLE processing_jobs ALTER COLUMN status TYPE TEXT",
    "ALTER TABLE processing_batches ALTER COLUMN batch_id TYPE TEXT",
    "ALTER TABLE processing_batches ALTER COLUMN job_id TYPE TEXT",
    "ALTER TABLE processing_batches ALTER COLUMN status TYPE TEXT",
    "ALTER TABLE processing_tasks ALTER COLUMN task_id TYPE TEXT",
    "ALTER TABLE processing_tasks ALTER COLUMN job_id TYPE TEXT",
    "ALTER TABLE processing_tasks ALTER COLUMN batch_id TYPE TEXT",
    "ALTER TABLE processing_tasks ALTER COLUMN status TYPE TEXT",
    "ALTER TABLE company_data ALTER COLUMN task_id TYPE TEXT",
    "ALTER TABLE company_data ALTER COLUMN company_name TYPE TEXT",
    "ALTER TABLE company_data ALTER COLUMN industry TYPE TEXT",
    "ALTER TABLE company_data ALTER COLUMN company_size TYPE TEXT",
    "ALTER TABLE company_data ALTER COLUMN segmentation TYPE TEXT",
    "ALTER TABLE company_data ALTER COLUMN processing_status TYPE TEXT",
    "ALTER TABLE key_persons ALTER COLUMN name TYPE TEXT",
    "ALTER TABLE key_persons ALTER COLUMN title TYPE TEXT",
]


def main() -> None:
    db = DatabaseManager()
    with db.engine.begin() as connection:
        for statement in ALTER_STATEMENTS:
            connection.execute(text(statement))
    print("PostgreSQL column widening completed successfully.")


if __name__ == "__main__":
    main()
