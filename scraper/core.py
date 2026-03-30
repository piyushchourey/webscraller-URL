import logging
from typing import Optional

import requests
import validators

from scraper.extractors import (
    ContentExtractor,
    MetadataExtractor,
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
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
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
        ]

    # ----- public API --------------------------------------------------------

    def scrape(self, url: str) -> ScrapedContent:
        """Scrape *url* and return a ``ScrapedContent`` object.

        Raises ``ScraperError`` on invalid input or network failures.
        """
        url = self._validate_url(url)
        html, status_code = self._fetch(url)
        title, main_text = self._extract(html, url)
        meta = MetadataExtractor(html, url)

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

    def _fetch(self, url: str) -> tuple[str, int]:
        try:
            resp = self._session.get(
                url,
                timeout=self._timeout,
                allow_redirects=True,
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