"""
Migration: Add extra_data column to company_data table.

Usage:
    python scripts/add_extra_data_column.py

Supports SQLite and PostgreSQL. Safe to run multiple times (no-op if column exists).
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from scraper.database.manager import DatabaseManager, get_database_url

db_url = get_database_url()
print(f"Running migration on: {db_url}")

# DatabaseManager._ensure_schema_compatibility already handles this migration.
# Instantiating it is sufficient.
DatabaseManager(db_url)
print("Migration complete: extra_data column is present in company_data.")
