"""SQLAlchemy ORM models for the webscraper database."""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    create_engine,
    event,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class ProcessingJob(Base):
    """Represents a bulk processing job with multiple URLs."""

    __tablename__ = "processing_jobs"

    job_id = Column(Text, primary_key=True)
    job_name = Column(Text, nullable=True)
    status = Column(Text, nullable=False, default="pending")
    # pending, processing, completed, failed, cancelled
    total_urls = Column(Integer, nullable=False)
    processed_urls = Column(Integer, default=0)
    failed_urls = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    batch_size = Column(Integer, default=50)
    current_batch = Column(Integer, default=0)
    total_batches = Column(Integer, default=0)
    progress_percentage = Column(Float, default=0.0)
    error_summary = Column(JSON, default={})
    config = Column(JSON, default={})

    # Relationships
    tasks = relationship("ProcessingTask", back_populates="job", cascade="all, delete-orphan")
    batches = relationship("ProcessingBatch", back_populates="job", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<ProcessingJob {self.job_id} name={self.job_name} ({self.status})>"


class ProcessingBatch(Base):
    """Represents a batch of tasks within a job."""

    __tablename__ = "processing_batches"

    batch_id = Column(Text, primary_key=True)
    job_id = Column(Text, ForeignKey("processing_jobs.job_id"), nullable=False)
    batch_number = Column(Integer, nullable=False)
    status = Column(Text, nullable=False, default="pending")
    # pending, processing, completed, failed
    task_count = Column(Integer, nullable=False)
    success_count = Column(Integer, default=0)
    failure_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    job = relationship("ProcessingJob", back_populates="batches")
    tasks = relationship("ProcessingTask", back_populates="batch")

    __table_args__ = (UniqueConstraint("job_id", "batch_number", name="uq_job_batch_number"),)

    def __repr__(self):
        return f"<ProcessingBatch {self.batch_id} (Batch {self.batch_number})>"


class ProcessingTask(Base):
    """Represents a single URL processing task."""

    __tablename__ = "processing_tasks"

    task_id = Column(Text, primary_key=True)
    job_id = Column(Text, ForeignKey("processing_jobs.job_id"), nullable=False)
    batch_id = Column(Text, ForeignKey("processing_batches.batch_id"), nullable=True)
    original_url = Column(Text, nullable=False)
    batch_number = Column(Integer, nullable=False)
    status = Column(Text, nullable=False, default="queued")
    # queued, scraping, analyzing, completed, failed
    retry_count = Column(Integer, default=0)
    processing_time = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)

    # Relationships
    job = relationship("ProcessingJob", back_populates="tasks")
    batch = relationship("ProcessingBatch", back_populates="tasks")
    company_data = relationship("CompanyData", back_populates="task", uselist=False, cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("job_id", "original_url", name="uq_job_url"),)

    def __repr__(self):
        return f"<ProcessingTask {self.task_id} ({self.status})>"


class CompanyData(Base):
    """Main company information extracted from websites."""

    __tablename__ = "company_data"

    company_id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Text, ForeignKey("processing_tasks.task_id"), nullable=False)
    original_url = Column(Text, nullable=False)
    company_name = Column(Text, nullable=True)
    company_url = Column(Text, nullable=True)
    location = Column(Text, nullable=True)
    industry = Column(Text, nullable=True)
    company_size = Column(Text, nullable=True)
    # '1-10', '11-50', '51-200', '201-500', '501-1000', '1001-5000', '5000+'
    segmentation = Column(Text, nullable=True)
    # 'Enterprise', 'Mid-market', 'Small-mid'
    salesforce_products = Column(JSON, default=[])
    key_persons = relationship("KeyPerson", back_populates="company", cascade="all, delete-orphan")
    raw_scraped_text = Column(Text, nullable=True)
    ai_analysis = Column(Text, nullable=True)
    confidence_score = Column(Float, default=0.0)
    processing_status = Column(Text, default="pending")
    error_message = Column(Text, nullable=True)
    
    extra_data = Column(JSON, nullable=True)  # All extra Excel columns preserved as JSON

    # Smartlead enrichment fields
    smartlead_enrichment = Column(JSON, nullable=True)  # Full Smartlead API response
    enrichment_status = Column(Text, default="pending")  # pending/processing/enriched/failed
    enrichment_retry_count = Column(Integer, default=0)
    enrichment_last_error = Column(Text, nullable=True)
    enrichment_updated_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    task = relationship("ProcessingTask", back_populates="company_data")

    __table_args__ = (UniqueConstraint("task_id", name="uq_task_company"),)

    def __repr__(self):
        return f"<CompanyData {self.company_id} - {self.company_name}>"


class KeyPerson(Base):
    """Key persons extracted from company websites."""

    __tablename__ = "key_persons"

    person_id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey("company_data.company_id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False)
    title = Column(Text, nullable=True)
    contact = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    company = relationship("CompanyData", back_populates="key_persons")

    __table_args__ = (UniqueConstraint("company_id", "name", "title", name="uq_company_person"),)

    def __repr__(self):
        return f"<KeyPerson {self.name} ({self.title})>"
