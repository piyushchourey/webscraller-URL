from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


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


@dataclass
class BulkJob:
    """Represents a bulk processing job with multiple URLs."""
    job_id: str
    status: str  # "pending", "processing", "completed", "failed", "cancelled"
    total_urls: int
    processed_urls: int = 0
    failed_urls: int = 0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None
    batch_size: int = 50
    current_batch: int = 0
    total_batches: int = 0
    progress_percentage: float = 0.0
    error_summary: Dict[str, int] = field(default_factory=dict)


@dataclass
class ProcessingTask:
    """Represents a single URL processing task."""
    task_id: str
    job_id: str
    url: str
    batch_number: int
    status: str  # "queued", "scraping", "analyzing", "completed", "failed"
    metadata: Optional[Dict[str, Any]] = None
    scraped_data: Optional[ScrapedContent] = None
    ai_result: Optional[AnalysisResult] = None
    enriched_data: Optional['EnrichedCompanyData'] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    processing_time: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None


@dataclass
class ProcessingBatch:
    """Represents a batch of tasks for processing."""
    batch_id: str
    job_id: str
    batch_number: int
    tasks: List[ProcessingTask]
    status: str  # "pending", "processing", "completed", "failed"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    success_count: int = 0
    failure_count: int = 0


@dataclass
class EnrichedCompanyData:
    """Structured data extracted from company websites."""
    url: str
    company_name: str = ""
    location: str = ""
    website: str = ""
    company_url: str = ""
    industry: str = ""
    company_size: str = ""  # '1-10', '11-50', '51-200', '201-500', '501-1000', '1001-5000', '5000+'
    segmentation: str = ""  # 'Enterprise', 'Mid-market', 'Small-mid'
    salesforce_products: List[str] = field(default_factory=list)
    key_persons: List[Dict[str, str]] = field(default_factory=list)
    raw_scraped_text: str = ""
    ai_analysis: str = ""
    processing_status: str = "pending"
    error_message: Optional[str] = None
    confidence_score: float = 0.0
    extra_data: Optional[Dict[str, Any]] = None

    @property
    def platform_products(self) -> List[str]:
        """Generic alias for platform-specific products/features mentioned."""
        return self.salesforce_products

    def to_dict(self) -> Dict:
        """Convert to dictionary for Excel export."""
        product_text = ", ".join(self.salesforce_products) if self.salesforce_products else ""
        return {
            "Original_URL": self.url,
            "Company_Name": self.company_name,
            "Company_URL": self.company_url or self.website,
            "Location": self.location,
            "Industry": self.industry,
            "Company_Size": self.company_size,
            "Segmentation": self.segmentation,
            "Platform_Products": product_text,
            "Salesforce_Products": product_text,
            "Key_Persons_JSON": str(self.key_persons),
            "Scraped_Text_Preview": self.raw_scraped_text[:500] + "..." if len(self.raw_scraped_text) > 500 else self.raw_scraped_text,
            "AI_Analysis_Summary": self.ai_analysis[:1000] + "..." if len(self.ai_analysis) > 1000 else self.ai_analysis,
            "Processing_Status": self.processing_status,
            "Error_Message": self.error_message or "",
            "Confidence_Score": self.confidence_score
        }