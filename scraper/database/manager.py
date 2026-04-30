"""Database manager for all persistence operations."""

import logging
import os
from datetime import datetime
from typing import List, Optional, Dict, Any

from sqlalchemy import create_engine, and_, func, inspect, text
from sqlalchemy.orm import sessionmaker, Session

from scraper.database.models import (
    Base,
    ProcessingJob,
    ProcessingBatch,
    ProcessingTask,
    CompanyData,
    KeyPerson,
)
from scraper.models import EnrichedCompanyData

logger = logging.getLogger(__name__)


def get_database_url() -> str:
    """Resolve database URL from environment with SQLite fallback."""
    db_url = os.getenv("DATABASE_URL") or os.getenv("DB_URL") or "sqlite:///webscraper.db"
    if db_url.startswith("postgres://"):
        return db_url.replace("postgres://", "postgresql+psycopg2://", 1)
    return db_url


class DatabaseManager:
    """Manages all database operations for the scraper."""

    def __init__(self, db_url: Optional[str] = None):
        """
        Initialize database connection and create tables.

        Args:
            db_url: Database connection URL
                   - SQLite: "sqlite:///webscraper.db" (default)
                   - PostgreSQL: "postgresql+psycopg2://user:password@localhost/dbname"
        """
        resolved_db_url = db_url or get_database_url()
        self.engine = create_engine(resolved_db_url, echo=False)
        self.SessionLocal = sessionmaker(bind=self.engine)

        # Create all tables
        Base.metadata.create_all(bind=self.engine)
        self._ensure_schema_compatibility()
        logger.info(f"Database initialized: {resolved_db_url}")

    def _ensure_schema_compatibility(self):
        """Apply lightweight runtime schema compatibility patches."""
        inspector = inspect(self.engine)
        if not inspector.has_table("processing_jobs"):
            return

        dialect_name = self.engine.dialect.name

        # Patch processing_jobs.job_name
        column_names = {col["name"] for col in inspector.get_columns("processing_jobs")}
        if "job_name" not in column_names:
            with self.engine.begin() as connection:
                if dialect_name == "postgresql":
                    connection.execute(text("ALTER TABLE processing_jobs ADD COLUMN IF NOT EXISTS job_name TEXT"))
                elif dialect_name == "sqlite":
                    connection.execute(text("ALTER TABLE processing_jobs ADD COLUMN job_name TEXT"))

        # Patch company_data.extra_data
        if inspector.has_table("company_data"):
            cd_columns = {col["name"] for col in inspector.get_columns("company_data")}
            if "extra_data" not in cd_columns:
                with self.engine.begin() as connection:
                    if dialect_name == "postgresql":
                        connection.execute(text("ALTER TABLE company_data ADD COLUMN IF NOT EXISTS extra_data JSONB"))
                    elif dialect_name == "sqlite":
                        connection.execute(text("ALTER TABLE company_data ADD COLUMN extra_data JSON"))
                logger.info("Added extra_data column to company_data")

        if dialect_name == "postgresql":
            self._sync_postgres_sequence("company_data", "company_id")
            self._sync_postgres_sequence("key_persons", "person_id")

    def _sync_postgres_sequence(self, table_name: str, column_name: str) -> None:
        """Align PostgreSQL serial sequence with the current max primary key value."""
        try:
            with self.engine.begin() as connection:
                sequence_name = connection.execute(
                    text(
                        "SELECT pg_get_serial_sequence(:table_name, :column_name)"
                    ),
                    {"table_name": table_name, "column_name": column_name},
                ).scalar()

                if not sequence_name:
                    return

                next_value = connection.execute(
                    text(
                        f"SELECT COALESCE(MAX({column_name}), 0) + 1 FROM {table_name}"
                    )
                ).scalar()

                connection.execute(
                    text("SELECT setval(:sequence_name, :next_value, false)"),
                    {
                        "sequence_name": sequence_name,
                        "next_value": int(next_value or 1),
                    },
                )

                logger.info(
                    "Synced PostgreSQL sequence %s to next value %s",
                    sequence_name,
                    next_value,
                )
        except Exception as exc:
            logger.warning(
                "Could not sync PostgreSQL sequence for %s.%s: %s",
                table_name,
                column_name,
                exc,
            )

    def get_session(self) -> Session:
        """Get a new database session."""
        return self.SessionLocal()

    # ── Job Management ───────────────────────────────────────────────────────

    def create_job(
        self,
        job_id: str,
        total_urls: int,
        batch_size: int = 50,
        job_name: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a new processing job."""
        session = self.get_session()
        try:
            total_batches = (total_urls + batch_size - 1) // batch_size
            job = ProcessingJob(
                job_id=job_id,
                job_name=job_name,
                status="pending",
                total_urls=total_urls,
                batch_size=batch_size,
                total_batches=total_batches,
                config=config or {},
            )
            session.add(job)
            session.commit()
            
            # Return dict instead of detached object
            result = {
                "job_id": job.job_id,
                "job_name": job.job_name,
                "status": job.status,
                "total_urls": job.total_urls,
                "batch_size": job.batch_size,
                "total_batches": total_batches,
            }
            logger.info(f"Created job {job_id} with {total_urls} URLs in {total_batches} batches")
            return result
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to create job: {e}")
            raise
        finally:
            session.close()

    def get_job(self, job_id: str) -> Optional[ProcessingJob]:
        """Get a job by ID."""
        session = self.get_session()
        try:
            job = session.query(ProcessingJob).filter(ProcessingJob.job_id == job_id).first()
            return job
        finally:
            session.close()

    def update_job_status(self, job_id: str, status: str, **kwargs):
        """Update job status and other fields."""
        session = self.get_session()
        try:
            job = session.query(ProcessingJob).filter(ProcessingJob.job_id == job_id).first()
            if job:
                job.status = status
                completed_at_value = kwargs.pop("completed_at", None)

                if completed_at_value is True or (status == "completed" and completed_at_value is None):
                    job.completed_at = datetime.utcnow()
                elif isinstance(completed_at_value, datetime):
                    job.completed_at = completed_at_value
                elif completed_at_value in (None, False):
                    pass

                for key, value in kwargs.items():
                    if hasattr(job, key):
                        setattr(job, key, value)
                session.commit()
                logger.info(f"Updated job {job_id} status to {status}")
            else:
                logger.warning(f"Job {job_id} not found")
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to update job status: {e}")
            raise
        finally:
            session.close()

    def get_all_jobs(self, limit: int = 100) -> List[ProcessingJob]:
        """Get all jobs, ordered by creation date (newest first)."""
        session = self.get_session()
        try:
            jobs = (
                session.query(ProcessingJob)
                .order_by(ProcessingJob.created_at.desc())
                .limit(limit)
                .all()
            )
            # Merge jobs into session to make them persistent before session closes
            # This ensures all attributes remain accessible after session.close()
            for job in jobs:
                session.merge(job, load=False)
            return jobs
        finally:
            session.close()

    # ── Task Management ──────────────────────────────────────────────────────

    def create_task(
        self,
        task_id: str,
        job_id: str,
        original_url: str,
        batch_number: int,
        batch_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new processing task."""
        session = self.get_session()
        try:
            task = ProcessingTask(
                task_id=task_id,
                job_id=job_id,
                batch_id=batch_id,
                original_url=original_url,
                batch_number=batch_number,
                status="queued",
            )
            session.add(task)
            session.commit()
            
            # Return dict instead of detached object
            result = {
                "task_id": task.task_id,
                "job_id": task.job_id,
                "original_url": task.original_url,
                "status": task.status,
            }
            return result
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to create task {task_id}: {e}")
            raise
        finally:
            session.close()

    def update_task_status(
        self,
        task_id: str,
        status: str,
        **kwargs,
    ):
        """Update task status and other fields."""
        session = self.get_session()
        try:
            task = session.query(ProcessingTask).filter(ProcessingTask.task_id == task_id).first()
            if task:
                task.status = status
                if status == "scraping" and not task.started_at:
                    task.started_at = datetime.utcnow()
                if status == "completed":
                    task.completed_at = datetime.utcnow()
                if status == "failed" and "error_message" in kwargs:
                    task.error_message = kwargs.pop("error_message")
                if "processing_time" in kwargs:
                    task.processing_time = kwargs.pop("processing_time")
                if "retry_count" in kwargs:
                    task.retry_count = kwargs.pop("retry_count")
                session.commit()
            else:
                logger.warning(f"Task {task_id} not found")
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to update task status: {e}")
            raise
        finally:
            session.close()

    def get_pending_tasks(self, job_id: str, limit: int = 50) -> List[ProcessingTask]:
        """Get pending tasks for a job."""
        session = self.get_session()
        try:
            tasks = (
                session.query(ProcessingTask)
                .filter(
                    and_(
                        ProcessingTask.job_id == job_id,
                        ProcessingTask.status.in_(["queued", "failed"]),
                    )
                )
                .limit(limit)
                .all()
            )
            return tasks
        finally:
            session.close()

    def is_url_processed(self, job_id: str, original_url: str) -> bool:
        """Check if URL was already successfully processed in this job."""
        session = self.get_session()
        try:
            task = (
                session.query(ProcessingTask)
                .filter(
                    and_(
                        ProcessingTask.job_id == job_id,
                        ProcessingTask.original_url == original_url,
                        ProcessingTask.status == "completed",
                    )
                )
                .first()
            )
            return task is not None
        finally:
            session.close()

    # ── Batch Management ─────────────────────────────────────────────────────

    def create_batch(
        self,
        batch_id: str,
        job_id: str,
        batch_number: int,
        task_count: int,
    ) -> Dict[str, Any]:
        """Create a new processing batch."""
        session = self.get_session()
        try:
            batch = ProcessingBatch(
                batch_id=batch_id,
                job_id=job_id,
                batch_number=batch_number,
                status="pending",
                task_count=task_count,
            )
            session.add(batch)
            session.commit()
            
            # Return dict instead of detached object
            result = {
                "batch_id": batch.batch_id,
                "job_id": batch.job_id,
                "batch_number": batch.batch_number,
            }
            return result
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to create batch: {e}")
            raise
        finally:
            session.close()

    def update_batch_status(self, batch_id: str, status: str):
        """Update batch status."""
        session = self.get_session()
        try:
            batch = session.query(ProcessingBatch).filter(ProcessingBatch.batch_id == batch_id).first()
            if batch:
                batch.status = status
                if status == "processing" and not batch.started_at:
                    batch.started_at = datetime.utcnow()
                if status == "completed":
                    batch.completed_at = datetime.utcnow()
                session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to update batch status: {e}")
            raise
        finally:
            session.close()

    def update_batch_counts(self, batch_id: str, success_count: int, failure_count: int):
        """Update batch success/failure counts."""
        session = self.get_session()
        try:
            batch = session.query(ProcessingBatch).filter(ProcessingBatch.batch_id == batch_id).first()
            if batch:
                batch.success_count = success_count
                batch.failure_count = failure_count
                session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to update batch counts: {e}")
            raise
        finally:
            session.close()

    # ── Company Data Management ──────────────────────────────────────────────

    def save_company_data(self, task_id: str, data: EnrichedCompanyData) -> Dict[str, Any]:
        """Save extracted company data to database."""
        session = self.get_session()
        try:
            resolved_status = data.processing_status if getattr(data, "processing_status", None) else "completed"
            company = CompanyData(
                task_id=task_id,
                original_url=data.url,
                company_name=data.company_name,
                company_url=data.company_url if hasattr(data, "company_url") else data.website,
                location=data.location,
                industry=data.industry,
                company_size=data.company_size if hasattr(data, "company_size") else None,
                segmentation=data.segmentation if hasattr(data, "segmentation") else None,
                salesforce_products=data.salesforce_products if hasattr(data, "salesforce_products") else [],
                raw_scraped_text=data.raw_scraped_text,
                ai_analysis=data.ai_analysis,
                confidence_score=data.confidence_score,
                processing_status=resolved_status,
                error_message=data.error_message,
                extra_data=data.extra_data if hasattr(data, "extra_data") else None,
            )
            session.add(company)
            session.flush()

            # Save key persons
            persons_data = []
            if data.key_persons:
                for person in data.key_persons:
                    key_person = KeyPerson(
                        company_id=company.company_id,
                        name=person.get("name", ""),
                        title=person.get("title", ""),
                        contact=person.get("contact", ""),
                    )
                    session.add(key_person)
                    persons_data.append({
                        "name": key_person.name,
                        "title": key_person.title,
                        "contact": key_person.contact,
                    })

            session.commit()
            
            # Return dict instead of detached object
            result = {
                "company_id": company.company_id,
                "company_name": company.company_name,
                "task_id": company.task_id,
                "key_persons": persons_data,
            }
            logger.info(f"Saved company data for {data.company_name} (task {task_id})")
            return result
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to save company data: {e}")
            raise
        finally:
            session.close()

    def get_company_data(self, company_id: int) -> Optional[CompanyData]:
        """Get company data by ID with eager loading."""
        session = self.get_session()
        try:
            from sqlalchemy.orm import joinedload
            company = (
                session.query(CompanyData)
                .options(joinedload(CompanyData.key_persons))
                .filter(CompanyData.company_id == company_id)
                .first()
            )
            # Eagerly load key_persons before closing session
            if company:
                _ = company.key_persons
            return company
        finally:
            session.close()

    def get_company_data_by_url(self, original_url: str) -> Optional[CompanyData]:
        """Get company data by original URL."""
        session = self.get_session()
        try:
            company = (
                session.query(CompanyData)
                .filter(CompanyData.original_url == original_url)
                .first()
            )
            return company
        finally:
            session.close()

    def get_job_results(self, job_id: str) -> List[Dict[str, Any]]:
        """Get all company data results for a job."""
        session = self.get_session()
        try:
            companies = (
                session.query(CompanyData)
                .join(ProcessingTask)
                .filter(ProcessingTask.job_id == job_id)
                .all()
            )

            results = []
            for company in companies:
                company_dict = {
                    "company_id": company.company_id,
                    "original_url": company.original_url,
                    "company_name": company.company_name,
                    "company_url": company.company_url,
                    "location": company.location,
                    "industry": company.industry,
                    "company_size": company.company_size,
                    "segmentation": company.segmentation,
                    "platform_products": company.salesforce_products or [],
                    "salesforce_products": company.salesforce_products or [],
                    "key_persons": [
                        {
                            "name": p.name,
                            "title": p.title,
                            "contact": p.contact,
                        }
                        for p in company.key_persons
                    ],
                    "confidence_score": company.confidence_score,
                    "enrichment_status": company.enrichment_status or "pending",
                    "smartlead_enrichment": company.smartlead_enrichment,
                    "enrichment_updated_at": company.enrichment_updated_at,
                    "enrichment_last_error": company.enrichment_last_error,
                    "extra_data": company.extra_data or {},
                }
                results.append(company_dict)

            return results
        finally:
            session.close()

    # ── Statistics ───────────────────────────────────────────────────────────

    def get_job_stats(self, job_id: str) -> Dict[str, Any]:
        """Get comprehensive statistics for a job."""
        session = self.get_session()
        try:
            job = session.query(ProcessingJob).filter(ProcessingJob.job_id == job_id).first()
            if not job:
                return {}

            completed_tasks = (
                session.query(func.count(ProcessingTask.task_id))
                .filter(
                    and_(
                        ProcessingTask.job_id == job_id,
                        ProcessingTask.status == "completed",
                    )
                )
                .scalar()
            )

            failed_tasks = (
                session.query(func.count(ProcessingTask.task_id))
                .filter(
                    and_(
                        ProcessingTask.job_id == job_id,
                        ProcessingTask.status == "failed",
                    )
                )
                .scalar()
            )

            pending_tasks = (
                session.query(func.count(ProcessingTask.task_id))
                .filter(
                    and_(
                        ProcessingTask.job_id == job_id,
                        ProcessingTask.status.in_(["queued", "scraping", "analyzing"]),
                    )
                )
                .scalar()
            )

            return {
                "job_id": job_id,
                "job_name": job.job_name,
                "status": job.status,
                "total_urls": job.total_urls,
                "completed_urls": completed_tasks,
                "failed_urls": failed_tasks,
                "pending_urls": pending_tasks,
                "progress_percentage": (completed_tasks / job.total_urls * 100) if job.total_urls > 0 else 0,
                "created_at": job.created_at,
                "completed_at": job.completed_at,
                "total_batches": job.total_batches,
            }
        finally:
            session.close()

    def get_cached_emails_by_domain(self, domain: str) -> Dict[tuple, Dict[str, Any]]:
        """
        Return a (firstName.lower, lastName.lower, domain) -> contact dict map
        built from smartlead_enrichment.contacts_enriched for any company_data
        record whose company_url matches the given domain.
        Only contacts with a non-empty email_id are included.
        """
        if not domain:
            return {}
        session = self.get_session()
        try:
            logger.info("[EMAIL CACHE] DB query | domain=%s", domain)
            rows = (
                session.query(CompanyData.smartlead_enrichment)
                .filter(
                    and_(
                        CompanyData.smartlead_enrichment.isnot(None),
                        CompanyData.company_url.ilike(f"%{domain}%"),
                    )
                )
                .all()
            )
            cache: Dict[tuple, Dict[str, Any]] = {}
            for (enrichment,) in rows:
                if not enrichment:
                    continue
                for contact in enrichment.get("contacts_enriched") or []:
                    email_id = (contact.get("email_id") or "").strip()
                    if not email_id or "@example.com" in email_id.lower():
                        continue
                    first = (contact.get("firstName") or "").strip().lower()
                    last = (contact.get("lastName") or "").strip().lower()
                    contact_domain = (contact.get("companyDomain") or domain).strip().lower()
                    if first and last:
                        cache[(first, last, contact_domain)] = contact
            logger.info(
                "[EMAIL CACHE] DB query result | domain=%s | matching_company_records=%d | cached_emails_found=%d",
                domain, len(rows), len(cache),
            )
            return cache
        except Exception as exc:
            logger.warning("[EMAIL CACHE] DB query failed | domain=%s | error=%s", domain, exc)
            return {}
        finally:
            session.close()

    def close(self):
        """Close database connection."""
        self.engine.dispose()

    # ── Enrichment Support ───────────────────────────────────────────────────

    def get_companies_for_enrichment(self, job_id: str, status: str = "pending", limit: int = 100) -> List[CompanyData]:
        """
        Get companies for enrichment by status and job.
        
        Args:
            job_id: Job ID to filter by
            status: Enrichment status (pending, processing, enriched, failed)
            limit: Maximum number of companies to return
            
        Returns:
            List of CompanyData records
        """
        session = self.get_session()
        try:
            companies = (
                session.query(CompanyData)
                .join(ProcessingTask, CompanyData.task_id == ProcessingTask.task_id)
                .filter(
                    and_(
                        ProcessingTask.job_id == job_id,
                        CompanyData.enrichment_status == status,
                    )
                )
                .limit(limit)
                .all()
            )
            return companies
        finally:
            session.close()

    def get_enrichment_stats(self, job_id: str) -> Dict[str, int]:
        """
        Get enrichment status breakdown for a job.
        
        Args:
            job_id: Job ID
            
        Returns:
            Dict with status counts and total
        """
        session = self.get_session()
        try:
            stats = (
                session.query(
                    CompanyData.enrichment_status,
                    func.count(CompanyData.company_id).label("count")
                )
                .join(ProcessingTask, CompanyData.task_id == ProcessingTask.task_id)
                .filter(ProcessingTask.job_id == job_id)
                .group_by(CompanyData.enrichment_status)
                .all()
            )
            
            result = {
                "pending": 0,
                "processing": 0,
                "enriched": 0,
                "failed": 0,
                "total": 0,
            }
            
            for status, count in stats:
                if status in result:
                    result[status] = count
                result["total"] += count
            
            return result
        finally:
            session.close()

    def update_company_enrichment(
        self,
        company_id: int,
        enrichment_status: str,
        enrichment_data: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
        retry_count: Optional[int] = None,
    ) -> bool:
        """
        Update company enrichment status and data.
        
        Args:
            company_id: Company ID
            enrichment_status: New status (pending/processing/enriched/failed)
            enrichment_data: Enrichment JSON data (for success)
            error_message: Error message (for failed)
            retry_count: Increment retry count
            
        Returns:
            True if successful, False otherwise
        """
        session = self.get_session()
        try:
            company = session.query(CompanyData).filter(CompanyData.company_id == company_id).first()
            if not company:
                logger.warning(f"Company {company_id} not found")
                return False
            
            company.enrichment_status = enrichment_status
            company.enrichment_updated_at = datetime.utcnow()
            
            if enrichment_data:
                company.smartlead_enrichment = enrichment_data
                company.enrichment_last_error = None
            
            if error_message:
                company.enrichment_last_error = error_message
            
            if retry_count is not None:
                company.enrichment_retry_count = retry_count
            
            session.commit()
            logger.info(f"Updated company {company_id} enrichment to {enrichment_status}")
            return True
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error updating enrichment for company {company_id}: {e}")
            return False
        finally:
            session.close()

    def increment_enrichment_retry(self, company_id: int) -> int:
        """
        Increment retry count for a company.
        
        Args:
            company_id: Company ID
            
        Returns:
            New retry count or -1 on error
        """
        session = self.get_session()
        try:
            company = session.query(CompanyData).filter(CompanyData.company_id == company_id).first()
            if not company:
                return -1
            
            company.enrichment_retry_count = (company.enrichment_retry_count or 0) + 1
            session.commit()
            return company.enrichment_retry_count
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error incrementing retry for company {company_id}: {e}")
            return -1
        finally:
            session.close()

