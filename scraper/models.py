from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ScrapedContent:
    url: str
    title: str
    main_text: str
    meta_description: str = ""
    author: str = ""
    publish_date: str = ""
    links: list[str] = field(default_factory=list)
    images: list[str] = field(default_factory=list)
    scraped_at: str = field(default_factory=lambda: datetime.now().isoformat())
    word_count: int = 0
    status_code: int = 0

    def __post_init__(self):
        self.word_count = len(self.main_text.split()) if self.main_text else 0


@dataclass
class AnalysisResult:
    prompt_used: str
    response_text: str
    model: str
    tokens_used: int = 0
    source_url: str = ""