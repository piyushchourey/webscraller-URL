"""Manager for Smartlead enrichment operations on a per-job basis."""

import logging
import re
from typing import List, Optional, Dict, Any
from datetime import datetime

from sqlalchemy import and_, func, text
from sqlalchemy.orm import Session

from scraper.database.manager import DatabaseManager
from scraper.database.models import CompanyData, ProcessingTask, ProcessingJob, KeyPerson

logger = logging.getLogger(__name__)


class EnrichmentManager:
    """Manages per-job Smartlead enrichment workflow."""

    def __init__(self, db_manager: DatabaseManager):
        """
        Initialize enrichment manager with database.
        
        Args:
            db_manager: DatabaseManager instance for database operations
        """
        self.db = db_manager

    def get_pending_companies_for_job(self, job_id: str) -> List[Dict[str, Any]]:
        """
        Get all companies in a job that need enrichment.
        
        Args:
            job_id: Job ID to get pending companies for
            
        Returns:
            List of company records with enrichment_status = 'pending'
        """
        session = self.db.get_session()
        try:
            companies = (
                session.query(CompanyData)
                .join(ProcessingTask, CompanyData.task_id == ProcessingTask.task_id)
                .filter(
                    and_(
                        ProcessingTask.job_id == job_id,
                        CompanyData.enrichment_status == "pending"
                    )
                )
                .all()
            )
            
            # Convert to dict list for safe usage outside session
            result = [
                {
                    "company_id": c.company_id,
                    "task_id": c.task_id,
                    "original_url": c.original_url,
                    "company_name": c.company_name,
                    "company_url": c.company_url,
                    "location": c.location,
                    "industry": c.industry,
                    "company_size": c.company_size,
                    "enrichment_status": c.enrichment_status,
                    "enrichment_retry_count": c.enrichment_retry_count,
                }
                for c in companies
            ]
            
            logger.info(f"Found {len(result)} pending companies for job {job_id}")
            return result
            
        finally:
            session.close()

    def get_enrichment_stats_for_job(self, job_id: str) -> Dict[str, int]:
        """
        Get enrichment status breakdown for a job.
        
        Args:
            job_id: Job ID
            
        Returns:
            Dict with counts: {pending, processing, enriched, failed}
        """
        session = self.db.get_session()
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
                result[status] = count
                result["total"] += count
            
            return result
            
        finally:
            session.close()

    def mark_enrichment_processing(self, company_id: int) -> bool:
        """
        Mark a company as currently being enriched.
        
        Args:
            company_id: Company ID
            
        Returns:
            True if successful, False otherwise
        """
        session = self.db.get_session()
        try:
            company = session.query(CompanyData).filter(CompanyData.company_id == company_id).first()
            if company:
                company.enrichment_status = "processing"
                company.enrichment_updated_at = datetime.utcnow()
                session.commit()
                logger.info(f"Marked company {company_id} as processing enrichment")
                return True
            else:
                logger.warning(f"Company {company_id} not found")
                return False
        except Exception as e:
            session.rollback()
            logger.error(f"Error marking company {company_id} as processing: {e}")
            return False
        finally:
            session.close()

    def save_enrichment_result(
        self,
        company_id: int,
        enrichment_data: Dict[str, Any],
        success: bool = True,
        error_message: Optional[str] = None,
    ) -> bool:
        """
        Save enrichment result for a company.
        
        Args:
            company_id: Company ID
            enrichment_data: Smartlead API response data (if successful)
            success: Whether enrichment was successful
            error_message: Error message if failed
            
        Returns:
            True if successful, False otherwise
        """
        session = self.db.get_session()
        try:
            company = session.query(CompanyData).filter(CompanyData.company_id == company_id).first()
            if not company:
                logger.warning(f"Company {company_id} not found")
                return False
            
            if success:
                company.enrichment_status = "enriched"
                company.smartlead_enrichment = enrichment_data
                company.enrichment_retry_count = 0
                company.enrichment_last_error = None
                logger.info(f"Successfully enriched company {company_id}")
            else:
                company.enrichment_status = "failed"
                company.enrichment_retry_count += 1
                company.enrichment_last_error = error_message
                logger.warning(f"Failed to enrich company {company_id}: {error_message}")
            
            company.enrichment_updated_at = datetime.utcnow()
            session.commit()
            return True
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving enrichment result for company {company_id}: {e}")
            return False
        finally:
            session.close()

    def reset_failed_enrichments(self, job_id: str, max_retries: int = 3) -> int:
        """
        Reset failed enrichments for a job (reset retry count if under max).
        
        Args:
            job_id: Job ID
            max_retries: Maximum retry attempts before giving up
            
        Returns:
            Number of records reset
        """
        session = self.db.get_session()
        try:
            # Get failed companies that haven't exceeded max retries
            failed_companies = (
                session.query(CompanyData)
                .join(ProcessingTask, CompanyData.task_id == ProcessingTask.task_id)
                .filter(
                    and_(
                        ProcessingTask.job_id == job_id,
                        CompanyData.enrichment_status == "failed",
                        CompanyData.enrichment_retry_count < max_retries,
                    )
                )
                .all()
            )
            
            count = 0
            for company in failed_companies:
                company.enrichment_status = "pending"
                company.enrichment_updated_at = datetime.utcnow()
                count += 1
            
            session.commit()
            logger.info(f"Reset {count} failed enrichments for job {job_id}")
            return count
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error resetting failed enrichments for job {job_id}: {e}")
            return 0
        finally:
            session.close()

    def get_job_info(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get job information for enrichment context.
        
        Args:
            job_id: Job ID
            
        Returns:
            Job info dict or None if not found
        """
        session = self.db.get_session()
        try:
            job = session.query(ProcessingJob).filter(ProcessingJob.job_id == job_id).first()
            if job:
                return {
                    "job_id": job.job_id,
                    "job_name": job.job_name or "Untitled Job",
                    "status": job.status,
                    "total_urls": job.total_urls,
                    "created_at": job.created_at,
                }
            return None
        finally:
            session.close()

    @staticmethod
    def _normalize_person_name(name: Optional[str]) -> str:
        """Normalize names for matching.
        """
        return re.sub(r"[^a-z0-9]", "", (name or "").lower())

    def update_key_person_emails(
        self,
        company_id: int,
        contacts_enriched: List[Dict[str, Any]],
    ) -> int:
        """
        Update key_persons.contact with valid email_id from Smartlead response.

        Returns:
            Number of key person rows updated.
        """
        session = self.db.get_session()
        try:
            valid_email_map: Dict[str, str] = {}
            for contact in contacts_enriched:
                email_id = contact.get("email_id")
                verification_status = str(contact.get("verification_status") or "").lower()
                if not email_id or verification_status != "valid":
                    continue

                full_name = contact.get("fullName") or f"{contact.get('firstName', '')} {contact.get('lastName', '')}".strip()
                normalized = self._normalize_person_name(full_name)
                if normalized:
                    valid_email_map[normalized] = email_id

            if not valid_email_map:
                return 0

            key_people = (
                session.query(KeyPerson)
                .filter(KeyPerson.company_id == company_id)
                .all()
            )

            updated = 0
            for person in key_people:
                normalized_person_name = self._normalize_person_name(person.name)
                email_id = valid_email_map.get(normalized_person_name)
                if email_id:
                    person.contact = email_id
                    updated += 1

            if updated:
                session.commit()
            return updated

        except Exception as e:
            session.rollback()
            logger.error(f"Error updating key person emails for company {company_id}: {e}")
            return 0
        finally:
            session.close()
