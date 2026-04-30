#!/usr/bin/env python
"""
Job-wise Smartlead enrichment worker.

This script processes enrichment for a specific job:
1. Query all pending companies for a job
2. Call Smartlead API for each company
3. Save enrichment data to database
4. Handle retries and errors
"""

import logging
import os
import sys
import argparse
from typing import Any, Optional
from urllib.parse import urlparse

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scraper.database.manager import DatabaseManager, get_database_url
from scraper.enrichment.manager import EnrichmentManager
from scraper.enrichment.smartlead_adapter import SmartleadAdapter

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def extract_domain(company_url: Optional[str]) -> Optional[str]:
    """Extract bare domain from URL/domain value."""
    if not company_url:
        return None
    value = company_url.strip()
    if not value:
        return None
    if "://" not in value:
        value = f"https://{value}"
    parsed = urlparse(value)
    domain = (parsed.netloc or parsed.path or "").lower().strip()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain or None


def format_smartlead_error(last_request_error: Optional[dict[str, Any]]) -> str:
    """Build a user-friendly root-cause error message from adapter metadata."""
    if not last_request_error:
        return "Smartlead API returned no data"

    error_type = str(last_request_error.get("type") or "unknown").strip()
    status_code = last_request_error.get("status_code")
    message = str(last_request_error.get("message") or "").strip()

    if status_code:
        return f"Smartlead {error_type} error ({status_code}): {message or 'No details'}"
    return f"Smartlead {error_type} error: {message or 'No details'}"


def _parse_csv(value: Optional[str]) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item and item.strip()]


def enrich_job(
    job_id: str,
    api_key: str,
    rate_limit: int = 60,
    max_retries: int = 3,
    dry_run: bool = False,
    company_filter_hook_enabled: Optional[bool] = None,
    company_filter_min_employees: Optional[int] = None,
    company_filter_max_employees: Optional[int] = None,
    excluded_industries: Optional[list[str]] = None,
    excluded_locations: Optional[list[str]] = None,
) -> bool:
    """
    Enrich all pending companies for a specific job.
    
    Args:
        job_id: Job ID to enrich
        api_key: Smartlead API key
        rate_limit: API calls per minute
        max_retries: Maximum retry attempts for failed enrichments
        dry_run: If True, only show what would be enriched without making API calls
        company_filter_hook_enabled: Optional hook toggle for pre-find-emails filtering
        company_filter_min_employees: Optional minimum employee threshold
        company_filter_max_employees: Optional maximum employee threshold
        excluded_industries: Optional list of industry exclusion keywords
        excluded_locations: Optional list of location exclusion keywords
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Initialize managers
        db = DatabaseManager()
        enrichment_mgr = EnrichmentManager(db)
        smartlead = SmartleadAdapter(
            api_key,
            rate_limit_per_minute=rate_limit,
            company_filter_hook_enabled=company_filter_hook_enabled,
            company_filter_min_employees=company_filter_min_employees,
            company_filter_max_employees=company_filter_max_employees,
            excluded_industries=excluded_industries,
            excluded_locations=excluded_locations,
        )
        
        # Get job info
        job_info = enrichment_mgr.get_job_info(job_id)
        if not job_info:
            logger.error(f"Job {job_id} not found")
            return False
        
        logger.info("=" * 70)
        logger.info(f"Starting enrichment for Job: {job_info['job_name']}")
        logger.info(f"Job ID: {job_id}")
        logger.info(f"Status: {job_info['status']}")
        logger.info(f"Dry Run: {dry_run}")
        logger.info(f"Company Filter Hook: {smartlead.company_filter_hook_enabled}")
        logger.info("=" * 70)
        
        # Get enrichment stats
        stats = enrichment_mgr.get_enrichment_stats_for_job(job_id)
        logger.info(f"Enrichment Status: {stats['pending']} pending, "
                   f"{stats['processing']} processing, "
                   f"{stats['enriched']} enriched, "
                   f"{stats['failed']} failed out of {stats['total']} total")
        
        if stats["pending"] == 0:
            logger.info("No pending companies to enrich for this job")
            return True
        
        # Get pending companies
        pending_companies = enrichment_mgr.get_pending_companies_for_job(job_id)
        logger.info(f"\nProcessing {len(pending_companies)} pending companies...\n")
        
        enriched_count = 0
        failed_count = 0
        
        for idx, company in enumerate(pending_companies, 1):
            logger.info(f"[{idx}/{len(pending_companies)}] Processing: {company['company_name']}")
            
            if dry_run:
                logger.info(f"  [DRY RUN] Would enrich: {company['company_name']} (Domain: {company['company_url']})")
                enriched_count += 1
                continue
            
            # Mark as processing
            enrichment_mgr.mark_enrichment_processing(company["company_id"])
            
            try:
                # Domain-first lookup, fallback to company name handled in adapter
                domain = extract_domain(company.get("company_url"))
                enrichment_data = smartlead.enrich_company_full(
                    company_name=company["company_name"],
                    domain=domain,
                    location=company["location"],
                    db=db,
                )
                
                if enrichment_data:
                    # Save successful enrichment
                    success = enrichment_mgr.save_enrichment_result(
                        company["company_id"],
                        enrichment_data,
                        success=True,
                    )
                    if success:
                        updated_contacts = enrichment_mgr.update_key_person_emails(
                            company["company_id"],
                            enrichment_data.get("contacts_enriched", []),
                        )
                        logger.info(f"  ✅ Successfully enriched")
                        if updated_contacts:
                            logger.info(f"  📧 Updated {updated_contacts} key person email(s)")
                        enriched_count += 1
                    else:
                        logger.error(f"  ❌ Failed to save enrichment")
                        failed_count += 1
                else:
                    # Save failed enrichment
                    failure_reason = format_smartlead_error(getattr(smartlead, "last_request_error", None))
                    enrichment_mgr.save_enrichment_result(
                        company["company_id"],
                        None,
                        success=False,
                        error_message=failure_reason,
                    )
                    logger.warning(f"  ⚠️  {failure_reason}")
                    failed_count += 1
                    
            except Exception as e:
                logger.error(f"  ❌ Error: {e}")
                enrichment_mgr.save_enrichment_result(
                    company["company_id"],
                    None,
                    success=False,
                    error_message=str(e),
                )
                failed_count += 1
        
        # Summary
        logger.info("\n" + "=" * 70)
        logger.info(f"Enrichment Complete for Job: {job_info['job_name']}")
        logger.info(f"✅ Successfully enriched: {enriched_count}")
        logger.info(f"❌ Failed: {failed_count}")
        logger.info("=" * 70)
        
        # Offer retry for failed enrichments
        if failed_count > 0:
            logger.info(f"\nTip: Run with --retry-failed to retry failed enrichments")
        
        return True
        
    except Exception as e:
        logger.error(f"Fatal error during enrichment: {e}", exc_info=True)
        return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Enrich company data for a specific job using Smartlead API"
    )
    parser.add_argument(
        "job_id",
        help="Job ID to enrich",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("SMARTLEAD_API_KEY"),
        help="Smartlead API key (or set SMARTLEAD_API_KEY env var)",
    )
    parser.add_argument(
        "--rate-limit",
        type=int,
        default=60,
        help="API calls per minute (default: 60)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be enriched without making API calls",
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Reset failed enrichments to pending for retry",
    )
    parser.add_argument(
        "--company-filter-hook",
        choices=["on", "off"],
        default=None,
        help="Enable/disable pre-find-emails company filter hook.",
    )
    parser.add_argument(
        "--company-min-employees",
        type=int,
        default=None,
        help="Exclude companies with fewer than this many employees.",
    )
    parser.add_argument(
        "--company-max-employees",
        type=int,
        default=None,
        help="Exclude companies with more than this many employees.",
    )
    parser.add_argument(
        "--excluded-industries",
        default=None,
        help="Comma-separated industry keywords to exclude.",
    )
    parser.add_argument(
        "--excluded-locations",
        default=None,
        help="Comma-separated location keywords to exclude.",
    )
    
    args = parser.parse_args()
    
    # Validate API key
    if not args.api_key:
        logger.error("❌ Smartlead API key not provided. Set SMARTLEAD_API_KEY env var or use --api-key")
        sys.exit(1)
    
    # Show database config
    db_url = get_database_url()
    logger.info(f"Database: {db_url}\n")
    
    # Retry failed enrichments if requested
    if args.retry_failed:
        logger.info("Resetting failed enrichments for retry...\n")
        db = DatabaseManager()
        enrichment_mgr = EnrichmentManager(db)
        reset_count = enrichment_mgr.reset_failed_enrichments(args.job_id)
        logger.info(f"Reset {reset_count} failed enrichments\n")
    
    # Run enrichment
    success = enrich_job(
        args.job_id,
        args.api_key,
        rate_limit=args.rate_limit,
        dry_run=args.dry_run,
        company_filter_hook_enabled=(
            None if args.company_filter_hook is None else args.company_filter_hook == "on"
        ),
        company_filter_min_employees=args.company_min_employees,
        company_filter_max_employees=args.company_max_employees,
        excluded_industries=_parse_csv(args.excluded_industries),
        excluded_locations=_parse_csv(args.excluded_locations),
    )
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
