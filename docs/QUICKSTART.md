# Quick Start: Smartlead Job-Wise Enrichment

## 5-Minute Setup

### 1️⃣ Database Migration (1 minute)

```bash
cd d:\projects\webscraller-URL
.\venv\Scripts\python.exe scripts\add_enrichment_columns.py
```

✅ Expected output:
```
✅ Migration complete: 5 column(s) added
✅ Migration completed successfully!
```

### 2️⃣ Add API Key to .env (1 minute)

Edit `.env` and add your Smartlead API key:

```env
SMARTLEAD_API_KEY=your_actual_api_key_here
```

Get your API key from: https://smartlead.ai/settings/api

### 3️⃣ Restart Streamlit (1 minute)

```bash
# Kill existing Streamlit
taskkill /F /IM streamlit.exe

# Restart
cd d:\projects\webscraller-URL
.\venv\Scripts\streamlit.exe run app.py
```

### 4️⃣ Access Enrichment Tab (2 minutes)

1. Open Streamlit app in browser
2. Look for new **"🔍 Enrichment"** tab in sidebar
3. Select a completed job
4. Click **"🚀 Start Enrichment"**

That's it! ✅

---

## Typical Usage Flow

```
1. Run Bulk Scraping (existing)
   └─ Creates Job-1 with companies data in DB

2. Go to Enrichment Tab (new)
   └─ Select Job-1
   └─ Click "Start Enrichment"
   └─ System calls Smartlead API for each company
   └─ Results stored in database

3. Monitor Progress
   └─ Check "Status Monitor" tab
   └─ See enrichment % complete

4. Export with Enrichment Data (coming soon)
   └─ Enriched data included in Excel export
```

---

## Command Line Usage

### Dry Run (Preview without API calls)

```bash
.\venv\Scripts\python.exe scripts\enrich_job.py JOB_ID_HERE --dry-run
```

### Full Enrichment

```bash
.\venv\Scripts\python.exe scripts\enrich_job.py JOB_ID_HERE --api-key your_key
```

### Retry Failed Enrichments

```bash
.\venv\Scripts\python.exe scripts\enrich_job.py JOB_ID_HERE --retry-failed
```

### Custom Rate Limit (30 calls/min)

```bash
.\venv\Scripts\python.exe scripts\enrich_job.py JOB_ID_HERE --rate-limit 30
```

---

## Find Your Job ID

### Option 1: Streamlit UI
1. Go to "Processing Job History" tab
2. Job IDs shown next to job names: `ec53d2d3-...`

### Option 2: Query Database

```bash
.\venv\Scripts\python.exe -c "
from scraper.database import DatabaseManager

db = DatabaseManager()
jobs = db.get_all_jobs(limit=5)
for job in jobs:
    print(f'{job.job_name}: {job.job_id}')
"
```

---

## What Gets Enriched?

Each company receives enrichment data from Smartlead with:

```json
{
  "smartlead_enrichment": {
    "company_info": {
      // Smartlead company details
      "company": "...",
      "industry": "...",
      "employees": "...",
      // ... other fields
    },
    "key_persons": {
      // Smartlead found persons
      "people": [
        {
          "name": "John Doe",
          "title": "CEO",
          "email": "john@company.com"
        },
        // ... more persons
      ]
    },
    "enriched_at": "2026-04-23T10:30:00"
  },
  "enrichment_status": "enriched"
}
```

---

## Troubleshooting

### ❌ "API key not provided"

**Solution:** Add to `.env`:
```env
SMARTLEAD_API_KEY=your_actual_key
```

### ❌ "No pending companies"

**Solution:** All companies already enriched. Use `--retry-failed` to retry failed ones.

### ❌ "Column not found" error

**Solution:** Run migration:
```bash
.\venv\Scripts\python.exe scripts\add_enrichment_columns.py
```

### ❌ "Rate limiting errors"

**Solution:** Reduce rate limit:
```bash
.\venv\Scripts\python.exe scripts\enrich_job.py JOB_ID --rate-limit 20
```

### ❌ "Job not found"

**Solution:** Verify job ID exists:
```bash
.\venv\Scripts\python.exe -c "
from scraper.database import DatabaseManager
db = DatabaseManager()
jobs = db.get_all_jobs()
print([job.job_id for job in jobs])
"
```

---

## Architecture Overview

```
Bulk Scraping (Phase 0)
  │
  ├─ Job-1 Created
  │  ├─ Company-A (enrichment_status: pending)
  │  ├─ Company-B (enrichment_status: pending)
  │  └─ Company-C (enrichment_status: pending)
  │
  └─ Job-2 Created
     ├─ Company-X (enrichment_status: pending)
     ├─ Company-Y (enrichment_status: pending)
     └─ Company-Z (enrichment_status: pending)

Enrichment Phase (Phase 1) - SELECT SPECIFIC JOB
  │
  ├─ User selects Job-1 in Streamlit
  │  ├─ Query: Companies in Job-1 with enrichment_status='pending'
  │  ├─ Call Smartlead API for each
  │  └─ Update: enrichment_status='enriched' + store JSON
  │
  └─ Job-2 remains pending (independent)
     ├─ Can be enriched later
     ├─ No interference with Job-1
     └─ Allows flexible scheduling

Export Phase (Phase 2)
  └─ Excel includes enriched data for each job independently
```

---

## Database Schema (Added Columns)

```sql
company_data table additions:
├── smartlead_enrichment JSONB      -- API response stored here
├── enrichment_status TEXT          -- pending/processing/enriched/failed
├── enrichment_retry_count INT      -- Auto-incremented on failures
├── enrichment_last_error TEXT      -- Error message from failed attempts
└── enrichment_updated_at TIMESTAMP -- When last updated
```

---

## Next Steps

1. ✅ **Migration**: Run `add_enrichment_columns.py`
2. ✅ **Configuration**: Add API key to `.env`
3. ✅ **UI**: Access new Enrichment tab
4. ⏳ **Enhancement**: Excel export with enriched data (coming soon)
5. ⏳ **Scheduling**: Optional background job scheduler

---

## File Structure (New Files)

```
webscrapper-URL/
├── scraper/
│   ├── enrichment/
│   │   ├── __init__.py              (new)
│   │   ├── manager.py               (new) - Job-wise enrichment logic
│   │   └── smartlead_adapter.py    (new) - API integration
│   │
│   └── database/
│       └── manager.py               (updated) - Added enrichment methods
│
├── pages/
│   └── enrichment.py                (new) - Streamlit UI
│
├── scripts/
│   ├── add_enrichment_columns.py   (new) - DB migration
│   └── enrich_job.py                (new) - CLI worker
│
├── ENRICHMENT_GUIDE.md              (new) - Full documentation
├── QUICKSTART.md                    (this file)
└── .env                             (updated) - Add SMARTLEAD_API_KEY
```

---

## Development Status

| Component | Status |
|-----------|--------|
| **Database Model** | ✅ Complete |
| **Migration Script** | ✅ Complete |
| **EnrichmentManager** | ✅ Complete |
| **Smartlead Adapter** | ✅ Complete |
| **CLI Worker** | ✅ Complete |
| **Streamlit UI** | ✅ Complete |
| **DatabaseManager Integration** | ✅ Complete |
| **Excel Export Enhancement** | 🟡 Next |
| **Background Scheduler** | 🟡 Optional |

---

## Getting Help

1. **Check ENRICHMENT_GUIDE.md** for detailed documentation
2. **Review error messages** - they're descriptive
3. **Check logs** - see what's happening behind the scenes
4. **Test dry-run** - use `--dry-run` flag to preview

---

## Success Criteria

✅ All companies in selected job enriched  
✅ Enrichment data stored in database  
✅ Status tracked (pending → processing → enriched/failed)  
✅ Retry logic works for failed enrichments  
✅ No interference between different jobs  
✅ Rate limiting respected  

You're ready to go! 🚀
