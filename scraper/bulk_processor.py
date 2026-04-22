"""Bulk processing pipeline for handling multiple URLs in batches."""

import json
import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from scraper import WebScraper
from scraper.ai_analyzer import get_analyzer
from scraper.database import DatabaseManager
from scraper.models import (
    AnalysisResult,
    BulkJob,
    EnrichedCompanyData,
    ProcessingBatch,
    ProcessingTask,
    ScrapedContent,
)

logger = logging.getLogger(__name__)

# ── AI Prompt for Structured Extraction ──────────────────────────────────────────
STRUCTURED_EXTRACTION_PROMPT = """
Analyze the following webpage content and extract structured company information.

Please return a JSON object with the following fields:
{
  "company_name": "Exact company name as mentioned on the page",
  "company_url": "Official company website URL",
  "location": "Headquarters or primary business location (city, country)",
  "industry": "Primary industry or business sector",
  "company_size": "Company size category. Must be ONE of: '1-10', '11-50', '51-200', '201-500', '501-1000', '1001-5000', '5000+'. If unclear, estimate based on context.",
  "segmentation": "Market segmentation category. Must be ONE of: 'Enterprise', 'Mid-market', 'Small-mid'. Base on company size and market position.",
  "salesforce_products": ["List of Salesforce products mentioned (Such as Products Used Section) on the page.Look for: Sales Cloud, Service Cloud, Marketing Cloud, Commerce Cloud, Analytics Cloud, Integration Cloud, Platform, CPQ, Einstein, etc."],
  "key_persons": [
    {
      "name": "Person's full name",
      "title": "Job title/role",
      "contact": "Email or phone if available (optional)"
    }
  ],
  "confidence_score": "Confidence in extraction accuracy (0.0-1.0). 0 = no data found, 1.0 = very confident"
}

Guidelines:
- For company_size: Look for 'employees', 'team size', 'headcount' mentions. Estimate if needed.
- For segmentation: Enterprise = 500+ employees, Mid-market = 51-500 employees, Small-mid = 11-50 employees
- For Salesforce products: Only include if explicitly mentioned or strongly implied from page content
- If information is not available, use empty strings or empty arrays
- Focus on the most prominent company mentioned on the page
"""

# ── Batch Processing Configuration ──────────────────────────────────────────────
DEFAULT_BATCH_SIZE = 50
MAX_WORKERS_PER_BATCH = 3
BATCH_DELAY_SECONDS = 5  # Delay between batches
REQUEST_DELAY_SECONDS = 2  # Delay between individual requests
MAX_RETRIES = 3

class ExcelProcessor:
    """Handles Excel file operations for bulk processing."""

    @staticmethod
    def deduplicate_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Deduplicate rows by URL while preserving first-seen order."""
        unique_rows: Dict[str, Dict[str, Any]] = {}

        for row in rows:
            url = row["url"]
            if url not in unique_rows:
                unique_rows[url] = dict(row)
                continue

            existing_row = unique_rows[url]
            if not existing_row.get("segmentation") and row.get("segmentation"):
                existing_row["segmentation"] = row["segmentation"]
            if not existing_row.get("company_size") and row.get("company_size"):
                existing_row["company_size"] = row["company_size"]
            if not existing_row.get("salesforce_products") and row.get("salesforce_products"):
                existing_row["salesforce_products"] = row["salesforce_products"]

        return list(unique_rows.values())

    @staticmethod
    def read_urls_from_excel(file_path: str) -> List[Dict[str, Any]]:
        """Extract URL rows and optional metadata from Excel."""
        try:
            df = pd.read_excel(file_path)
            df.columns = [str(col).strip() for col in df.columns]
            if 'URL' not in df.columns:
                raise ValueError("Excel file must contain a 'URL' column")

            rows = []
            for _, row in df.iterrows():
                url_str = str(row['URL']).strip()
                if not url_str or not url_str.startswith(('http://', 'https://')):
                    continue

                row_metadata = {
                    "url": url_str,
                    "segmentation": "",
                    "company_size": "",
                    "salesforce_products": [],
                }

                if 'Segmentation' in df.columns:
                    segmentation_value = row['Segmentation']
                    if pd.notna(segmentation_value):
                        row_metadata['segmentation'] = str(segmentation_value).strip()

                if 'Company_Size' in df.columns or 'Company Size' in df.columns:
                    company_size_value = row.get('Company_Size', row.get('Company Size', ''))
                    if pd.notna(company_size_value):
                        row_metadata['company_size'] = str(company_size_value).strip()

                if 'Salesforce_Products' in df.columns or 'Salesforce Products' in df.columns:
                    products_value = row.get('Salesforce_Products', row.get('Salesforce Products', ''))
                    if pd.notna(products_value):
                        products_text = str(products_value).strip()
                        row_metadata['salesforce_products'] = [x.strip() for x in products_text.split(',') if x.strip()]

                rows.append(row_metadata)

            return ExcelProcessor.deduplicate_rows(rows)
        except Exception as e:
            raise ValueError(f"Failed to read Excel file: {e}")

    @staticmethod
    def write_results_to_excel(
        enriched_data: List[EnrichedCompanyData],
        output_path: str
    ) -> str:
        """Write enriched data to Excel file."""
        try:
            data_dicts = [data.to_dict() for data in enriched_data]
            df = pd.DataFrame(data_dicts)

            # Reorder columns for better readability
            column_order = [
                "Original_URL", "Company_Name", "Location", "Website",
                "Company_Size", "Segmentation", "Salesforce_Products",
                "Industry", "Key_Persons_JSON", "Confidence_Score",
                "Processing_Status", "Error_Message",
                "Scraped_Text_Preview", "AI_Analysis_Summary"
            ]

            # Only include columns that exist
            existing_columns = [col for col in column_order if col in df.columns]
            df = df[existing_columns]

            df.to_excel(output_path, index=False, engine='openpyxl')
            return output_path
        except Exception as e:
            raise RuntimeError(f"Failed to write Excel file: {e}")


class BatchProcessor:
    """Handles batch-wise processing of URLs."""

    def __init__(
        self,
        batch_size: int = DEFAULT_BATCH_SIZE,
        max_workers: int = MAX_WORKERS_PER_BATCH,
        ai_provider: str = "ollama",
        ai_model: str = "mistral:7b"
    ):
        self.batch_size = batch_size
        self.max_workers = max_workers
        self.ai_provider = ai_provider
        self.ai_model = ai_model

        # Initialize analyzers
        self.scraper = WebScraper()
        self.ai_analyzer = get_analyzer(
            provider=ai_provider,
            model=ai_model
        )

    def create_batches(self, urls: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        """Split URLs into batches."""
        return [
            urls[i:i + self.batch_size]
            for i in range(0, len(urls), self.batch_size)
        ]

    def process_single_task(self, task: ProcessingTask) -> ProcessingTask:
        """Process a single URL task with retry logic."""
        start_time = time.time()

        try:
            # Step 1: Scrape the URL
            task.status = "scraping"
            logger.info(f"Scraping: {task.url}")

            scraped_data = self.scraper.scrape(task.url)
            task.scraped_data = scraped_data

            # Step 2: AI Analysis
            task.status = "analyzing"
            logger.info(f"Analyzing: {task.url}")

            ai_result = self.ai_analyzer.analyze(
                text=scraped_data.main_text,
                user_prompt=STRUCTURED_EXTRACTION_PROMPT,
                source_url=task.url,
                page_title=scraped_data.title
            )
            task.ai_result = ai_result

            # Step 3: Parse and structure the AI response
            enriched_data = self._parse_ai_response(
                task.url,
                scraped_data,
                ai_result,
                row_metadata=task.metadata,
            )
            task.enriched_data = enriched_data

            task.status = "completed"
            task.completed_at = datetime.now().isoformat()

        except Exception as e:
            logger.error(f"Task failed for {task.url}: {e}")
            task.status = "failed"
            task.error_message = str(e)
            task.completed_at = datetime.now().isoformat()

        task.processing_time = time.time() - start_time
        return task

    def _parse_ai_response(
        self,
        url: str,
        scraped_data: ScrapedContent,
        ai_result: AnalysisResult,
        row_metadata: Optional[Dict[str, Any]] = None
    ) -> EnrichedCompanyData:
        """Parse AI response and create structured data."""
        try:
            row_metadata = row_metadata or {}
            # Try to parse JSON from AI response
            response_text = ai_result.response_text.strip()

            # Find JSON in response (AI might add extra text)
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1

            if json_start != -1 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                data = json.loads(json_str)

                return EnrichedCompanyData(
                    url=url,
                    company_name=data.get('company_name', ''),
                    company_url=data.get('company_url', ''),
                    location=data.get('location', ''),
                    website=data.get('website', '') or data.get('company_url', ''),
                    industry=data.get('industry', ''),
                    company_size=row_metadata.get('company_size') or data.get('company_size', ''),
                    segmentation=row_metadata.get('segmentation') or data.get('segmentation', ''),
                    salesforce_products=row_metadata.get('salesforce_products') or data.get('salesforce_products', []),
                    key_persons=data.get('key_persons', []),
                    raw_scraped_text=scraped_data.main_text,
                    ai_analysis=ai_result.response_text,
                    processing_status="completed",
                    confidence_score=float(data.get('confidence_score', 0.5))
                )
            else:
                # Fallback: create basic enriched data
                return EnrichedCompanyData(
                    url=url,
                    company_size=row_metadata.get('company_size', ''),
                    segmentation=row_metadata.get('segmentation', ''),
                    salesforce_products=row_metadata.get('salesforce_products', []),
                    raw_scraped_text=scraped_data.main_text,
                    ai_analysis=ai_result.response_text,
                    processing_status="completed",
                    error_message="Could not parse structured data from AI response",
                    confidence_score=0.3
                )

        except json.JSONDecodeError:
            return EnrichedCompanyData(
                url=url,
                company_size=row_metadata.get('company_size', ''),
                segmentation=row_metadata.get('segmentation', ''),
                salesforce_products=row_metadata.get('salesforce_products', []),
                raw_scraped_text=scraped_data.main_text,
                ai_analysis=ai_result.response_text,
                processing_status="completed",
                error_message="Invalid JSON in AI response",
                confidence_score=0.2
            )

    def process_batch(self, batch_urls: List[Dict[str, Any]], batch_number: int) -> List[ProcessingTask]:
        """Process a single batch of URLs."""
        logger.info(f"Processing batch {batch_number} with {len(batch_urls)} URLs")

        # Create tasks for this batch
        tasks = []
        for i, row in enumerate(batch_urls):
            url = row['url'] if isinstance(row, dict) else str(row)
            metadata = row if isinstance(row, dict) else None
            task = ProcessingTask(
                task_id=f"task_{batch_number}_{i}",
                job_id=f"batch_{batch_number}",
                url=url,
                metadata=metadata,
                batch_number=batch_number,
                status="queued"
            )
            tasks.append(task)

        # Process tasks concurrently
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_task = {
                executor.submit(self.process_single_task, task): task
                for task in tasks
            }

            for future in as_completed(future_to_task):
                task = future_to_task[future]
                try:
                    updated_task = future.result()
                    # Update the task in our list
                    task_idx = tasks.index(task)
                    tasks[task_idx] = updated_task

                    # Add delay between requests to avoid rate limiting
                    time.sleep(REQUEST_DELAY_SECONDS)

                except Exception as e:
                    logger.error(f"Task execution failed: {e}")
                    task.status = "failed"
                    task.error_message = str(e)

        return tasks

    def process_all_batches(
        self,
        urls: List[Dict[str, Any]],
        progress_callback: Optional[callable] = None
    ) -> Tuple[List[EnrichedCompanyData], BulkJob]:
        """Process all URLs in batches with progress tracking."""

        # Create job
        job_id = str(uuid.uuid4())
        total_batches = (len(urls) + self.batch_size - 1) // self.batch_size

        job = BulkJob(
            job_id=job_id,
            status="processing",
            total_urls=len(urls),
            batch_size=self.batch_size,
            total_batches=total_batches
        )

        logger.info(f"Starting bulk job {job_id} with {len(urls)} URLs in {total_batches} batches")

        # Split URLs into batches
        batches = self.create_batches(urls)
        all_enriched_data = []

        for batch_num, batch_urls in enumerate(batches, 1):
            logger.info(f"Starting batch {batch_num}/{total_batches}")

            # Process batch
            tasks = self.process_batch(batch_urls, batch_num)

            # Convert tasks to enriched data
            for task in tasks:
                if task.enriched_data:
                    all_enriched_data.append(task.enriched_data)
                else:
                    # Create failed entry
                    failed_data = EnrichedCompanyData(
                        url=task.url,
                        processing_status="failed",
                        error_message=task.error_message or "Unknown error"
                    )
                    all_enriched_data.append(failed_data)

            # Update job progress
            job.processed_urls = len(all_enriched_data)
            job.current_batch = batch_num
            job.progress_percentage = (batch_num / total_batches) * 100

            # Count failures
            job.failed_urls = sum(1 for data in all_enriched_data if data.processing_status == "failed")

            # Update error summary
            for data in all_enriched_data:
                if data.error_message:
                    error_type = data.error_message.split(':')[0] if ':' in data.error_message else 'Unknown'
                    job.error_summary[error_type] = job.error_summary.get(error_type, 0) + 1

            # Progress callback
            if progress_callback:
                progress_callback(job, batch_num, total_batches)

            # Delay between batches to avoid overwhelming servers
            if batch_num < total_batches:
                logger.info(f"Batch {batch_num} completed. Waiting {BATCH_DELAY_SECONDS}s before next batch...")
                time.sleep(BATCH_DELAY_SECONDS)

        # Mark job as completed
        job.status = "completed"
        job.completed_at = datetime.now().isoformat()

        logger.info(f"Bulk job {job_id} completed. Processed {job.processed_urls} URLs, {job.failed_urls} failed.")

        return all_enriched_data, job


def process_excel_file(
    input_file: str,
    output_file: str,
    batch_size: int = DEFAULT_BATCH_SIZE,
    ai_provider: str = "ollama",
    ai_model: str = "mistral:7b",
    progress_callback: Optional[callable] = None
) -> BulkJob:
    """Main function to process Excel file with URLs."""

    # Read URLs from Excel
    excel_processor = ExcelProcessor()
    rows = excel_processor.read_urls_from_excel(input_file)
    urls = [row["url"] for row in rows]

    if not urls:
        raise ValueError("No valid URLs found in Excel file")

    # Process in batches
    processor = BatchProcessor(
        batch_size=batch_size,
        ai_provider=ai_provider,
        ai_model=ai_model
    )

    enriched_data, job = processor.process_all_batches(rows, progress_callback)

    # Write results to Excel
    excel_processor.write_results_to_excel(enriched_data, output_file)

    return job


def process_excel_file_with_db(
    input_file: str,
    output_file: str,
    batch_size: int = DEFAULT_BATCH_SIZE,
    ai_provider: str = "ollama",
    ai_model: str = "mistral:7b",
    progress_callback: Optional[callable] = None,
    db_url: str = "sqlite:///webscraper.db"
) -> str:
    """
    Process Excel file with database persistence and resumability.

    Args:
        input_file: Path to input Excel file with URLs
        output_file: Path to output Excel file for results
        batch_size: Number of URLs per batch
        ai_provider: 'ollama' or 'gemini'
        ai_model: Model name
        progress_callback: Function(job_dict, batch_num, total_batches)
        db_url: Database connection URL

    Returns:
        Job ID for tracking progress
    """
    logger.info(f"Starting DB-backed processing: {input_file}")

    # Initialize database
    db = DatabaseManager(db_url)

    # Read URLs from Excel
    excel_processor = ExcelProcessor()
    rows = excel_processor.read_urls_from_excel(input_file)
    urls = [row["url"] for row in rows]

    if not urls:
        raise ValueError("No valid URLs found in Excel file")

    # Create processing job in DB
    job_id = str(uuid.uuid4())
    total_batches = (len(urls) + batch_size - 1) // batch_size

    db.create_job(
        job_id=job_id,
        total_urls=len(urls),
        batch_size=batch_size,
        config={
            "ai_provider": ai_provider,
            "ai_model": ai_model,
            "input_file": input_file,
            "output_file": output_file,
        }
    )

    row_metadata_by_url = {row["url"]: row for row in rows}

    # Create all processing tasks
    for i, url in enumerate(urls):
        batch_number = (i // batch_size) + 1

        # Check if already processed successfully
        if not db.is_url_processed(job_id, url):
            db.create_task(
                task_id=f"{job_id}_{i}",
                job_id=job_id,
                original_url=url,
                batch_number=batch_number,
            )

    # Initialize processor
    processor = BatchProcessor(
        batch_size=batch_size,
        ai_provider=ai_provider,
        ai_model=ai_model
    )

    # Process batches
    db.update_job_status(job_id, "processing")
    scraper = WebScraper()

    for batch_num in range(1, total_batches + 1):
        # Get pending tasks for this batch
        batch_tasks = db.get_pending_tasks(job_id, limit=batch_size)

        if not batch_tasks:
            logger.info(f"Batch {batch_num}: No pending tasks")
            continue

        logger.info(f"Processing batch {batch_num}/{total_batches} with {len(batch_tasks)} tasks")

        # Create batch in DB
        batch_id = f"{job_id}_batch_{batch_num}"
        db.create_batch(
            batch_id=batch_id,
            job_id=job_id,
            batch_number=batch_num,
            task_count=len(batch_tasks),
        )
        db.update_batch_status(batch_id, "processing")

        # Process tasks concurrently
        success_count = 0
        failure_count = 0

        with ThreadPoolExecutor(max_workers=MAX_WORKERS_PER_BATCH) as executor:
            future_to_task = {}

            for db_task in batch_tasks:
                future = executor.submit(
                    _process_task_with_db,
                    db_task,
                    processor,
                    db,
                    row_metadata_by_url.get(db_task.original_url),
                )
                future_to_task[future] = db_task

            for future in as_completed(future_to_task):
                db_task = future_to_task[future]
                try:
                    enriched_data = future.result()
                    if enriched_data.processing_status == "completed":
                        success_count += 1
                    else:
                        failure_count += 1
                    time.sleep(REQUEST_DELAY_SECONDS)
                except Exception as e:
                    logger.error(f"Task execution failed for {db_task.original_url}: {e}")
                    db.update_task_status(
                        db_task.task_id,
                        "failed",
                        error_message=str(e),
                        retry_count=db_task.retry_count + 1
                    )
                    failure_count += 1

        # Update batch completion
        db.update_batch_counts(batch_id, success_count, failure_count)
        db.update_batch_status(batch_id, "completed")

        # Update job progress
        job_stats = db.get_job_stats(job_id)
        db.update_job_status(
            job_id,
            "processing",
            processed_urls=job_stats["completed_urls"],
            failed_urls=job_stats["failed_urls"],
            progress_percentage=job_stats["progress_percentage"],
            current_batch=batch_num,
        )

        # Progress callback
        if progress_callback:
            progress_callback(job_stats, batch_num, total_batches)

        # Delay between batches
        if batch_num < total_batches:
            logger.info(f"Batch {batch_num} completed. Waiting {BATCH_DELAY_SECONDS}s...")
            time.sleep(BATCH_DELAY_SECONDS)

    # Export results to Excel
    results = db.get_job_results(job_id)
    if results:
        enriched_data_list = []
        for result in results:
            enriched = EnrichedCompanyData(
                url=result["original_url"],
                company_name=result["company_name"],
                company_url=result["company_url"],
                location=result["location"],
                industry=result["industry"],
                company_size=result["company_size"],
                segmentation=result["segmentation"],
                salesforce_products=result["salesforce_products"],
                key_persons=result["key_persons"],
                processing_status="completed",
                confidence_score=result["confidence_score"],
            )
            enriched_data_list.append(enriched)

        excel_processor.write_results_to_excel(enriched_data_list, output_file)
        logger.info(f"Results exported to {output_file}")

    # Mark job as completed
    final_stats = db.get_job_stats(job_id)
    db.update_job_status(job_id, "completed", completed_at=True)

    logger.info(f"Job {job_id} completed: {final_stats['completed_urls']}/{final_stats['total_urls']} processed")

    return job_id


def _process_task_with_db(
    db_task,
    processor: BatchProcessor,
    db: DatabaseManager,
    row_metadata: Optional[Dict[str, Any]] = None,
) -> EnrichedCompanyData:
    """
    Process a single task with database updates.

    Args:
        db_task: ProcessingTask from database
        processor: BatchProcessor instance
        db: DatabaseManager instance

    Returns:
        EnrichedCompanyData with results
    """
    start_time = time.time()

    try:
        db.update_task_status(db_task.task_id, "scraping")

        # Scrape the URL
        scraped_data = processor.scraper.scrape(db_task.original_url)

        # Analyze with AI
        db.update_task_status(db_task.task_id, "analyzing")
        ai_result = processor.ai_analyzer.analyze(
            text=scraped_data.main_text,
            user_prompt=STRUCTURED_EXTRACTION_PROMPT,
            source_url=db_task.original_url,
            page_title=scraped_data.title
        )

        # Parse and structure
        enriched_data = processor._parse_ai_response(
            db_task.original_url,
            scraped_data,
            ai_result,
            row_metadata=row_metadata,
        )

        # Save to database
        db.save_company_data(db_task.task_id, enriched_data)

        # Mark task as completed
        processing_time = time.time() - start_time
        db.update_task_status(
            db_task.task_id,
            "completed",
            processing_time=processing_time
        )

        logger.info(f"✓ Completed: {db_task.original_url} ({processing_time:.2f}s)")
        return enriched_data

    except Exception as e:
        logger.error(f"✗ Failed: {db_task.original_url}: {e}")
        processing_time = time.time() - start_time
        db.update_task_status(
            db_task.task_id,
            "failed",
            error_message=str(e),
            processing_time=processing_time,
            retry_count=db_task.retry_count + 1
        )

        # Return failed enriched data
        return EnrichedCompanyData(
            url=db_task.original_url,
            processing_status="failed",
            error_message=str(e),
            confidence_score=0.0
        )