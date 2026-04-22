import logging
from abc import ABC, abstractmethod
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from readability import Document
import trafilatura

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

logger = logging.getLogger(__name__)


class ContentExtractor(ABC):
    """Base class for content extraction strategies."""

    @abstractmethod
    def extract_text(self, html: str, url: str) -> str:
        ...

    @abstractmethod
    def extract_title(self, html: str) -> str:
        ...


class TrafilaturaExtractor(ContentExtractor):
    """Primary extractor using trafilatura — best for article-like pages."""

    def extract_text(self, html: str, url: str) -> str:
        result = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=True,
            no_fallback=False,
            favor_precision=False,
            url=url,
        )
        return result or ""

    def extract_title(self, html: str) -> str:
        metadata = trafilatura.extract_metadata(html)
        return metadata.title if metadata and metadata.title else ""


class ReadabilityExtractor(ContentExtractor):
    """Fallback extractor using readability-lxml (Mozilla Readability port)."""

    def extract_text(self, html: str, url: str) -> str:
        doc = Document(html, url=url)
        summary_html = doc.summary()
        soup = BeautifulSoup(summary_html, "lxml")
        return soup.get_text(separator="\n", strip=True)

    def extract_title(self, html: str) -> str:
        doc = Document(html)
        return doc.title() or ""


class PlaywrightExtractor(ContentExtractor):
    """Advanced extractor using Playwright for JavaScript-rendered content."""

    def __init__(self, headless: bool = True):
        if not PLAYWRIGHT_AVAILABLE:
            raise ImportError("Playwright not installed. Run: pip install playwright && playwright install")
        self.headless = headless

    def extract_text(self, html: str, url: str) -> str:
        """Render page with Playwright and extract content."""
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=self.headless)
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    viewport={"width": 1280, "height": 720}
                )
                page = context.new_page()

                # Set longer timeout for JS-heavy sites
                page.set_default_timeout(30000)

                try:
                    page.goto(url, wait_until="networkidle")
                    # Wait a bit more for dynamic content
                    page.wait_for_timeout(2000)

                    # Try trafilatura on the rendered HTML
                    rendered_html = page.content()
                    result = trafilatura.extract(
                        rendered_html,
                        include_comments=False,
                        include_tables=True,
                        no_fallback=False,
                        favor_precision=False,
                        url=url,
                    )
                    return result or ""

                except Exception as e:
                    logger.warning(f"Playwright extraction failed for {url}: {e}")
                    return ""
                finally:
                    browser.close()

        except Exception as e:
            logger.error(f"Playwright setup failed: {e}")
            return ""

    def extract_title(self, html: str) -> str:
        """Extract title from rendered page."""
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=self.headless)
                context = browser.new_context()
                page = context.new_page()

                try:
                    page.goto(html if html.startswith(('http://', 'https://')) else f"data:text/html,{html}",
                             wait_until="domcontentloaded")
                    title = page.title()
                    return title or ""
                finally:
                    browser.close()

        except Exception as e:
            logger.error(f"Playwright title extraction failed: {e}")
            return ""


class MetadataExtractor:
    """Extracts structured metadata from HTML using BeautifulSoup."""

    def __init__(self, html: str, base_url: str):
        self._soup = BeautifulSoup(html, "lxml")
        self._base_url = base_url

    @property
    def meta_description(self) -> str:
        tag = self._soup.find("meta", attrs={"name": "description"})
        if tag and tag.get("content"):
            return tag["content"].strip()
        og = self._soup.find("meta", attrs={"property": "og:description"})
        if og and og.get("content"):
            return og["content"].strip()
        return ""

    @property
    def author(self) -> str:
        tag = self._soup.find("meta", attrs={"name": "author"})
        if tag and tag.get("content"):
            return tag["content"].strip()
        return ""

    @property
    def publish_date(self) -> str:
        for attr in ("article:published_time", "datePublished", "date"):
            tag = self._soup.find("meta", attrs={"property": attr}) or self._soup.find(
                "meta", attrs={"name": attr}
            )
            if tag and tag.get("content"):
                return tag["content"].strip()
        time_tag = self._soup.find("time", attrs={"datetime": True})
        if time_tag:
            return time_tag["datetime"].strip()
        return ""

    @property
    def links(self) -> list[str]:
        urls: list[str] = []
        for a in self._soup.find_all("a", href=True):
            href = a["href"]
            absolute = urljoin(self._base_url, href)
            if absolute.startswith(("http://", "https://")):
                urls.append(absolute)
        return list(dict.fromkeys(urls))  # dedupe, preserve order

    @property
    def images(self) -> list[str]:
        urls: list[str] = []
        for img in self._soup.find_all("img", src=True):
            absolute = urljoin(self._base_url, img["src"])
            if absolute.startswith(("http://", "https://")):
                urls.append(absolute)
        return list(dict.fromkeys(urls))