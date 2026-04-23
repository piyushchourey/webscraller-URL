# Job-Wise Smartlead Enrichment System

## Overview

This system enriches company data on a **per-job basis**. After bulk scraping completes for a job, you can trigger enrichment for all companies in that job.

## Architecture

```
Phase 0: Bulk Scraping (Existing)
├─ Job-1 (Salesforce Leads)
│  ├─ Company-A → DB (enrichment_status: pending)
│  ├─ Company-B → DB (enrichment_status: pending)
│  └─ Company-C → DB (enrichment_status: pending)
│
└─ Job-2 (Snowflake Leads)
   ├─ Company-X → DB (enrichment_status: pending)
   ├─ Company-Y → DB (enrichment_status: pending)
   └─ Company-Z → DB (enrichment_status: pending)

Phase 1: Job-Wise Enrichment (New)
├─ Enrich Job-1
│  ├─ Query: SELECT * FROM company_data WHERE job_id=1 AND enrichment_status='pending'
│  ├─ Call Smartlead API for each company
│  ├─ Save: smartlead_enrichment JSON + status update
│  └─ Result: All Job-1 companies → enrichment_status: 'enriched'
│
└─ Enrich Job-2 (independently)
   ├─ Query: SELECT * FROM company_data WHERE job_id=2 AND enrichment_status='pending'
   ├─ Call Smartlead API for each company
   ├─ Save: smartlead_enrichment JSON + status update
   └─ Result: All Job-2 companies → enrichment_status: 'enriched'

Phase 2: Export (Existing + Enhanced)
├─ Job-1 Export: Companies + enriched data from smartlead_enrichment JSON
└─ Job-2 Export: Companies + enriched data from smartlead_enrichment JSON
```

## Database Schema

### CompanyData Table (Enhanced)

```sql
company_data
├── company_id (PK)
├── task_id (FK → processing_tasks)
├── company_name TEXT
├── company_url TEXT
├── location TEXT
├── industry TEXT
├── company_size TEXT
│
├── Scraped Data:
│  ├── raw_scraped_text TEXT
│  ├── ai_analysis TEXT
│  └── confidence_score FLOAT
│
├── Key Persons (Relationship to key_persons table)
│  └── key_persons JSON/Foreign key
│
├── NEW - Smartlead Enrichment:
│  ├── smartlead_enrichment JSONB ← API response stored here
│  ├── enrichment_status TEXT (pending/processing/enriched/failed)
│  ├── enrichment_retry_count INT
│  ├── enrichment_last_error TEXT
│  └── enrichment_updated_at TIMESTAMP
│
└── Timestamps:
   ├── created_at TIMESTAMP
   └── updated_at TIMESTAMP
```

## Setup Instructions

### 1. Run Database Migration

Add the new enrichment columns to your PostgreSQL database:

```bash
cd d:\projects\webscraller-URL
.\venv\Scripts\python.exe scripts\add_enrichment_columns.py
```

Expected output:
```
✅ Added column 'smartlead_enrichment' - Smartlead API response
✅ Added column 'enrichment_status' - enrichment status
✅ Added column 'enrichment_retry_count' - number of enrichment retry attempts
✅ Added column 'enrichment_last_error' - error message from last enrichment attempt
✅ Added column 'enrichment_updated_at' - timestamp of last enrichment update

✅ Migration completed successfully!
```

### 2. Set Smartlead API Key

Add your Smartlead API key to `.env`:

```env
SMARTLEAD_API_KEY=your_api_key_here
```

Or pass it via command line.

## Usage

### Run Enrichment for a Job

**Dry Run (Preview what would be enriched):**
```bash
.\venv\Scripts\python.exe scripts\enrich_job.py ec53d2d3-xxxx --dry-run
```

**Actual Enrichment:**
```bash
.\venv\Scripts\python.exe scripts\enrich_job.py ec53d2d3-xxxx
```

**With API Key:**
```bash
.\venv\Scripts\python.exe scripts\enrich_job.py ec53d2d3-xxxx --api-key your_key
```

**With Rate Limiting:**
```bash
.\venv\Scripts\python.exe scripts\enrich_job.py ec53d2d3-xxxx --rate-limit 30
```

**Retry Failed Enrichments:**
```bash
.\venv\Scripts\python.exe scripts\enrich_job.py ec53d2d3-xxxx --retry-failed
```

### Example Output

```
======================================================================
Starting enrichment for Job: Salesforce Customer-22April
Job ID: ec53d2d3-xxxx
Status: completed
Dry Run: False
======================================================================

Enrichment Status: 3 pending, 0 processing, 0 enriched, 0 failed out of 3 total

Processing 3 pending companies...

[1/3] Processing: Acme Corporation
  ✅ Successfully enriched
[2/3] Processing: TechCorp Inc
  ✅ Successfully enriched
[3/3] Processing: Global Industries
  ✅ Successfully enriched

======================================================================
Enrichment Complete for Job: Salesforce Customer-22April
✅ Successfully enriched: 3
❌ Failed: 0
======================================================================
```

## Python API Usage

### EnrichmentManager Class

```python
from scraper.database.manager import DatabaseManager
from scraper.enrichment import EnrichmentManager

db = DatabaseManager()
enrichment_mgr = EnrichmentManager(db)

# Get pending companies for a job
companies = enrichment_mgr.get_pending_companies_for_job("job_id_here")

# Get enrichment stats
stats = enrichment_mgr.get_enrichment_stats_for_job("job_id_here")
print(f"Pending: {stats['pending']}, Enriched: {stats['enriched']}, Failed: {stats['failed']}")

# Save enrichment result
enrichment_mgr.save_enrichment_result(
    company_id=123,
    enrichment_data={"company_info": {...}, "key_persons": [...]},
    success=True
)

# Reset failed enrichments for retry
reset_count = enrichment_mgr.reset_failed_enrichments("job_id_here")
```

### SmartleadAdapter Class

```python
from scraper.enrichment.smartlead_adapter import SmartleadAdapter

smartlead = SmartleadAdapter(api_key="your_key")

# Enrich single company
data = smartlead.enrich_company(
    company_name="Acme Corp",
    domain="acme.com",
    location="New York, USA"
)

# Find key persons
persons = smartlead.find_key_persons(
    company_name="Acme Corp",
    domain="acme.com"
)

# Full enrichment (both endpoints)
full_data = smartlead.enrich_company_full(
    company_name="Acme Corp",
    domain="acme.com",
    location="New York, USA"
)
```

## Enrichment Status Workflow

```
        ┌─────────────┐
        │   PENDING   │ (Initial state after scraping)
        └──────┬──────┘
               │ enrichment_mgr.mark_enrichment_processing()
               ▼
        ┌──────────────┐
        │ PROCESSING   │ (While calling Smartlead API)
        └──────┬───────┘
               │
        ┌──────┴──────────┐
        │                 │
   [SUCCESS]         [ERROR]
        │                 │
        ▼                 ▼
  ┌──────────┐     ┌───────────┐
  │ ENRICHED │     │  FAILED   │
  └──────────┘     └─────┬─────┘
                         │
                         ├─ enrichment_retry_count++
                         ├─ enrichment_last_error = msg
                         │
                  [If retries < max]
                         │
                         ▼ (with --retry-failed)
                    [Reset to PENDING]
```

## Error Handling & Retries

### Automatic Retries
- API timeouts: Exponential backoff (2s, 4s, 8s)
- Rate limiting (429): Respects rate limits + backoff
- Connection errors: 3 retry attempts

### Manual Retries
```bash
# See which companies failed
.\venv\Scripts\python.exe -c "
from scraper.database.manager import DatabaseManager
from scraper.enrichment import EnrichmentManager

db = DatabaseManager()
mgr = EnrichmentManager(db)
stats = mgr.get_enrichment_stats_for_job('job_id')
print(f'Failed: {stats[\"failed\"]} out of {stats[\"total\"]}')
"

# Reset and retry
.\venv\Scripts\python.exe scripts\enrich_job.py job_id --retry-failed
```

## Smartlead API Endpoint Configuration

Update the following in `scraper/enrichment/smartlead_adapter.py`:

```python
# Line ~100: Update company enrichment endpoint
endpoint="/v1/company/enrich"  # Change to actual Smartlead endpoint

# Line ~130: Update key persons endpoint
endpoint="/v1/people/find"  # Change to actual Smartlead endpoint
```

Replace with your actual Smartlead API endpoints and update payload/response parsing as needed.

## Integration with Streamlit UI (Future)

Once enrichment is complete, you can add a "View Enrichment" section in `pages/bulk_processing.py`:

```python
# Show enrichment status
stats = enrichment_mgr.get_enrichment_stats_for_job(job_id)
st.metric("Enriched Companies", stats['enriched'])
st.metric("Failed Enrichments", stats['failed'])

# Button to trigger enrichment
if st.button("🚀 Start Enrichment"):
    # Trigger background job
    subprocess.Popen([
        "python", "scripts/enrich_job.py", job_id,
        "--api-key", os.getenv("SMARTLEAD_API_KEY")
    ])
```

## Troubleshooting

**Q: "Job not found" error**
- A: Verify the job_id exists: `db.get_all_jobs()`

**Q: "No pending companies"**
- A: All companies already enriched or haven't been scraped yet

**Q: API authentication failed**
- A: Check SMARTLEAD_API_KEY is correct in `.env`

**Q: Rate limiting errors**
- A: Reduce `--rate-limit` value (e.g., 30 instead of 60)

**Q: Database column not found**
- A: Run migration: `scripts/add_enrichment_columns.py`
