"""Smartlead API integration adapter."""

import logging
import time
from urllib.parse import urlparse
from typing import Optional, Dict, Any, List
from datetime import datetime

import requests

from scraper.enrichment.company_filters import (
    CompanyFilterConfig,
    build_filter_engine,
    extract_company_filter_context,
)

logger = logging.getLogger(__name__)


class SmartleadAdapter:
    """Adapter for Smartlead API integration."""

    def __init__(
        self,
        api_key: str,
        rate_limit_per_minute: int = 60,
        company_filter_hook_enabled: Optional[bool] = None,
        company_filter_min_employees: Optional[int] = None,
        company_filter_max_employees: Optional[int] = None,
        excluded_industries: Optional[List[str]] = None,
        excluded_locations: Optional[List[str]] = None,
    ):
        """
        Initialize Smartlead adapter.
        
        Args:
            api_key: Smartlead API key
            rate_limit_per_minute: API calls per minute to respect rate limits
            company_filter_hook_enabled: Optional override to enable/disable
                pre-find-emails exclusion hook.
            company_filter_min_employees: Optional override for min size exclusion.
            company_filter_max_employees: Optional override for max size exclusion.
            excluded_industries: Optional industry keyword exclusions.
            excluded_locations: Optional location keyword exclusions.
        """
        self.api_key = api_key
        self.base_url = "https://prospect-api.smartlead.ai"
        self.search_contacts_path = "/api/v1/search-email-leads/search-contacts"
        self.find_emails_path = "/api/v1/search-email-leads/search-contacts/find-emails"
        self.find_emails_batch_size = 10
        self.default_levels = ["VP-Level", "C-Level", "Manager-Level", "Director-Level"]
        self.department_filters = ["Finance & Administration","Engineering","Other","Operations","IT & IS"]
        self.rate_limit_per_minute = rate_limit_per_minute
        self.min_delay_between_requests = 60.0 / rate_limit_per_minute
        self.last_request_time = 0
        self.last_request_error: Optional[Dict[str, Any]] = None
        # Timeout settings: find_emails needs more time due to email verification work
        self.search_contacts_timeout = 15
        self.find_emails_timeout = 30  # Allow more time for email verification
        self.max_retries = 5  # Increase retries to handle transient timeouts
        filter_config = CompanyFilterConfig.from_env()
        if company_filter_min_employees is not None:
            filter_config.min_employees = int(company_filter_min_employees)
        if company_filter_max_employees is not None:
            filter_config.max_employees = int(company_filter_max_employees)
        if excluded_industries is not None:
            filter_config.industry_exclusions = excluded_industries
        if excluded_locations is not None:
            filter_config.location_exclusions = excluded_locations
        self.company_filter_engine = build_filter_engine(filter_config)
        self.company_filter_hook_enabled = (
            self.company_filter_engine.enabled
            if company_filter_hook_enabled is None
            else bool(company_filter_hook_enabled)
        )

    def _wait_for_rate_limit(self):
        """Ensure rate limiting between API requests."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_delay_between_requests:
            wait_time = self.min_delay_between_requests - elapsed
            logger.debug(f"Rate limiting: waiting {wait_time:.2f}s")
            time.sleep(wait_time)

    def _make_request(
        self,
        endpoint: str,
        method: str = "GET",
        payload: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Make HTTP request to Smartlead API with retry logic.
        
        Args:
            endpoint: API endpoint (e.g., "/v1/find-contact")
            method: HTTP method (GET, POST, etc.)
            payload: Request payload
            timeout: Request timeout in seconds (uses endpoint-specific defaults if None)
            
        Returns:
            Response JSON dict or None on error
        """
        self._wait_for_rate_limit()
        self.last_request_error = None
        
        # Use endpoint-specific timeout if not provided
        if timeout is None:
            if "find-emails" in endpoint:
                timeout = self.find_emails_timeout
            else:
                timeout = self.search_contacts_timeout
        
        url = f"{self.base_url}{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        
        retry_count = 0
        
        while retry_count < self.max_retries:
            try:
                self.last_request_time = time.time()
                
                if method == "GET":
                    response = requests.get(url, headers=headers, params=payload, timeout=timeout)
                elif method == "POST":
                    response = requests.post(url, headers=headers, json=payload, timeout=timeout)
                else:
                    logger.error(f"Unsupported HTTP method: {method}")
                    self.last_request_error = {
                        "type": "config",
                        "message": f"Unsupported HTTP method: {method}",
                    }
                    return None
                
                response.raise_for_status()
                return response.json()
                
            except requests.exceptions.Timeout:
                retry_count += 1
                wait_time = 2 ** retry_count  # exponential backoff: 2s, 4s, 8s, 16s, 32s
                logger.warning(f"Request timeout (attempt {retry_count}/{self.max_retries}). Retrying in {wait_time}s...")
                self.last_request_error = {
                    "type": "timeout",
                    "message": f"Request timeout (attempt {retry_count}/{self.max_retries})",
                }
                if retry_count < self.max_retries:
                    time.sleep(wait_time)
                    
            except requests.exceptions.HTTPError as e:
                if response.status_code == 429:  # Rate limited
                    retry_count += 1
                    wait_time = 2 ** retry_count
                    logger.warning(f"Rate limited (attempt {retry_count}/{self.max_retries}). Retrying in {wait_time}s...")
                    self.last_request_error = {
                        "type": "rate_limit",
                        "status_code": 429,
                        "message": str(e),
                    }
                    if retry_count < self.max_retries:
                        time.sleep(wait_time)
                else:
                    logger.error(f"HTTP error: {e}")
                    self.last_request_error = {
                        "type": "http",
                        "status_code": response.status_code,
                        "message": str(e),
                    }
                    return None
                    
            except Exception as e:
                logger.error(f"Request error: {e}")
                self.last_request_error = {
                    "type": "exception",
                    "message": str(e),
                }
                return None
        
        logger.error(f"Failed after {self.max_retries} retries")
        if not self.last_request_error:
            self.last_request_error = {
                "type": "retry_exhausted",
                "message": f"Failed after {self.max_retries} retries",
            }
        return None

    @staticmethod
    def _normalize_domain(domain_or_url: Optional[str]) -> Optional[str]:
        """Normalize URL/domain into bare domain string."""
        if not domain_or_url:
            return None
        raw_value = domain_or_url.strip()
        if not raw_value:
            return None
        if "://" not in raw_value:
            raw_value = f"https://{raw_value}"
        parsed = urlparse(raw_value)
        domain = (parsed.netloc or parsed.path or "").lower().strip()
        if domain.startswith("www."):
            domain = domain[4:]
        return domain or None

    def search_contacts(
        self,
        domain: Optional[str] = None,
        company_name: Optional[str] = None,
        limit: int = 30,
        levels: Optional[List[str]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Search contacts using company domain only.
        """
        normalized_domain = self._normalize_domain(domain)
        if not normalized_domain:
            logger.error("search_contacts requires a valid domain")
            return None

        payload: Dict[str, Any] = {
            "limit": limit,
            "level": levels or self.default_levels,
            "department": self.department_filters,
            "companyDomain": [normalized_domain],
        }

        endpoint = f"{self.search_contacts_path}?api_key={self.api_key}"
        response = self._make_request(endpoint, method="POST", payload=payload)
        if response and response.get("success"):
            response["lookup_method"] = "domain"
            return response
        return None

    def find_emails(self, contacts: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
        """Find emails for a list of contacts."""
        if not contacts:
            return None

        endpoint = f"{self.find_emails_path}?api_key={self.api_key}"
        all_rows: List[Dict[str, Any]] = []

        for index in range(0, len(contacts), self.find_emails_batch_size):
            contact_batch = contacts[index:index + self.find_emails_batch_size]
            payload = {"contacts": contact_batch}
            response = self._make_request(endpoint, method="POST", payload=payload)

            if not response or not response.get("success"):
                return None

            all_rows.extend(response.get("data") or [])

        return {
            "success": True,
            "message": "Find emails completed",
            "data": all_rows,
        }

    def enrich_company_full(
        self,
        company_name: Optional[str] = None,
        domain: Optional[str] = None,
        location: Optional[str] = None,
        db=None,
    ) -> Optional[Dict[str, Any]]:
        """
        Perform full enrichment (both company data and key persons) in one call.
        
        Args:
            company_name: Company name (optional, used for metadata only)
            domain: Company domain used for contact search
            location: Company location (optional)
            
        Returns:
            Combined enrichment data or None on error
        """
        normalized_domain = self._normalize_domain(domain)
        clean_name = (company_name or "").strip()

        # Domain-only search
        search_response = self.search_contacts(domain=normalized_domain, company_name=None)
        lookup_method = "domain"

        if not search_response or not search_response.get("success"):
            return None

        contacts = search_response.get("data", {}).get("list") or []
        if not contacts:
            return None

        filter_context = extract_company_filter_context(
            contacts=contacts,
            company_location=location,
            company_industry="",
        )
        filter_decision = self.company_filter_engine.evaluate(filter_context)
        exclusion_applied = self.company_filter_hook_enabled and filter_decision.excluded

        # Check DB cache for existing emails before calling find-emails API
        cached_email_map: Dict[tuple, Dict[str, Any]] = {}
        if db is not None and normalized_domain:
            logger.info(
                "[EMAIL CACHE] Checking DB for existing emails | company=%s | domain=%s | contacts_to_check=%d",
                clean_name or normalized_domain, normalized_domain, len(contacts),
            )
            cached_email_map = db.get_cached_emails_by_domain(normalized_domain)
            if cached_email_map:
                logger.info(
                    "[EMAIL CACHE] HIT | domain=%s | cached_contacts=%d | persons=%s",
                    normalized_domain,
                    len(cached_email_map),
                    [f"{k[0]} {k[1]}" for k in cached_email_map.keys()],
                )
            else:
                logger.info(
                    "[EMAIL CACHE] MISS | domain=%s | no existing emails found in DB",
                    normalized_domain,
                )
        else:
            logger.info(
                "[EMAIL CACHE] Skipped DB check | company=%s | domain=%s | db_available=%s",
                clean_name or normalized_domain, normalized_domain, db is not None,
            )

        # Build find-emails input — only for contacts NOT already in cache
        email_contacts: List[Dict[str, str]] = []
        for contact in contacts:
            first_name = (contact.get("firstName") or "").strip()
            last_name = (contact.get("lastName") or "").strip()
            contact_company_domain = self._normalize_domain(
                (contact.get("company") or {}).get("website")
            ) or normalized_domain

            if not first_name or not last_name or not contact_company_domain:
                continue

            key = (first_name.lower(), last_name.lower(), contact_company_domain)
            if key not in cached_email_map:
                email_contacts.append(
                    {
                        "firstName": first_name,
                        "lastName": last_name,
                        "companyDomain": contact_company_domain,
                    }
                )

        cache_hits = len(cached_email_map)
        logger.info(
            "[EMAIL CACHE] Split result | domain=%s | from_cache=%d | needs_api=%d",
            normalized_domain, cache_hits, len(email_contacts),
        )

        find_emails_response = None
        if exclusion_applied:
            logger.info(
                "[SMARTLEAD API] SKIPPED find_emails | company=%s | domain=%s | reason=exclusion_rules | rules=%s",
                clean_name or normalized_domain or "unknown_company",
                normalized_domain,
                "; ".join(filter_decision.reasons),
            )
        elif email_contacts:
            logger.info(
                "[SMARTLEAD API] Calling find_emails | company=%s | domain=%s | contacts=%d | persons=%s",
                clean_name or normalized_domain,
                normalized_domain,
                len(email_contacts),
                [f"{c['firstName']} {c['lastName']}" for c in email_contacts],
            )
            find_emails_response = self.find_emails(email_contacts)
            logger.info(
                "[SMARTLEAD API] find_emails response | domain=%s | success=%s | emails_returned=%d",
                normalized_domain,
                bool(find_emails_response and find_emails_response.get("success")),
                len((find_emails_response or {}).get("data") or []),
            )
        else:
            logger.info(
                "[SMARTLEAD API] find_emails not needed | domain=%s | all %d contact(s) served from cache",
                normalized_domain, cache_hits,
            )

        if email_contacts and not exclusion_applied and not find_emails_response:
            error_type = (self.last_request_error or {}).get("type")
            if error_type in {"http", "rate_limit"}:
                logger.warning(
                    "find_emails failed with HTTP error; treating enrichment as failed to allow retry."
                )
                return None

        # Seed email_map from DB cache first, then overlay fresh API results
        email_map: Dict[tuple, Dict[str, Any]] = dict(cached_email_map)
        if find_emails_response and find_emails_response.get("success"):
            for row in find_emails_response.get("data") or []:
                key = (
                    (row.get("firstName") or "").strip().lower(),
                    (row.get("lastName") or "").strip().lower(),
                    self._normalize_domain(row.get("companyDomain")) or "",
                )
                email_map[key] = row

        contacts_with_email: List[Dict[str, Any]] = []
        valid_email_count = 0
        for contact in contacts:
            enriched_contact = dict(contact)
            first = (contact.get("firstName") or "").strip().lower()
            last = (contact.get("lastName") or "").strip().lower()
            company_domain = self._normalize_domain((contact.get("company") or {}).get("website")) or (normalized_domain or "")
            email_info = email_map.get((first, last, company_domain))

            if email_info:
                enriched_contact["email_id"] = email_info.get("email_id")
                enriched_contact["email_status"] = email_info.get("status")
                enriched_contact["verification_status"] = email_info.get("verification_status")
                enriched_contact["email_source"] = email_info.get("source")
                if email_info.get("email_id") and str(email_info.get("verification_status", "")).lower() == "valid":
                    valid_email_count += 1

            contacts_with_email.append(enriched_contact)

        logger.info(
            "[ENRICHMENT SUMMARY] company=%s | domain=%s | total_contacts=%d | cache_hits=%d | api_calls=%d | valid_emails=%d",
            clean_name or normalized_domain,
            normalized_domain,
            len(contacts),
            cache_hits,
            len(email_contacts),
            valid_email_count,
        )

        return {
            "lookup_method": lookup_method,
            "company_context": {
                "company_name": clean_name,
                "company_domain": normalized_domain,
                "location": location,
            },
            "exclusion_applied": exclusion_applied,
            "exclusion_reasons": filter_decision.reasons if exclusion_applied else [],
            "rule_ids": filter_decision.rule_ids if exclusion_applied else [],
            "headcount_observed": filter_context.get("headcount_raw") or "",
            "filter_evaluation": filter_decision.as_dict(),
            "find_emails_skipped": exclusion_applied,
            "search_contacts": search_response,
            "find_emails": find_emails_response,
            "contacts_enriched": contacts_with_email,
            "stats": {
                "contacts_found": len(contacts),
                "email_cache_hits": cache_hits,
                "email_requested": 0 if exclusion_applied else len(email_contacts),
                "valid_emails_found": valid_email_count,
            },
            "enriched_at": datetime.utcnow().isoformat(),
        }
