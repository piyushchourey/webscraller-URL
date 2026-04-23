#!/usr/bin/env python
"""Debug script to check job names in database."""

import os
from scraper.database.manager import DatabaseManager, get_database_url

# Get the DB URL
db_url = get_database_url()
print(f"Database URL: {db_url}\n")

# Initialize DB
db = DatabaseManager()

# Query jobs
jobs = db.get_all_jobs(limit=5)
print(f"Total jobs found: {len(jobs)}\n")

for idx, job in enumerate(jobs):
    print(f"Job {idx + 1}:")
    print(f"  ID: {job.job_id[:8]}...")
    print(f"  Name (type={type(job.job_name).__name__}): {repr(job.job_name)}")
    print(f"  Status: {job.status}")
    print()
