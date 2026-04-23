"""Smartlead Enrichment Page for job-specific data enrichment."""

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

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

    for row in job_results:
        enrichment_data = row.get("smartlead_enrichment") or {}
        stats = enrichment_data.get("stats") or {}
        company_rows.append(
            {
                "Company": row.get("company_name") or "",
                "Domain": row.get("company_url") or "",
                "Location": row.get("location") or "",
                "Enrichment_Status": row.get("enrichment_status") or "pending",
                "Contacts_Found": stats.get("contacts_found", 0),
                "Valid_Emails": stats.get("valid_emails_found", 0),
                "Last_Error": row.get("enrichment_last_error") or "",
            }
        )

        for contact in enrichment_data.get("contacts_enriched", []) or []:
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

# Page configuration
st.set_page_config(
    page_title="Smartlead Enrichment Workspace",
    page_icon="🔍",
    layout="wide",
)
apply_app_shell_styles("Enrichment")

st.title("🔍 Smartlead Enrichment Workspace")
st.markdown("Run and monitor job-wise Smartlead enrichment with clear structured outputs.")

# Initialize database
db = DatabaseManager()
enrichment_mgr = EnrichmentManager(db)

# Sidebar configuration
with st.sidebar:
    st.header("⚙️ Configuration")
    
    api_key = st.text_input(
        "Smartlead API Key",
        value=os.getenv("SMARTLEAD_API_KEY", ""),
        type="password",
        help="Get from https://smartlead.ai/settings/api",
    )
    
    rate_limit = st.slider(
        "API Rate Limit (calls/min)",
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
    st.header("Start Job Enrichment")
    
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
        
        # Display job info
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Job Name", job_info["job_name"])
        with col2:
            st.metric("Created", job_info["created_at"].strftime("%Y-%m-%d %H:%M"))
        with col3:
            st.metric("Total Companies", job_info["total_urls"])
        with col4:
            st.metric("Status", job_info["status"].upper())
        
        st.divider()
        
        # Enrichment status breakdown
        st.subheader("Enrichment Status Breakdown")
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric(
                "Pending",
                stats["pending"],
                delta=f"({stats['pending'] / stats['total'] * 100:.1f}%)" if stats["total"] > 0 else "0%",
            )
        with col2:
            st.metric(
                "Processing",
                stats["processing"],
                delta=f"({stats['processing'] / stats['total'] * 100:.1f}%)" if stats["total"] > 0 else "0%",
            )
        with col3:
            st.metric(
                "Enriched",
                stats["enriched"],
                delta=f"({stats['enriched'] / stats['total'] * 100:.1f}%)" if stats["total"] > 0 else "0%",
            )
        with col4:
            st.metric(
                "Failed",
                stats["failed"],
                delta=f"({stats['failed'] / stats['total'] * 100:.1f}%)" if stats["total"] > 0 else "0%",
            )
        
        st.divider()
        
        # Enrichment options
        st.subheader("🚀 Enrichment Options")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            dry_run = st.checkbox(
                "Dry Run Mode",
                value=False,
                help="Preview what would be enriched without making API calls",
            )
        
        with col2:
            retry_failed = st.checkbox(
                "Retry Failed",
                value=False,
                help="Retry previously failed enrichments",
            )
        
        st.divider()
        
        # Action buttons
        col1, col2, col3 = st.columns([1, 1, 2])
        
        with col1:
            start_button = st.button(
                "🚀 Start Enrichment",
                key="start_enrichment",
                use_container_width=True,
                type="primary",
            )
        
        with col2:
            view_button = st.button(
                "👁️ Preview",
                key="preview_enrichment",
                use_container_width=True,
            )
        
        # Handle preview
        if view_button:
            companies = enrichment_mgr.get_pending_companies_for_job(selected_job_id)
            if companies:
                st.info(f"Preview: {len(companies)} companies pending enrichment")
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
                st.info("No pending companies to enrich for this job")
        
        # Handle enrichment start
        if start_button:
            if not api_key:
                st.error("❌ Please provide Smartlead API Key in sidebar")
            elif stats["pending"] == 0 and not retry_failed:
                st.warning("⚠️ No pending companies to enrich. Use 'Retry Failed' to retry failed enrichments.")
            else:
                # Prepare enrichment parameters
                enrichment_params = {
                    "job_id": selected_job_id,
                    "api_key": api_key,
                    "rate_limit": rate_limit,
                    "dry_run": dry_run,
                    "retry_failed": retry_failed,
                }
                
                # Store in session state
                st.session_state.enrichment_started = True
                st.session_state.enrichment_params = enrichment_params
                st.session_state.enrichment_start_time = datetime.now()
                
                # Display progress
                st.success(
                    f"✅ Enrichment started for {job_info['job_name']}\n\n"
                    f"- Mode: {'Dry Run' if dry_run else 'Full Enrichment'}\n"
                    f"- Companies to process: {stats['pending']}\n"
                    f"- API Rate Limit: {rate_limit} calls/min\n\n"
                    f"Refresh page in a few moments to see progress..."
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
                ]
                
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
                        f"🚀 Worker started (PID: {process.pid}). Track progress in Status Monitor and live log below."
                    )
                except Exception as exc:
                    st.error(f"❌ Failed to start enrichment worker: {exc}")

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
                with st.expander("Worker Log (latest lines)", expanded=return_code is None):
                    if log_text:
                        st.code(log_text, language="text")
                    else:
                        st.caption("No log output yet.")

# ═════════════════════════════════════════════════════════════════════════════
# TAB 2: Status Monitor
# ═════════════════════════════════════════════════════════════════════════════

with tab2:
    st.header("📊 Enrichment Status Monitor")
    
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
                "Status": job.status.upper(),
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
        else:
            st.info("No company output available for this job yet.")

        st.markdown("**Contact-Level Output**")
        if contact_rows:
            st.dataframe(contact_rows, use_container_width=True, hide_index=True)
        else:
            st.info("No enriched contacts available for this job yet.")

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
                else:
                    st.caption("No company-level enrichment output recorded.")

                st.markdown("**Contact-Level Output**")
                if contact_rows:
                    st.dataframe(contact_rows, use_container_width=True, hide_index=True)
                else:
                    st.caption("No contact-level enrichment output recorded.")

st.divider()

# Footer
st.markdown(
    """
    ---
    **Documentation:** See `ENRICHMENT_GUIDE.md` for detailed usage instructions.
    
    **Support:** For API issues, check Smartlead documentation or contact support.
    """
)
