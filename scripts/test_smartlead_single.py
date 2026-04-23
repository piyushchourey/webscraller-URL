"""
Test Smartlead API for a SINGLE company — step-by-step with full output.

Usage:
    python scripts/test_smartlead_single.py
    python scripts/test_smartlead_single.py --api-key YOUR_KEY --domain example.com
    python scripts/test_smartlead_single.py --api-key YOUR_KEY --name "Acme Corp"
    python scripts/test_smartlead_single.py --api-key YOUR_KEY --domain example.com --name "Acme Corp"
"""

import argparse
import json
import os
import sys
import logging
from pathlib import Path

# ── Make sure project root is on sys.path ──────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Load .env if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from scraper.enrichment.smartlead_adapter import SmartleadAdapter

# ── Logging: pretty, coloured-ish ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def _print_json(title: str, data) -> None:
    """Pretty-print a section with a header."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print("="*60)
    print(json.dumps(data, indent=2, default=str))


def _print_section(title: str) -> None:
    print(f"\n{'─'*60}")
    print(f"  {title}")
    print("─"*60)


def run_test(api_key: str, domain: str | None, company_name: str | None, location: str | None, limit: int):
    adapter = SmartleadAdapter(api_key=api_key, rate_limit_per_minute=20)

    # ── STEP 1: Normalise domain ───────────────────────────────────────────────
    _print_section("STEP 1 — Domain normalisation")
    normalised = adapter._normalize_domain(domain)
    print(f"  Input domain  : {domain!r}")
    print(f"  Normalised    : {normalised!r}")

    # ── STEP 2: search-contacts (domain-first) ─────────────────────────────────
    _print_section("STEP 2 — search-contacts (domain-first)")
    search_resp = None
    if normalised:
        print(f"  Trying companyDomain = [{normalised!r}] ...")
        search_resp = adapter.search_contacts(domain=normalised, limit=limit)
        if search_resp and search_resp.get("success"):
            contacts = search_resp.get("data", {}).get("list") or []
            print(f"  ✅ Success — {len(contacts)} contact(s) found via domain")
            _print_json("search-contacts response (domain)", search_resp)
        else:
            print(f"  ❌ No results via domain (response: {search_resp})")
    else:
        print("  ⚠️  No domain provided — skipping domain search")

    # ── STEP 3: search-contacts fallback (company name) ───────────────────────
    fallback_triggered = False
    if not (search_resp and (search_resp.get("data", {}).get("list") or [])):
        _print_section("STEP 3 — search-contacts FALLBACK (company name)")
        if company_name:
            print(f"  Trying companyName = [{company_name!r}] ...")
            search_resp = adapter.search_contacts(company_name=company_name, limit=limit)
            if search_resp and search_resp.get("success"):
                contacts = search_resp.get("data", {}).get("list") or []
                print(f"  ✅ Success — {len(contacts)} contact(s) found via company name")
                _print_json("search-contacts response (company name)", search_resp)
            else:
                print(f"  ❌ No results via company name either (response: {search_resp})")
            fallback_triggered = True
        else:
            print("  ⚠️  No company name provided — cannot fallback")
    else:
        _print_section("STEP 3 — search-contacts fallback")
        print("  ⏭️  Skipped — domain search returned results")

    contacts = (search_resp or {}).get("data", {}).get("list") or []
    if not contacts:
        print("\n🚫 No contacts found via either method — stopping here.")
        return

    # ── STEP 4: Build find-emails payload ─────────────────────────────────────
    _print_section("STEP 4 — Build find-emails payload")
    email_contacts = []
    for c in contacts:
        first = (c.get("firstName") or "").strip()
        last  = (c.get("lastName")  or "").strip()
        cdomain = adapter._normalize_domain(
            (c.get("company") or {}).get("website")
        ) or normalised
        if first and last and cdomain:
            email_contacts.append({"firstName": first, "lastName": last, "companyDomain": cdomain})
        else:
            print(f"  ⚠️  Skipping {first} {last} — missing domain")

    print(f"  Contacts ready for email lookup: {len(email_contacts)}")
    _print_json("find-emails input payload", {"contacts": email_contacts})

    # ── STEP 5: find-emails ────────────────────────────────────────────────────
    _print_section("STEP 5 — find-emails")
    find_resp = None
    if email_contacts:
        find_resp = adapter.find_emails(email_contacts)
        if find_resp and find_resp.get("success"):
            rows = find_resp.get("data") or []
            valid = [r for r in rows if str(r.get("verification_status", "")).lower() == "valid"]
            print(f"  ✅ find-emails success — {len(rows)} row(s) returned, {len(valid)} valid")
            _print_json("find-emails response", find_resp)
        else:
            print(f"  ❌ find-emails failed (response: {find_resp})")
    else:
        print("  ⚠️  No contacts to look up — skipping")

    # ── STEP 6: Merge & Summary ────────────────────────────────────────────────
    _print_section("STEP 6 — Merged contacts_enriched")
    email_map = {}
    if find_resp and find_resp.get("success"):
        for row in find_resp.get("data") or []:
            key = (
                (row.get("firstName") or "").strip().lower(),
                (row.get("lastName")  or "").strip().lower(),
                adapter._normalize_domain(row.get("companyDomain")) or "",
            )
            email_map[key] = row

    enriched = []
    valid_count = 0
    for c in contacts:
        ec = dict(c)
        first  = (c.get("firstName") or "").strip().lower()
        last   = (c.get("lastName")  or "").strip().lower()
        cdomain = adapter._normalize_domain((c.get("company") or {}).get("website")) or (normalised or "")
        info = email_map.get((first, last, cdomain))
        if info:
            ec["email_id"]             = info.get("email_id")
            ec["email_status"]         = info.get("status")
            ec["verification_status"]  = info.get("verification_status")
            ec["email_source"]         = info.get("source")
            if info.get("email_id") and str(info.get("verification_status", "")).lower() == "valid":
                valid_count += 1
        enriched.append(ec)

    _print_json("contacts_enriched", enriched)

    print(f"\n{'='*60}")
    print("  SUMMARY")
    print("="*60)
    print(f"  Lookup method     : {'domain' if not fallback_triggered else 'company_name'}")
    print(f"  Contacts found    : {len(contacts)}")
    print(f"  Emails requested  : {len(email_contacts)}")
    print(f"  Valid emails found: {valid_count}")
    print("="*60)


def main():
    parser = argparse.ArgumentParser(
        description="Test Smartlead API for a single company (step-by-step)"
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("SMARTLEAD_API_KEY", ""),
        help="Smartlead API key (or set SMARTLEAD_API_KEY env var)",
    )
    parser.add_argument("--domain",       default=None, help="Company domain, e.g. apple.com")
    parser.add_argument("--name",         default=None, help="Company name, e.g. 'Apple Inc'")
    parser.add_argument("--location",     default=None, help="Location hint (optional)")
    parser.add_argument("--limit",        type=int, default=5, help="Max contacts to fetch (default 5)")
    args = parser.parse_args()

    if not args.api_key:
        print("❌ No API key provided.")
        print("   Pass --api-key YOUR_KEY  or set SMARTLEAD_API_KEY in your .env file")
        sys.exit(1)

    if not args.domain and not args.name:
        print("❌ Provide at least --domain or --name (or both).")
        sys.exit(1)

    run_test(
        api_key=args.api_key,
        domain=args.domain,
        company_name=args.name,
        location=args.location,
        limit=args.limit,
    )


if __name__ == "__main__":
    main()
