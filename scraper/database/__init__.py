"""Database layer for webscraper persistence."""

from scraper.database.models import Base, ProcessingJob, ProcessingTask, CompanyData, KeyPerson
from scraper.database.manager import DatabaseManager

__all__ = [
    "Base",
    "ProcessingJob",
    "ProcessingTask",
    "CompanyData",
    "KeyPerson",
    "DatabaseManager",
]
