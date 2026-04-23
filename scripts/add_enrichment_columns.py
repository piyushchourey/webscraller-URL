#!/usr/bin/env python
"""Migration script: Add Smartlead enrichment columns to company_data table."""

import os
import sys
from sqlalchemy import text, inspect

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scraper.database.manager import DatabaseManager, get_database_url


def add_enrichment_columns():
    """Add enrichment-related columns to company_data table if they don't exist."""
    db = DatabaseManager()
    inspector = inspect(db.engine)
    
    # Check if table exists
    if not inspector.has_table("company_data"):
        print("❌ company_data table does not exist")
        return False
    
    # Get existing columns
    existing_columns = {col["name"] for col in inspector.get_columns("company_data")}
    
    # Define columns to add
    columns_to_add = [
        ("smartlead_enrichment", "JSONB DEFAULT NULL", "Smartlead API response"),
        ("enrichment_status", "TEXT DEFAULT 'pending'", "enrichment status (pending/processing/enriched/failed)"),
        ("enrichment_retry_count", "INTEGER DEFAULT 0", "number of enrichment retry attempts"),
        ("enrichment_last_error", "TEXT DEFAULT NULL", "error message from last enrichment attempt"),
        ("enrichment_updated_at", "TIMESTAMP DEFAULT NULL", "timestamp of last enrichment update"),
    ]
    
    added_count = 0
    
    with db.engine.begin() as connection:
        dialect_name = db.engine.dialect.name
        
        for col_name, col_def, description in columns_to_add:
            if col_name in existing_columns:
                print(f"⏭️  Column '{col_name}' already exists - skipping")
                continue
            
            try:
                if dialect_name == "postgresql":
                    sql = f"ALTER TABLE company_data ADD COLUMN {col_name} {col_def}"
                elif dialect_name == "sqlite":
                    # SQLite syntax slightly different
                    col_def_sqlite = col_def.replace("JSONB", "TEXT").replace("DEFAULT NULL", "")
                    sql = f"ALTER TABLE company_data ADD COLUMN {col_name} {col_def_sqlite}"
                else:
                    print(f"❌ Unsupported database dialect: {dialect_name}")
                    return False
                
                connection.execute(text(sql))
                print(f"✅ Added column '{col_name}' - {description}")
                added_count += 1
                
            except Exception as e:
                print(f"❌ Error adding column '{col_name}': {e}")
                return False
    
    if added_count == 0:
        print("✓ All enrichment columns already exist")
    else:
        print(f"\n✅ Migration complete: {added_count} column(s) added")
    
    return True


if __name__ == "__main__":
    print("=" * 70)
    print("PostgreSQL Migration: Add Smartlead Enrichment Columns")
    print("=" * 70)
    
    db_url = get_database_url()
    print(f"\nDatabase: {db_url}\n")
    
    success = add_enrichment_columns()
    
    if success:
        print("\n✅ Migration completed successfully!")
        sys.exit(0)
    else:
        print("\n❌ Migration failed")
        sys.exit(1)
