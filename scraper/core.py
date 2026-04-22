import logging
from typing import Optional

import requests
import validators
from urllib.parse import urlsplit, urlunsplit

from scraper.extractors import (
    ContentExtractor,
    MetadataExtractor,
    PLAYWRIGHT_AVAILABLE,
    PlaywrightExtractor,
    ReadabilityExtractor,
    TrafilaturaExtractor,
)
from scraper.models import ScrapedContent

logger = logging.getLogger(__name__)

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
    "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}

REQUEST_TIMEOUT = 15  # seconds
MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10 MB


class ScraperError(Exception):
    """Domain-specific error raised by WebScraper."""


class WebScraper:
    """Fetches a URL and extracts structured textual content."""

    def __init__(
        self,
        *,
        timeout: int = REQUEST_TIMEOUT,
        headers: Optional[dict[str, str]] = None,
    ):
        self._timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(headers or _DEFAULT_HEADERS)
        self._extractors: list[ContentExtractor] = [
            TrafilaturaExtractor(),
            ReadabilityExtractor(),
            PlaywrightExtractor(),
        ]

    # ----- public API --------------------------------------------------------

    def scrape(self, url: str) -> ScrapedContent:
        """Scrape *url* and return a ``ScrapedContent`` object.

        Raises ``ScraperError`` on invalid input or network failures.
        """
        url = self._validate_url(url)
        parsed = urlsplit(url)
        fragment = parsed.fragment
        fetch_url = urlunsplit(parsed._replace(fragment="")) if fragment else url

        try:
            # Try regular HTTP request first
            html, status_code = self._fetch(fetch_url)
        except ScraperError as e:
            if "403" in str(e) and PLAYWRIGHT_AVAILABLE:
                # Try Playwright for 403 errors (likely anti-bot protection)
                logger.info(f"Regular request failed with 403, trying Playwright for {fetch_url}")
                try:
                    playwright_extractor = PlaywrightExtractor()
                    html = playwright_extractor.extract_text("", fetch_url)  # Empty html, use URL
                    if not html:
                        raise ScraperError("Playwright extraction also failed")
                    status_code = 200  # Assume success if we got content
                except Exception as pw_e:
                    logger.error(f"Playwright fallback failed: {pw_e}")
                    raise e  # Re-raise original error
            else:
                raise

        title, main_text = self._extract(html, fetch_url)
        if fragment:
            fragment_text = self._extract_fragment(html, fragment)
            if fragment_text:
                main_text = fragment_text

        meta = MetadataExtractor(html, fetch_url)

        return ScrapedContent(
            url=url,
            title=title,
            main_text=main_text,
            meta_description=meta.meta_description,
            author=meta.author,
            publish_date=meta.publish_date,
            links=meta.links[:50],
            images=meta.images[:20],
            status_code=status_code,
        )

    # ----- private helpers ---------------------------------------------------

    @staticmethod
    def _validate_url(url: str) -> str:
        url = url.strip()
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        if not validators.url(url):
            raise ScraperError(f"Invalid URL: {url}")
        return url

    @staticmethod
    def _extract_fragment(html: str, fragment: str) -> str:
        """Extract a specific section from HTML based on element id."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")
        node = soup.find(id=fragment)
        if not node:
            return ""

        # If fragment marker is heading, include sibling content until next heading
        content = [node.get_text(" ", strip=True)]
        if node.name and node.name.startswith("h"):
            for sibling in node.next_siblings:
                if hasattr(sibling, "name") and sibling.name and sibling.name.startswith("h"):
                    break
                if hasattr(sibling, "get_text"):
                    text = sibling.get_text(" ", strip=True)
                    if text:
                        content.append(text)
        return "\n\n".join([c for c in content if c])

    def _fetch(self, url: str) -> tuple[str, int]:
        try:
            import time
            import random
            
            # Add small random delay to avoid rate limiting (0.5-2 seconds)
            time.sleep(random.uniform(0.5, 2.0))
            
            # Enhanced cookies for various consent systems
            cookies = {
                "cookie_consent": "accepted",
                "cookieConsent": "true", 
                "gdpr_consent": "accepted",
                "cc_cookie": "true",
                "visitor_id": str(random.randint(1000000, 9999999)),
                "session_id": str(random.randint(1000000, 9999999)),
            }
            
            # Add Referer header for Salesforce domains
            headers = {}
            if "salesforce.com" in url:
                headers["Referer"] = "https://www.salesforce.com/"
            
            resp = self._session.get(
                url,
                timeout=self._timeout,
                allow_redirects=True,
                cookies=cookies,
                headers=headers,
            )
            resp.raise_for_status()
            if len(resp.content) > MAX_CONTENT_LENGTH:
                raise ScraperError("Response too large (>10 MB).")
            resp.encoding = resp.apparent_encoding or "utf-8"
            return resp.text, resp.status_code
        except requests.RequestException as exc:
            raise ScraperError(f"Failed to fetch URL: {exc}") from exc

    def _extract(self, html: str, url: str) -> tuple[str, str]:
        """Try each extractor in priority order; return (title, text)."""
        for extractor in self._extractors:
            try:
                text = extractor.extract_text(html, url)
                if text and len(text.split()) > 20:
                    title = extractor.extract_title(html) or url
                    return title, text
            except Exception:
                logger.debug("Extractor %s failed, trying next", type(extractor).__name__, exc_info=True)
        # last-resort: return whatever the first extractor got
        return self._extractors[0].extract_title(html) or url, (
            self._extractors[0].extract_text(html, url) or "No readable content found."
        )