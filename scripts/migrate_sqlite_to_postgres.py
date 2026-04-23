"""Migrate scraper records from SQLite to PostgreSQL using SQLAlchemy models."""

import argparse
import sys
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import create_engine, delete
from sqlalchemy.orm import sessionmaker

from scraper.database.models import (
    Base,
    CompanyData,
    KeyPerson,
    ProcessingBatch,
    ProcessingJob,
    ProcessingTask,
)


def _iterable_count(rows: Iterable) -> int:
    return sum(1 for _ in rows)


def migrate(source_url: str, target_url: str, truncate_target: bool = False) -> None:
    source_engine = create_engine(source_url, echo=False)
    target_engine = create_engine(target_url, echo=False)

    SourceSession = sessionmaker(bind=source_engine)
    TargetSession = sessionmaker(bind=target_engine)

    Base.metadata.create_all(bind=target_engine)

    source_session = SourceSession()
    target_session = TargetSession()

    try:
        if truncate_target:
            target_session.execute(delete(KeyPerson))
            target_session.execute(delete(CompanyData))
            target_session.execute(delete(ProcessingTask))
            target_session.execute(delete(ProcessingBatch))
            target_session.execute(delete(ProcessingJob))
            target_session.commit()

        jobs = source_session.query(ProcessingJob).all()
        batches = source_session.query(ProcessingBatch).all()
        tasks = source_session.query(ProcessingTask).all()
        companies = source_session.query(CompanyData).all()
        key_people = source_session.query(KeyPerson).all()

        for row in jobs:
            target_session.merge(ProcessingJob(**{c.name: getattr(row, c.name) for c in ProcessingJob.__table__.columns}))
        target_session.commit()

        for row in batches:
            target_session.merge(ProcessingBatch(**{c.name: getattr(row, c.name) for c in ProcessingBatch.__table__.columns}))
        target_session.commit()

        for row in tasks:
            target_session.merge(ProcessingTask(**{c.name: getattr(row, c.name) for c in ProcessingTask.__table__.columns}))
        target_session.commit()

        for row in companies:
            target_session.merge(CompanyData(**{c.name: getattr(row, c.name) for c in CompanyData.__table__.columns}))
        target_session.commit()

        for row in key_people:
            target_session.merge(KeyPerson(**{c.name: getattr(row, c.name) for c in KeyPerson.__table__.columns}))
        target_session.commit()

        print("Migration completed successfully")
        print(f"Jobs migrated: {_iterable_count(jobs)}")
        print(f"Batches migrated: {_iterable_count(batches)}")
        print(f"Tasks migrated: {_iterable_count(tasks)}")
        print(f"Company rows migrated: {_iterable_count(companies)}")
        print(f"Key persons migrated: {_iterable_count(key_people)}")

    finally:
        source_session.close()
        target_session.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate scraper data from SQLite to PostgreSQL")
    parser.add_argument(
        "--source",
        default="sqlite:///webscraper.db",
        help="Source SQLAlchemy DB URL (default: sqlite:///webscraper.db)",
    )
    parser.add_argument(
        "--target",
        required=True,
        help="Target SQLAlchemy DB URL (example: postgresql+psycopg2://user:pass@host:5432/db)",
    )
    parser.add_argument(
        "--truncate-target",
        action="store_true",
        help="Delete existing target records before migration",
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    migrate(arguments.source, arguments.target, arguments.truncate_target)
