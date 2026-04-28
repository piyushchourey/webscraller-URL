"""
Cleanup script to delete failed jobs and all their references from the database.

Usage:
    # Activate your venv first if needed
    # python scripts/_cleanup_failed_jobs.py <job_id_1> <job_id_2> ...

- This script will delete the specified jobs and all related batches, tasks, and company data in a single transaction.
- It will also reset the primary key sequences for all affected tables to avoid sequence mismatch errors.
- You can pass one or more job IDs as arguments.

Example:
    python scripts/_cleanup_failed_jobs.py 9822a93d-029f-4724-8a5f-6eb31ce2954f b1ddc594-4a0b-489f-9fbe-26e760da40fb

"""
import sys
import os
from pathlib import Path
from dotenv import load_dotenv
import psycopg2

# --- CONFIGURE YOUR DATABASE CONNECTION HERE ---
# Load .env if present
dotenv_path = Path(__file__).parent.parent / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path)

DB_URL = os.environ.get("DATABASE_URL") or "postgresql://user:password@localhost:5432/yourdb"
# If SQLAlchemy-style URL, strip '+psycopg2' for psycopg2 compatibility
if DB_URL.startswith("postgresql+"):
    DB_URL = DB_URL.replace("postgresql+psycopg2://", "postgresql://")

if len(sys.argv) < 2:
    print("Usage: python scripts/_cleanup_failed_jobs.py <job_id_1> <job_id_2> ...")
    sys.exit(1)

job_ids = sys.argv[1:]

print(f"Deleting jobs: {job_ids}")

with psycopg2.connect(DB_URL) as conn:
    with conn.cursor() as cur:
        # Show counts before
        print("BEFORE DELETE:")
        for table in ["processing_jobs", "processing_batches", "processing_tasks", "company_data", "key_persons"]:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            print(f"  {table}: {cur.fetchone()[0]}")

        # Delete in dependency order for each job
        for job_id in job_ids:
            print(f"Deleting job {job_id} and all dependencies...")

            # Get task_ids for this job
            cur.execute("SELECT task_id FROM processing_tasks WHERE job_id = %s", (job_id,))
            task_ids = [row[0] for row in cur.fetchall()]

            if task_ids:
                # Get company_ids linked to those tasks
                cur.execute("SELECT company_id FROM company_data WHERE task_id = ANY(%s)", (task_ids,))
                company_ids = [row[0] for row in cur.fetchall()]

                if company_ids:
                    cur.execute("DELETE FROM key_persons WHERE company_id = ANY(%s)", (company_ids,))

                cur.execute("DELETE FROM company_data WHERE task_id = ANY(%s)", (task_ids,))

            cur.execute("DELETE FROM processing_tasks WHERE job_id = %s", (job_id,))
            cur.execute("DELETE FROM processing_batches WHERE job_id = %s", (job_id,))
            cur.execute("DELETE FROM processing_jobs WHERE job_id = %s", (job_id,))

        # Reset sequence for integer PKs
        for table, pk in [("company_data", "company_id"), ("key_persons", "person_id")]:
            try:
                cur.execute(f"SELECT setval(pg_get_serial_sequence('{table}', '{pk}'), COALESCE(MAX({pk}), 1), true) FROM {table}")
            except Exception as e:
                print(f"  Could not reset sequence for {table}: {e}")

        # Show counts after
        print("AFTER DELETE:")
        for table in ["processing_jobs", "processing_batches", "processing_tasks", "company_data", "key_persons"]:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            print(f"  {table}: {cur.fetchone()[0]}")

    conn.commit()
    print("Cleanup complete.")
