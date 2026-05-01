"""Smartlead Enrichment Page for job-specific data enrichment."""

import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from scraper.database import DatabaseManager, get_database_url
from scraper.enrichment import EnrichmentManager
from scraper.ui_styles import apply_app_shell_styles

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENRICHMENT_LOG_DIR = PROJECT_ROOT / "logs" / "enrichment"


def _tail_file(file_path: Path, max_lines: int = 30) -> str:
    """Return last N lines from a text file."""
    if not file_path.exists():
        return ""
    with file_path.open("r", encoding="utf-8", errors="replace") as handle:
        lines = handle.readlines()
    return "".join(lines[-max_lines:])


def _start_background_enrichment(cmd: list[str], log_file: Path) -> subprocess.Popen:
    """Start enrichment worker as detached background process."""
    ENRICHMENT_LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_handle = log_file.open("a", encoding="utf-8")
    popen_kwargs = {
        "cwd": str(PROJECT_ROOT),
        "stdout": log_handle,
        "stderr": subprocess.STDOUT,
        "stdin": subprocess.DEVNULL,
        "shell": False,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        )
    return subprocess.Popen(cmd, **popen_kwargs)


def _build_enrichment_tables(job_results: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build company-level and contact-level enrichment table rows."""
    company_rows: list[dict[str, Any]] = []
    contact_rows: list[dict[str, Any]] = []

    def _first_non_empty(items: list[dict[str, Any]], key: str) -> str:
        for item in items:
            value = item.get(key)
            if value not in (None, ""):
                return str(value)
        return ""

    for row in job_results:
        enrichment_data = row.get("smartlead_enrichment") or {}
        stats = enrichment_data.get("stats") or {}
        contacts_enriched = enrichment_data.get("contacts_enriched", []) or []
        search_contacts = ((enrichment_data.get("search_contacts") or {}).get("data") or {}).get("list") or []
        filter_eval = enrichment_data.get("filter_evaluation") or {}
        evaluated_fields = filter_eval.get("evaluated_fields") or {}
        exclusion_reasons = enrichment_data.get("exclusion_reasons") or []
        exclusion_rule_ids = enrichment_data.get("rule_ids") or []

        smartlead_headcount = (
            _first_non_empty(contacts_enriched, "companyHeadCount")
            or _first_non_empty(search_contacts, "companyHeadCount")
        )
        smartlead_revenue = (
            _first_non_empty(contacts_enriched, "companyRevenue")
            or _first_non_empty(search_contacts, "companyRevenue")
        )

        company_rows.append(
            {
                "Company": row.get("company_name") or "",
                "Domain": row.get("company_url") or "",
                "Location": row.get("location") or "",
                "Industry": row.get("industry") or "",
                "Company_Size": smartlead_headcount or row.get("company_size") or "",
                "Company_Revenue": smartlead_revenue,
                "Segment": row.get("segmentation") or "",
                "Enrichment_Status": row.get("enrichment_status") or "pending",
                "Contacts_Found": stats.get("contacts_found", 0),
                "Valid_Emails": stats.get("valid_emails_found", 0),
                "Find_Emails_Skipped": bool(enrichment_data.get("find_emails_skipped", False)),
                "Exclusion_Applied": bool(enrichment_data.get("exclusion_applied", False)),
                "Exclusion_Rule_IDs": ", ".join(str(x) for x in exclusion_rule_ids if str(x).strip()),
                "Exclusion_Reasons": " | ".join(str(x) for x in exclusion_reasons if str(x).strip()),
                "Headcount_Observed": (
                    enrichment_data.get("headcount_observed")
                    or evaluated_fields.get("headcount_raw")
                    or smartlead_headcount
                    or ""
                ),
                "Last_Error": row.get("enrichment_last_error") or "",
            }
        )

        for contact in contacts_enriched:
            contact_rows.append(
                {
                    "Company": row.get("company_name") or "",
                    "First_Name": contact.get("firstName") or "",
                    "Last_Name": contact.get("lastName") or "",
                    "Title": contact.get("title") or "",
                    "Email": contact.get("email_id") or "",
                    "Verification_Status": contact.get("verification_status") or "",
                    "Email_Status": contact.get("email_status") or "",
                    "LinkedIn": contact.get("linkedin") or "",
                }
            )

    return company_rows, contact_rows


def _get_email_verification_counts(contact_rows: list[dict[str, Any]]) -> tuple[int, int]:
    """Return valid and invalid email counts from contact-level rows."""
    valid_count = 0
    invalid_count = 0

    for row in contact_rows:
        status = str(row.get("Verification_Status") or "").strip().lower()
        if status == "valid":
            valid_count += 1
        elif status:
            invalid_count += 1

    return valid_count, invalid_count


def _build_enrichment_excel_bytes(
    job_results: list[dict],
    job_name: str = "",
) -> bytes:
    """
    Flatten smartlead_enrichment JSON from each company row into a single Excel sheet.

    Each row in the output represents one contact enriched.  Company-level columns
    (from the DB row and from enrichment.company_context / stats) are repeated for
    every contact of that company so the sheet is fully self-contained.

    If a company has no contacts its data still appears as a single row (blanks for
    contact columns).
    """
    import io

    flat_rows: list[dict] = []

    for row in job_results:
        enrichment: dict = row.get("smartlead_enrichment") or {}
        company_ctx: dict = enrichment.get("company_context") or {}
        stats: dict = enrichment.get("stats") or {}
        enriched_at: str = enrichment.get("enriched_at") or ""

        # ── Company-level columns ────────────────────────────────────────────
        company_base = {
            "Company_Name": row.get("company_name") or "",
            "Company_URL":  row.get("company_url") or "",
            #"Country":      row.get("location") or company_ctx.get("location") or "",
        }

        # ── Contacts: prefer contacts_enriched; fall back to search_contacts ─
        contacts_enriched: list[dict] = enrichment.get("contacts_enriched") or []
        search_contacts: list[dict] = (
            (enrichment.get("search_contacts") or {})
            .get("data", {})
            .get("list", [])
        )
        contacts: list[dict] = contacts_enriched or search_contacts

        # find_emails keyed by email_id for quick lookup
        find_email_map: dict[str, dict] = {
            fe.get("email_id", ""): fe
            for fe in (enrichment.get("find_emails") or {}).get("data") or []
        }

        if not contacts:
            flat_rows.append({
                **company_base,
                "Industry":            "",
                "Company_Size":        "",
                "Revenue":             "",
                "First_Name":          "",
                "Last_Name":           "",
                "Title":               "",
                "Level":               "",
                "Department":          "",
                "Email":               "",
                "Verification_Status": "",
                "City":                "",
                "State":               "",
                "Country_Contact":     "",
                "Address":             "",
            })
            continue

        for contact in contacts:
            dept = contact.get("department") or []
            email_id = contact.get("email_id") or contact.get("email") or ""
            fe_row = find_email_map.get(email_id) or {}

            flat_rows.append({
                **company_base,
                # Smartlead-sourced company fields
                "Industry":            contact.get("industry") or row.get("industry") or "",
                "Company_Size":        contact.get("companyHeadCount") or row.get("company_size") or "",
                "Revenue":             contact.get("companyRevenue") or "",
                # Contact identity
                "First_Name":          contact.get("firstName") or "",
                "Last_Name":           contact.get("lastName") or "",
                "Title":               contact.get("title") or "",
                "Level":               contact.get("level") or "",
                "Department":          ", ".join(dept) if isinstance(dept, list) else str(dept or ""),
                # Contact info
                "Email":               email_id,
                "Verification_Status": (
                    contact.get("verification_status")
                    or fe_row.get("verification_status")
                    or ""
                ),
                # Location
                "City":                contact.get("city") or "",
                "State":               contact.get("state") or "",
                "Country_Contact":     contact.get("country") or "",
                "Address":             contact.get("address") or "",
            })

    output = io.BytesIO()
    df = pd.DataFrame(flat_rows) if flat_rows else pd.DataFrame()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Enrichment Data", index=False)
    return output.getvalue()


def _render_kpi_card(label: str, value: Any, tone: str = "") -> None:
    """Render compact KPI card."""
    tone_class = f"ui-{tone}" if tone else ""
    st.markdown(
        f"""
        <div class="ui-kpi-card">
            <div class="ui-kpi-label">{label}</div>
            <div class="ui-kpi-value {tone_class}">{value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_status_chart(stats: dict[str, int]) -> None:
    """Render enrichment status bar chart."""
    chart_df = pd.DataFrame(
        {
            "Status": ["Pending", "Processing", "Enriched", "Failed"],
            "Count": [
                stats.get("pending", 0),
                stats.get("processing", 0),
                stats.get("enriched", 0),
                stats.get("failed", 0),
            ],
        }
    )
    st.bar_chart(chart_df.set_index("Status"), height=230)

# Page configuration
st.set_page_config(
    page_title="Smartlead Enrichment Workspace",
    page_icon="🔍",
    layout="wide",
)
apply_app_shell_styles("Enrichment")

st.title("🔍 Smartlead Enrichment Workspace")
st.markdown(
    """
    <div class="ui-hero">
        <strong>Enrich company and decision-maker data in one place.</strong><br/>
        Select a completed batch job, start enrichment, and monitor progress with structured outputs.
    </div>
    """,
    unsafe_allow_html=True,
)

# Initialize database
db = DatabaseManager()
enrichment_mgr = EnrichmentManager(db)

# Sidebar configuration
with st.sidebar:
    st.header("⚙️ Enrichment Settings")
    
    api_key = st.text_input(
        "Smartlead API Key",
        value=os.getenv("SMARTLEAD_API_KEY", ""),
        type="password",
        help="Get from https://smartlead.ai/settings/api",
    )
    
    rate_limit = st.slider(
        "Rate Limit (calls/min)",
        min_value=10,
        max_value=120,
        value=60,
        help="Respect API rate limits to avoid throttling",
    )
    
    st.divider()
    
    db_url = get_database_url()
    st.metric("Database", "PostgreSQL" if "postgresql" in db_url else "SQLite")

# Main content area
tab1, tab2, tab3 = st.tabs(["🎯 Run Enrichment", "📊 Status Monitor", "📋 Results & History"])

# ═════════════════════════════════════════════════════════════════════════════
# TAB 1: Start Enrichment
# ═════════════════════════════════════════════════════════════════════════════

with tab1:
    st.header("Start Data Enrichment")
    st.caption("Flow: Choose Job → Configure Options → Start Enrichment → Track Live Progress")
    
    # Get completed jobs
    all_jobs = db.get_all_jobs(limit=100)
    completed_jobs = [job for job in all_jobs if job.status == "completed"]
    
    if not completed_jobs:
        st.warning("⚠️ No completed jobs found. Run Batch URL Processing first.")
    else:
        # Job selector
        job_options = {
            f"{job.job_name or 'Untitled'} • {job.job_id[:8]}... • {job.created_at.strftime('%Y-%m-%d')}": job.job_id
            for job in completed_jobs
        }
        
        selected_job_label = st.selectbox(
            "Select Job for Enrichment",
            options=list(job_options.keys()),
            help="Choose a completed job to enrich",
        )
        
        selected_job_id = job_options[selected_job_label]
        
        # Get job details
        job_info = enrichment_mgr.get_job_info(selected_job_id)
        stats = enrichment_mgr.get_enrichment_stats_for_job(selected_job_id)

        total_companies = stats.get("total") or (
            stats.get("pending", 0)
            + stats.get("processing", 0)
            + stats.get("enriched", 0)
            + stats.get("failed", 0)
        )
        completion_ratio = (stats.get("enriched", 0) / total_companies) if total_companies else 0
        
        # Display job info
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            _render_kpi_card("Selected Job", job_info["job_name"])
        with col2:
            _render_kpi_card("Created", job_info["created_at"].strftime("%Y-%m-%d %H:%M"))
        with col3:
            _render_kpi_card("Total Companies", job_info["total_urls"])
        with col4:
            _render_kpi_card("Job Status", job_info["status"].upper())
        
        st.divider()
        st.progress(completion_ratio, text=f"Enrichment completion: {completion_ratio*100:.1f}%")
        
        # Enrichment status breakdown
        st.subheader("Status Overview")
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            _render_kpi_card("Pending", stats["pending"], "warning")
        with col2:
            _render_kpi_card("Processing", stats["processing"])
        with col3:
            _render_kpi_card("Enriched", stats["enriched"], "success")
        with col4:
            _render_kpi_card("Failed", stats["failed"], "danger")

        _render_status_chart(stats)
        
        st.divider()
        
        # Enrichment options
        st.subheader("Enrichment Controls")
        with st.expander("Advanced Options", expanded=False):
            col1, col2 = st.columns([2, 1])

            with col1:
                dry_run = st.checkbox(
                    "Preview only (no API calls)",
                    value=False,
                    help="Show what would be enriched without calling Smartlead.",
                )

            with col2:
                retry_failed = st.checkbox(
                    "Retry failed records",
                    value=False,
                    help="Re-run companies marked as failed.",
                )

            st.markdown("**Company Filter Hook (before find-emails)**")
            hook_col1, hook_col2 = st.columns(2)
            with hook_col1:
                company_filter_hook_enabled = st.checkbox(
                    "Enable company exclusion filters",
                    value=True,
                    help="Skip find-emails for companies matching exclusion rules.",
                )
            with hook_col2:
                st.caption("Default rules: exclude >2000 and <15 employees")

            threshold_col1, threshold_col2 = st.columns(2)
            with threshold_col1:
                company_min_employees = st.number_input(
                    "Min employees (exclude below)",
                    min_value=0,
                    value=15,
                    step=1,
                    help="Companies below this size are excluded from find-emails.",
                )
            with threshold_col2:
                company_max_employees = st.number_input(
                    "Max employees (exclude above)",
                    min_value=0,
                    value=1000,
                    step=1,
                    help="Companies above this size are excluded from find-emails.",
                )

            excluded_industries = st.text_input(
                "Excluded industries (comma-separated)",
                value="",
                help="Example: Government, Defense, Gambling",
            )
            excluded_locations = st.text_input(
                "Excluded locations (comma-separated)",
                value="",
                help="Example: Russia, North Korea",
            )

        st.divider()
        
        # Action buttons
        col1, col2, col3 = st.columns([1, 1, 2])
        
        with col1:
            start_button = st.button(
                "🚀 Start Data Enrichment",
                key="start_enrichment",
                use_container_width=True,
                type="primary",
            )
        
        with col2:
            view_button = st.button(
                "👁️ Preview Queue",
                key="preview_enrichment",
                use_container_width=True,
            )
        
        # Handle preview
        if view_button:
            companies = enrichment_mgr.get_pending_companies_for_job(selected_job_id)
            if companies:
                st.info(f"{len(companies)} companies are currently queued for enrichment.")
                preview_rows = [
                    {
                        "Company": company.get("company_name") or "",
                        "Domain": company.get("company_url") or "",
                        "Location": company.get("location") or "",
                        "Industry": company.get("industry") or "",
                    }
                    for company in companies
                ]
                st.dataframe(preview_rows, use_container_width=True, hide_index=True)
            else:
                st.info("No pending companies to enrich for this job.")
        
        # Handle enrichment start
        if start_button:
            if not api_key:
                st.error("❌ Add your Smartlead API key in the sidebar to continue.")
            elif stats["pending"] == 0 and not retry_failed:
                st.warning("⚠️ No pending records. Enable 'Retry failed records' to reprocess failures.")
            else:
                # Prepare enrichment parameters
                enrichment_params = {
                    "job_id": selected_job_id,
                    "api_key": api_key,
                    "rate_limit": rate_limit,
                    "dry_run": dry_run,
                    "retry_failed": retry_failed,
                    "company_filter_hook_enabled": company_filter_hook_enabled,
                    "company_min_employees": int(company_min_employees),
                    "company_max_employees": int(company_max_employees),
                    "excluded_industries": excluded_industries,
                    "excluded_locations": excluded_locations,
                }
                
                # Store in session state
                st.session_state.enrichment_started = True
                st.session_state.enrichment_params = enrichment_params
                st.session_state.enrichment_start_time = datetime.now()
                
                # Display progress
                st.success(
                    f"✅ Data enrichment started for {job_info['job_name']}\n\n"
                    f"- Mode: {'Dry Run' if dry_run else 'Full Enrichment'}\n"
                    f"- Companies to process: {stats['pending']}\n"
                    f"- API Rate Limit: {rate_limit} calls/min\n\n"
                    f"Progress updates are shown below and in Status Monitor."
                )
                
                st.info(
                    "⏳ Enrichment is running in the background. You can safely close this page. "
                    "Check Status Monitor tab for updates."
                )
                
                # Background worker command
                cmd = [
                    sys.executable, "scripts/enrich_job.py",
                    selected_job_id,
                    "--api-key", api_key,
                    "--rate-limit", str(rate_limit),
                    "--company-filter-hook", "on" if company_filter_hook_enabled else "off",
                    "--company-min-employees", str(int(company_min_employees)),
                    "--company-max-employees", str(int(company_max_employees)),
                ]

                if excluded_industries.strip():
                    cmd.extend(["--excluded-industries", excluded_industries.strip()])

                if excluded_locations.strip():
                    cmd.extend(["--excluded-locations", excluded_locations.strip()])
                
                if dry_run:
                    cmd.append("--dry-run")
                
                if retry_failed:
                    cmd.append("--retry-failed")
                
                run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
                short_job_id = selected_job_id[:8]
                log_path = ENRICHMENT_LOG_DIR / f"enrich_{short_job_id}_{run_id}.log"

                try:
                    process = _start_background_enrichment(cmd, log_path)
                    st.session_state.enrichment_process = process
                    st.session_state.enrichment_pid = process.pid
                    st.session_state.enrichment_job_id = selected_job_id
                    st.session_state.enrichment_log_path = str(log_path)
                    st.session_state.enrichment_started_at = datetime.now().isoformat()

                    st.success(
                        f"🚀 Worker started (PID: {process.pid}). Track progress in Status Monitor and Live Worker Log."
                    )
                except Exception as exc:
                    st.error(f"❌ Failed to start enrichment worker: {exc}")

                with st.expander("Technical Details", expanded=False):
                    st.caption(f"Command: `{' '.join(cmd)}`")
                    st.caption(f"Log file: `{log_path}`")

        process = st.session_state.get("enrichment_process")
        process_job_id = st.session_state.get("enrichment_job_id")
        process_log_path = st.session_state.get("enrichment_log_path")

        if process and process_job_id == selected_job_id:
            return_code = process.poll()
            if return_code is None:
                st.info(
                    f"⏳ Enrichment worker running for this job (PID: {st.session_state.get('enrichment_pid')})."
                )
            elif return_code == 0:
                st.success("✅ Enrichment worker finished successfully.")
            else:
                st.error(f"❌ Enrichment worker exited with code {return_code}.")

            if process_log_path:
                log_text = _tail_file(Path(process_log_path), max_lines=40)
                with st.expander("Live Worker Log", expanded=return_code is None):
                    if log_text:
                        st.code(log_text, language="text")
                    else:
                        st.caption("No log output yet.")

# ═════════════════════════════════════════════════════════════════════════════
# TAB 2: Status Monitor
# ═════════════════════════════════════════════════════════════════════════════

with tab2:
    st.header("📊 Enrichment Status Monitor")

    refresh_col1, refresh_col2, refresh_col3 = st.columns([1, 1, 4])
    with refresh_col1:
        refresh_now = st.button("🔄 Refresh", key="refresh_status_monitor", use_container_width=True)
    with refresh_col2:
        auto_refresh = st.checkbox("Auto refresh", key="auto_refresh_monitor", value=False)
    with refresh_col3:
        st.caption("Tip: enable auto refresh to keep progress live while enrichment is running.")

    if refresh_now:
        st.rerun()
    
    # Get all jobs with their enrichment stats
    all_jobs = db.get_all_jobs(limit=50)
    
    if not all_jobs:
        st.info("No jobs found")
    else:
        # Create status table
        status_data = []
        
        for job in all_jobs:
            stats = enrichment_mgr.get_enrichment_stats_for_job(job.job_id)

            total_count = stats.get("total") or (
                stats.get("pending", 0)
                + stats.get("processing", 0)
                + stats.get("enriched", 0)
                + stats.get("failed", 0)
            )
            enriched_count = stats.get("enriched", 0)

            if total_count > 0:
                enrichment_pct = (enriched_count / total_count) * 100
                if enriched_count > 0 and enrichment_pct < 1:
                    progress_label = "<1%"
                else:
                    progress_label = f"{enrichment_pct:.1f}%"
            else:
                enrichment_pct = 0
                progress_label = "0%"
            
            status_data.append({
                "Job Name": job.job_name or "Untitled",
                "Job ID": job.job_id[:8],
                "Status": {
                    "completed": "✅ COMPLETED",
                    "processing": "🟡 PROCESSING",
                    "pending": "⏳ PENDING",
                    "failed": "❌ FAILED",
                }.get((job.status or "").lower(), (job.status or "unknown").upper()),
                "Total": total_count,
                "Pending": stats["pending"],
                "Processing": stats["processing"],
                "Enriched": stats["enriched"],
                "Failed": stats["failed"],
                "Progress": progress_label,
            })
        
        st.dataframe(
            status_data,
            use_container_width=True,
            hide_index=True,
        )
        
        st.divider()
        
        # Detailed view for selected job
        st.subheader("Detailed View")
        
        job_display_options = {
            f"{job.job_name or 'Untitled'} • {job.job_id[:8]}": job.job_id
            for job in all_jobs
        }
        
        selected_detail_job = st.selectbox(
            "Select job for details",
            options=list(job_display_options.keys()),
            key="detail_job_select",
        )
        
        detail_job_id = job_display_options[selected_detail_job]
        detail_stats = enrichment_mgr.get_enrichment_stats_for_job(detail_job_id)
        detail_results = db.get_job_results(detail_job_id)
        
        # Show detailed metrics
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Companies", detail_stats["total"])
        with col2:
            st.metric("Pending", detail_stats["pending"])
        with col3:
            st.metric("Enriched", detail_stats["enriched"])
        with col4:
            st.metric("Failed", detail_stats["failed"])
        
        # Progress bar
        detail_total = detail_stats.get("total") or (
            detail_stats.get("pending", 0)
            + detail_stats.get("processing", 0)
            + detail_stats.get("enriched", 0)
            + detail_stats.get("failed", 0)
        )
        detail_enriched = detail_stats.get("enriched", 0)

        if detail_total > 0:
            progress = detail_enriched / detail_total
            if detail_enriched > 0 and (progress * 100) < 1:
                progress_text = f"<1% Complete ({detail_enriched}/{detail_total})"
            else:
                progress_text = f"{progress*100:.1f}% Complete ({detail_enriched}/{detail_total})"
            st.progress(progress, text=progress_text)

        st.divider()
        st.subheader("Enrichment Output")
        company_rows, contact_rows = _build_enrichment_tables(detail_results)

        if company_rows:
            st.markdown("**Company-Level Output**")
            st.dataframe(company_rows, use_container_width=True, hide_index=True)
            skipped_count = sum(1 for company_row in company_rows if company_row.get("Find_Emails_Skipped"))
            if skipped_count:
                st.caption(
                    f"Filter hook summary: find-emails skipped for {skipped_count}/{len(company_rows)} companies based on exclusion rules."
                )
        else:
            st.info("No company output available for this job yet.")

        st.markdown("**Contact-Level Output**")
        if contact_rows:
            st.dataframe(contact_rows, use_container_width=True, hide_index=True)
            valid_count, invalid_count = _get_email_verification_counts(contact_rows)
            st.caption(f"Email verification summary: ✅ Valid = {valid_count} | ❌ Invalid/Other = {invalid_count}")
        else:
            st.info("No enriched contacts available for this job yet.")

        # ── Download enrichment Excel ────────────────────────────────────────
        if detail_results:
            _detail_job_name = selected_detail_job.split(" \u2022 ")[0].strip().replace(" ", "_")
            _excel_bytes = _build_enrichment_excel_bytes(
                detail_results, _detail_job_name
            )
            st.download_button(
                label="\u2b07\ufe0f Download Enrichment Excel",
                data=_excel_bytes,
                file_name=f"enrichment_{_detail_job_name}_{detail_job_id[:8]}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"dl_tab2_{detail_job_id}",
                use_container_width=False,
            )

    if auto_refresh:
        time.sleep(5)
        st.rerun()

# ═════════════════════════════════════════════════════════════════════════════
# TAB 3: History
# ═════════════════════════════════════════════════════════════════════════════

with tab3:
    st.header("📋 Enrichment Results History")
    
    all_jobs = db.get_all_jobs(limit=100)
    
    if not all_jobs:
        st.info("No jobs in history")
    else:
        for job in all_jobs:
            stats = enrichment_mgr.get_enrichment_stats_for_job(job.job_id)
            
            with st.expander(
                f"**{job.job_name or 'Untitled Job'}** • {job.job_id[:8]} • Created: {job.created_at.strftime('%Y-%m-%d %H:%M')}"
            ):
                job_results = db.get_job_results(job.job_id)
                company_rows, contact_rows = _build_enrichment_tables(job_results)
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Total", stats["total"])
                with col2:
                    st.metric("Pending", stats["pending"])
                with col3:
                    st.metric("Enriched", stats["enriched"])
                with col4:
                    st.metric("Failed", stats["failed"])
                
                st.caption(f"Job ID: `{job.job_id}`")
                st.caption(f"Status: {job.status.upper()}")
                
                if stats["total"] > 0:
                    progress = stats["enriched"] / stats["total"]
                    st.progress(progress, text=f"{progress*100:.1f}% enriched")

                st.markdown("**Company-Level Output**")
                if company_rows:
                    st.dataframe(company_rows, use_container_width=True, hide_index=True)
                    skipped_count = sum(1 for company_row in company_rows if company_row.get("Find_Emails_Skipped"))
                    if skipped_count:
                        st.caption(
                            f"Filter hook summary: find-emails skipped for {skipped_count}/{len(company_rows)} companies based on exclusion rules."
                        )
                else:
                    st.caption("No company-level enrichment output recorded.")

                st.markdown("**Contact-Level Output**")
                if contact_rows:
                    st.dataframe(contact_rows, use_container_width=True, hide_index=True)
                    valid_count, invalid_count = _get_email_verification_counts(contact_rows)
                    st.caption(f"Email verification summary: ✅ Valid = {valid_count} | ❌ Invalid/Other = {invalid_count}")
                else:
                    st.caption("No contact-level enrichment output recorded.")

                # ── Download button ──────────────────────────────────────────
                if job_results:
                    _hist_job_name = (job.job_name or "Untitled").replace(" ", "_")
                    _hist_excel_bytes = _build_enrichment_excel_bytes(
                        job_results, _hist_job_name
                    )
                    st.download_button(
                        label="⬇️ Download Enrichment Excel",
                        data=_hist_excel_bytes,
                        file_name=f"enrichment_{_hist_job_name}_{job.job_id[:8]}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key=f"dl_hist_{job.job_id}",
                        use_container_width=False,
                    )

st.divider()

# Footer
st.markdown(
    """
    ---
    **Documentation:** See `ENRICHMENT_GUIDE.md` for detailed usage instructions.
    
    **Support:** For API issues, check Smartlead documentation or contact support.
    """
)
