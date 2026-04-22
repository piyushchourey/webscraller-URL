"""Test script for database-backed bulk processing system."""

import os
import sys
import tempfile
import json
from pathlib import Path

import pandas as pd

from scraper.database import DatabaseManager
from scraper.models import EnrichedCompanyData
from scraper.bulk_processor import BatchProcessor, STRUCTURED_EXTRACTION_PROMPT

# Handle encoding
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')


def test_database_initialization():
    """Test database creation and initialization."""
    print("\n" + "=" * 70)
    print("TEST 1: Database Initialization")
    print("=" * 70)

    try:
        db = DatabaseManager("sqlite:///test_db_init.db")
        print("[OK] Database initialized successfully")

        # Create a test job
        job_dict = db.create_job(
            job_id="test_job_001",
            total_urls=10,
            batch_size=5,
            config={"test": True}
        )
        print(f"[OK] Created test job: {job_dict['job_id']}")

        # Verify job was created
        fetched_job = db.get_job("test_job_001")
        assert fetched_job is not None
        assert fetched_job.total_urls == 10
        print(f"[OK] Job verified: {fetched_job.status}")

        return True
    except Exception as e:
        print(f"[FAIL] Database test failed: {e}")
        return False


def test_task_management():
    """Test task creation and status updates."""
    print("\n" + "=" * 70)
    print("TEST 2: Task Management")
    print("=" * 70)

    try:
        db = DatabaseManager("sqlite:///test_db_task.db")

        job_id = "test_job_task_001"
        db.create_job(job_id=job_id, total_urls=3, batch_size=3)

        # Create tasks
        urls = [
            "https://example.com/company1",
            "https://example.com/company2",
            "https://example.com/company3",
        ]

        for i, url in enumerate(urls):
            task_dict = db.create_task(
                task_id=f"{job_id}_task_{i}",
                job_id=job_id,
                original_url=url,
                batch_number=1,
            )
            print(f"✓ Created task: {task_dict['task_id']}")

        # Check duplicate prevention
        existing = db.is_url_processed(job_id, urls[0])
        assert not existing, "URL should not be marked as processed yet"
        print("✓ Duplicate URL detection working")

        # Update task status
        db.update_task_status(f"{job_id}_task_0", "processing")
        db.update_task_status(f"{job_id}_task_0", "completed")

        # Get pending tasks
        pending = db.get_pending_tasks(job_id)
        assert len(pending) == 2, "Should have 2 pending tasks"
        print(f"✓ Pending tasks retrieved: {len(pending)} remaining")

        # Verify URL is now marked as processed
        existing = db.is_url_processed(job_id, urls[0])
        assert existing, "URL should be marked as processed"
        print("✓ Processed URL correctly marked")

        return True
    except Exception as e:
        print(f"✗ Task management test failed: {e}")
        return False


def test_company_data_persistence():
    """Test saving and retrieving company data with persons."""
    print("\n" + "=" * 70)
    print("TEST 3: Company Data Persistence with Separate Person Table")
    print("=" * 70)

    try:
        db = DatabaseManager("sqlite:///test_db_company.db")

        # Create job and task first
        job_id = "test_job_company_001"
        db.create_job(job_id=job_id, total_urls=1, batch_size=1)

        task_id = f"{job_id}_task_0"
        db.create_task(
            task_id=task_id,
            job_id=job_id,
            original_url="https://example.com",
            batch_number=1,
        )

        # Create enriched company data
        enriched_data = EnrichedCompanyData(
            url="https://example.com",
            company_name="Example Corp",
            company_url="https://example.com",
            location="San Francisco, USA",
            industry="Technology",
            company_size="201-500",
            segmentation="Mid-market",
            salesforce_products=["Sales Cloud", "Service Cloud"],
            key_persons=[
                {
                    "name": "John Smith",
                    "title": "Chief Executive Officer",
                    "contact": "john@example.com"
                },
                {
                    "name": "Jane Doe",
                    "title": "VP Sales",
                    "contact": "jane@example.com"
                }
            ],
            raw_scraped_text="Sample company text...",
            ai_analysis="Company analysis...",
            confidence_score=0.95
        )

        # Save to database
        company_dict = db.save_company_data(task_id, enriched_data)
        print(f"✓ Saved company data (ID: {company_dict['company_id']})")
        print(f"  - Company: {company_dict['company_name']}")
        print(f"  - Persons: {len(company_dict['key_persons'])}")

        # Verify persons were saved
        assert len(company_dict['key_persons']) == 2
        print(f"✓ Persons saved in separate table: {len(company_dict['key_persons'])} entries")
        for person in company_dict['key_persons']:
            print(f"  - {person['name']} ({person['title']})")

        # Retrieve and verify
        retrieved = db.get_company_data(company_dict['company_id'])
        assert retrieved is not None
        assert retrieved.company_name == "Example Corp"
        assert len(retrieved.key_persons) == 2
        assert retrieved.company_size == "201-500"
        assert retrieved.segmentation == "Mid-market"
        assert "Sales Cloud" in retrieved.salesforce_products
        print("✓ Company data retrieved successfully with all new fields")

        # Query by URL
        retrieved_by_url = db.get_company_data_by_url("https://example.com")
        assert retrieved_by_url is not None
        print("✓ Company data retrievable by original URL")

        return True
    except Exception as e:
        print(f"✗ Company data persistence test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_job_statistics():
    """Test job statistics and progress tracking."""
    print("\n" + "=" * 70)
    print("TEST 4: Job Statistics and Progress Tracking")
    print("=" * 70)

    try:
        db = DatabaseManager("sqlite:///test_db_stats.db")

        job_id = "test_job_stats_001"
        db.create_job(job_id=job_id, total_urls=5, batch_size=5)

        # Create and process some tasks
        for i in range(5):
            task_id = f"{job_id}_task_{i}"
            db.create_task(
                task_id=task_id,
                job_id=job_id,
                original_url=f"https://example.com/{i}",
                batch_number=1,
            )

            if i < 3:
                db.update_task_status(task_id, "completed")
            elif i < 4:
                db.update_task_status(task_id, "failed", error_message="Test error")
            # Leave one as queued

        # Get statistics
        stats = db.get_job_stats(job_id)

        print(f"Job Statistics:")
        print(f"  - Status: {stats['status']}")
        print(f"  - Total: {stats['total_urls']}")
        print(f"  - Completed: {stats['completed_urls']}")
        print(f"  - Failed: {stats['failed_urls']}")
        print(f"  - Pending: {stats['pending_urls']}")
        print(f"  - Progress: {stats['progress_percentage']:.1f}%")

        assert stats["completed_urls"] == 3
        assert stats["failed_urls"] == 1
        assert stats["pending_urls"] == 1
        assert stats["progress_percentage"] == 60.0

        print("✓ Statistics calculated correctly")
        return True
    except Exception as e:
        print(f"✗ Job statistics test failed: {e}")
        return False


def test_ai_prompt_extraction():
    """Test the enhanced AI extraction prompt."""
    print("\n" + "=" * 70)
    print("TEST 5: Enhanced AI Extraction Prompt")
    print("=" * 70)

    try:
        print("\nCurrent Extraction Prompt:")
        print("-" * 70)
        print(STRUCTURED_EXTRACTION_PROMPT[:500] + "...")

        # Check for new fields in prompt
        required_fields = [
            "company_size",
            "segmentation",
            "salesforce_products",
        ]

        for field in required_fields:
            if field in STRUCTURED_EXTRACTION_PROMPT:
                print(f"✓ Prompt includes: {field}")
            else:
                print(f"✗ Prompt missing: {field}")
                return False

        print("\n✓ All enhanced fields present in extraction prompt")
        return True
    except Exception as e:
        print(f"✗ AI prompt test failed: {e}")
        return False


def test_batch_processor():
    """Test batch processor with new fields."""
    print("\n" + "=" * 70)
    print("TEST 6: Batch Processor with New Fields")
    print("=" * 70)

    try:
        processor = BatchProcessor(
            batch_size=5,
            max_workers=1,
            ai_provider="ollama",
            ai_model="mistral:7b"
        )

        # Test AI response parsing with new fields
        mock_ai_response = """
        Here's the extracted data:
        {
            "company_name": "Tech Innovations Inc",
            "company_url": "https://techinnovations.com",
            "location": "New York, USA",
            "industry": "Software Development",
            "company_size": "201-500",
            "segmentation": "Mid-market",
            "salesforce_products": ["Sales Cloud", "Marketing Cloud"],
            "key_persons": [
                {
                    "name": "Alice Johnson",
                    "title": "CEO",
                    "contact": "alice@techinnovations.com"
                }
            ],
            "confidence_score": 0.92
        }
        """

        from scraper.models import AnalysisResult, ScrapedContent

        scraped = ScrapedContent(
            url="https://techinnovations.com",
            title="Tech Innovations",
            main_text="Company details..."
        )

        ai_result = AnalysisResult(
            prompt_used="test",
            response_text=mock_ai_response,
            model="test"
        )

        enriched = processor._parse_ai_response(
            "https://techinnovations.com",
            scraped,
            ai_result
        )

        print(f"✓ Parsed AI response:")
        print(f"  - Company: {enriched.company_name}")
        print(f"  - Size: {enriched.company_size}")
        print(f"  - Segmentation: {enriched.segmentation}")
        print(f"  - Products: {enriched.salesforce_products}")
        print(f"  - Persons: {len(enriched.key_persons)}")

        assert enriched.company_name == "Tech Innovations Inc"
        assert enriched.company_size == "201-500"
        assert enriched.segmentation == "Mid-market"
        assert len(enriched.salesforce_products) == 2
        assert len(enriched.key_persons) == 1

        print("✓ All new fields parsed correctly")
        return True
    except Exception as e:
        print(f"✗ Batch processor test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_excel_export_with_new_fields():
    """Test Excel export includes new fields."""
    print("\n" + "=" * 70)
    print("TEST 7: Excel Export with New Fields")
    print("=" * 70)

    try:
        enriched_data = EnrichedCompanyData(
            url="https://example.com",
            company_name="Example Corp",
            company_url="https://example.com",
            location="SF, USA",
            industry="Tech",
            company_size="501-1000",
            segmentation="Enterprise",
            salesforce_products=["Sales Cloud", "Analytics Cloud"],
            key_persons=[{"name": "John", "title": "CEO"}],
            confidence_score=0.88
        )

        export_dict = enriched_data.to_dict()

        print("Excel Export Fields:")
        for key, value in export_dict.items():
            print(f"  - {key}: {str(value)[:50]}")

        # Verify new fields are in export
        assert "Company_Size" in export_dict
        assert "Segmentation" in export_dict
        assert "Salesforce_Products" in export_dict

        print("✓ All new fields included in Excel export")
        return True
    except Exception as e:
        print(f"✗ Excel export test failed: {e}")
        return False


def cleanup_test_db():
    """Clean up test databases."""
    test_dbs = [
        "test_db_init.db",
        "test_db_task.db",
        "test_db_company.db",
        "test_db_stats.db",
        "test_webscraper.db",
    ]
    for db_file in test_dbs:
        try:
            if os.path.exists(db_file):
                os.remove(db_file)
                print(f"[OK] Deleted {db_file}")
        except Exception as e:
            print(f"Warning: Could not delete {db_file}: {e}")


if __name__ == "__main__":
    print("\n")
    print("=" * 70)
    print("DATABASE-BACKED BULK PROCESSOR TESTS")
    print("=" * 70)

    tests = [
        ("Database Initialization", test_database_initialization),
        ("Task Management", test_task_management),
        ("Company Data Persistence", test_company_data_persistence),
        ("Job Statistics", test_job_statistics),
        ("AI Prompt Enhancement", test_ai_prompt_extraction),
        ("Batch Processor", test_batch_processor),
        ("Excel Export", test_excel_export_with_new_fields),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n✗ {test_name} crashed: {e}")
            results.append((test_name, False))

    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"[{status}] {test_name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n==> All tests passed! Database-backed system is ready.")
    else:
        print(f"\n==> {total - passed} test(s) failed. Review output above.")

    # Cleanup
    cleanup_test_db()
