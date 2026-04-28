"""Smartlead API integration adapter."""

import logging
import time
from urllib.parse import urlparse
from typing import Optional, Dict, Any, List
from datetime import datetime

import requests

logger = logging.getLogger(__name__)


class SmartleadAdapter:
    """Adapter for Smartlead API integration."""

    def __init__(self, api_key: str, rate_limit_per_minute: int = 60):
        """
        Initialize Smartlead adapter.
        
        Args:
            api_key: Smartlead API key
            rate_limit_per_minute: API calls per minute to respect rate limits
        """
        self.api_key = api_key
        self.base_url = "https://prospect-api.smartlead.ai"
        self.search_contacts_path = "/api/v1/search-email-leads/search-contacts"
        self.find_emails_path = "/api/v1/search-email-leads/search-contacts/find-emails"
        self.find_emails_batch_size = 10
        self.default_levels = ["VP-Level", "C-Level", "Manager-Level", "Director-Level"]
        self.rate_limit_per_minute = rate_limit_per_minute
        self.min_delay_between_requests = 60.0 / rate_limit_per_minute
        self.last_request_time = 0
        self.last_request_error: Optional[Dict[str, Any]] = None

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
        timeout: int = 10,
    ) -> Optional[Dict[str, Any]]:
        """
        Make HTTP request to Smartlead API with retry logic.
        
        Args:
            endpoint: API endpoint (e.g., "/v1/find-contact")
            method: HTTP method (GET, POST, etc.)
            payload: Request payload
            timeout: Request timeout in seconds
            
        Returns:
            Response JSON dict or None on error
        """
        self._wait_for_rate_limit()
        self.last_request_error = None
        
        url = f"{self.base_url}{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
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
                wait_time = 2 ** retry_count  # exponential backoff: 2s, 4s, 8s
                logger.warning(f"Request timeout (attempt {retry_count}/{max_retries}). Retrying in {wait_time}s...")
                self.last_request_error = {
                    "type": "timeout",
                    "message": f"Request timeout (attempt {retry_count}/{max_retries})",
                }
                if retry_count < max_retries:
                    time.sleep(wait_time)
                    
            except requests.exceptions.HTTPError as e:
                if response.status_code == 429:  # Rate limited
                    retry_count += 1
                    wait_time = 2 ** retry_count
                    logger.warning(f"Rate limited (attempt {retry_count}/{max_retries}). Retrying in {wait_time}s...")
                    self.last_request_error = {
                        "type": "rate_limit",
                        "status_code": 429,
                        "message": str(e),
                    }
                    if retry_count < max_retries:
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
        
        logger.error(f"Failed after {max_retries} retries")
        if not self.last_request_error:
            self.last_request_error = {
                "type": "retry_exhausted",
                "message": f"Failed after {max_retries} retries",
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
        levels: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Search contacts with priority: companyDomain first, then companyName fallback.
        """
        normalized_domain = self._normalize_domain(domain)
        clean_name = (company_name or "").strip()
        if not normalized_domain and not clean_name:
            logger.error("search_contacts requires either domain or company_name")
            return None

        payload: Dict[str, Any] = {
            "limit": limit,
            "level": levels or self.default_levels,
        }
        lookup_method = "domain"
        if normalized_domain:
            payload["companyDomain"] = [normalized_domain]
        else:
            payload["companyName"] = [clean_name]
            lookup_method = "company_name"

        endpoint = f"{self.search_contacts_path}?api_key={self.api_key}"
        response = self._make_request(endpoint, method="POST", payload=payload)
        if response and response.get("success"):
            response["lookup_method"] = lookup_method
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
    ) -> Optional[Dict[str, Any]]:
        """
        Perform full enrichment (both company data and key persons) in one call.
        
        Args:
            company_name: Company name (optional)
            domain: Company domain (required, if company_name not provided)
            location: Company location (optional)
            
        Returns:
            Combined enrichment data or None on error
        """
        normalized_domain = self._normalize_domain(domain)
        clean_name = (company_name or "").strip()

        # 1) Domain-first search
        search_response = self.search_contacts(domain=normalized_domain, company_name=None)
        lookup_method = "domain"

        # 2) Fallback to company name if domain missing/no-results
        no_results = not search_response or not (search_response.get("data", {}).get("list") or [])
        if no_results and clean_name:
            search_response = self.search_contacts(domain=None, company_name=clean_name)
            lookup_method = "company_name"

        if not search_response or not search_response.get("success"):
            return None

        contacts = search_response.get("data", {}).get("list") or []
        if not contacts:
            return None

        # Build input for find-emails endpoint.
        email_contacts: List[Dict[str, str]] = []
        for contact in contacts:
            first_name = (contact.get("firstName") or "").strip()
            last_name = (contact.get("lastName") or "").strip()
            contact_company_domain = self._normalize_domain(
                (contact.get("company") or {}).get("website")
            ) or normalized_domain

            if first_name and last_name and contact_company_domain:
                email_contacts.append(
                    {
                        "firstName": first_name,
                        "lastName": last_name,
                        "companyDomain": contact_company_domain,
                    }
                )

        find_emails_response = self.find_emails(email_contacts) if email_contacts else None
        if email_contacts and not find_emails_response:
            error_type = (self.last_request_error or {}).get("type")
            if error_type in {"http", "rate_limit"}:
                logger.warning(
                    "find_emails failed with HTTP error; treating enrichment as failed to allow retry."
                )
                return None

        email_map: Dict[tuple, Dict[str, Any]] = {}
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

        return {
            "lookup_method": lookup_method,
            "company_context": {
                "company_name": clean_name,
                "company_domain": normalized_domain,
                "location": location,
            },
            "search_contacts": search_response,
            "find_emails": find_emails_response,
            "contacts_enriched": contacts_with_email,
            "stats": {
                "contacts_found": len(contacts),
                "email_requested": len(email_contacts),
                "valid_emails_found": valid_email_count,
            },
            "enriched_at": datetime.utcnow().isoformat(),
        }
