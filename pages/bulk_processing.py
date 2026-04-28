"""Bulk Processing Page with Database Persistence and Resumability."""

import os
import tempfile
import time
from io import BytesIO
from datetime import datetime
from typing import List, Optional, Any

import pandas as pd
import streamlit as st
from sqlalchemy.orm import Session

from scraper.bulk_processor import ExcelProcessor, PLATFORM_CONFIGS, process_excel_file_with_db
from scraper.database import DatabaseManager, get_database_url
from scraper.models import BulkJob
from scraper.ui_styles import apply_app_shell_styles


def build_export_dataframes(results: List[dict]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build company, key person, and enriched contact export dataframes from job results."""
    company_rows = []
    key_person_rows = []
    enriched_contact_rows = []

    for result in results:
        product_values = result.get("platform_products") or result.get("salesforce_products", [])
        enrichment_payload: dict[str, Any] = result.get("smartlead_enrichment") or {}
        enrichment_stats = enrichment_payload.get("stats") or {}
        company_rows.append({
            "Original_URL": result.get("original_url", ""),
            "Company_Name": result.get("company_name", ""),
            "Company_URL": result.get("company_url", ""),
            "Location": result.get("location", ""),
            "Industry": result.get("industry", ""),
            "Company_Size": result.get("company_size", ""),
            "Segmentation": result.get("segmentation", ""),
            "Platform_Products": ", ".join(product_values),
            "Confidence_Score": result.get("confidence_score", 0.0),
            "Enrichment_Status": result.get("enrichment_status", "pending"),
            "Enriched_Contacts": enrichment_stats.get("contacts_found", 0),
            "Valid_Emails": enrichment_stats.get("valid_emails_found", 0),
        })

        for person in result.get("key_persons", []):
            key_person_rows.append({
                "Original_URL": result.get("original_url", ""),
                "Company_Name": result.get("company_name", ""),
                "Company_URL": result.get("company_url", ""),
                "Person_Name": person.get("name", ""),
                "Title": person.get("title", ""),
                "Contact": person.get("contact", ""),
            })

        for contact in enrichment_payload.get("contacts_enriched", []) or []:
            enriched_contact_rows.append({
                "Company_Name": result.get("company_name", ""),
                "Company_URL": result.get("company_url", ""),
                "First_Name": contact.get("firstName", ""),
                "Last_Name": contact.get("lastName", ""),
                "Title": contact.get("title", ""),
                "LinkedIn": contact.get("linkedin", ""),
                "Email": contact.get("email_id", ""),
                "Verification_Status": contact.get("verification_status", ""),
                "Email_Status": contact.get("email_status", ""),
                "Email_Source": contact.get("email_source", ""),
            })

    company_df = pd.DataFrame(company_rows)
    key_person_df = pd.DataFrame(key_person_rows)
    enriched_contacts_df = pd.DataFrame(enriched_contact_rows)

    if key_person_df.empty:
        key_person_df = pd.DataFrame(columns=[
            "Original_URL", "Company_Name", "Company_URL", "Person_Name", "Title", "Contact"
        ])

    if enriched_contacts_df.empty:
        enriched_contacts_df = pd.DataFrame(columns=[
            "Company_Name", "Company_URL", "First_Name", "Last_Name", "Title", "LinkedIn",
            "Email", "Verification_Status", "Email_Status", "Email_Source"
        ])

    return company_df, key_person_df, enriched_contacts_df


def dataframe_to_excel_bytes(df: pd.DataFrame, sheet_name: str) -> bytes:
    """Convert dataframe to Excel bytes for download."""
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
    buffer.seek(0)
    return buffer.getvalue()


def render_job_downloads(job_id: str, db: DatabaseManager, file_prefix: str, render_context: str = "default"):
    """Render download buttons for company and key person exports."""
    results = db.get_job_results(job_id)
    if not results:
        st.info("No saved company results available for download yet.")
        return

    company_df, key_person_df, enriched_contacts_df = build_export_dataframes(results)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    st.markdown("### 📥 Download Processed Data")
    col1, col2, col3 = st.columns(3)

    with col1:
        st.download_button(
            label="📥 Download Company Data",
            data=dataframe_to_excel_bytes(company_df, "Companies"),
            file_name=f"{file_prefix}_companies_{timestamp}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key=f"download_company_{job_id}_{render_context}",
        )

    with col2:
        st.download_button(
            label="📥 Download Key Persons Data",
            data=dataframe_to_excel_bytes(key_person_df, "KeyPersons"),
            file_name=f"{file_prefix}_key_persons_{timestamp}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key=f"download_key_persons_{job_id}_{render_context}",
        )

    with col3:
        st.download_button(
            label="📥 Download Enriched Contacts",
            data=dataframe_to_excel_bytes(enriched_contacts_df, "EnrichedContacts"),
            file_name=f"{file_prefix}_enriched_contacts_{timestamp}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key=f"download_enriched_contacts_{job_id}_{render_context}",
        )

# Page configuration
st.set_page_config(
    page_title="Batch URL Pipeline",
    page_icon="📊",
    layout="wide"
)
apply_app_shell_styles("Batch URL")

# Initialize session state
db_url = get_database_url()

if "db_manager" not in st.session_state:
    st.session_state.db_manager = DatabaseManager(db_url)

if "current_job_id" not in st.session_state:
    st.session_state.current_job_id = None

# ── Page Header ──────────────────────────────────────────────────────────────
st.title("📊 Batch URL Processing Workspace")
st.markdown(
    """
    <div class="ui-hero">
        <strong>Process URL lists at scale with consistent extraction quality.</strong><br/>
        Upload Excel URLs, run AI-powered extraction, and review structured outputs for companies and contacts.
    </div>
    """,
    unsafe_allow_html=True,
)

db = st.session_state.db_manager

with st.sidebar:
    st.header("⚙️ Batch Settings")

    ai_provider = st.radio(
        "AI Provider",
        ["Ollama", "Gemini"],
        help="Choose between local Ollama or cloud Gemini"
    )

    ai_provider_lower = ai_provider.lower()

    if ai_provider_lower == "ollama":
        ai_model = st.selectbox(
            "Ollama Model",
            ["mistral:7b", "neural-chat:7b", "llama2:7b", "dolphin-mixtral:latest"],
            help="Select model available in your Ollama installation"
        )
    else:
        ai_model = st.selectbox(
            "Gemini Model",
            ["gemini-1.5-pro", "gemini-1.5-flash", "gemini-pro"],
            help="Available Gemini models"
        )

    with st.expander("Processing Performance", expanded=True):
        batch_size = st.slider(
            "URLs per batch",
            min_value=10,
            max_value=100,
            value=50,
            step=10,
            help="Smaller batches are slower but more reliable",
        )

        max_workers = st.slider(
            "Concurrent workers",
            min_value=1,
            max_value=10,
            value=3,
            step=1,
            help="Higher values are faster but may hit rate limits",
        )

        batch_delay = st.slider(
            "Delay between batches (seconds)",
            min_value=0,
            max_value=30,
            value=5,
            step=1,
            help="Protect target websites and avoid bursts",
        )

    st.subheader("🎯 Extraction Target")
    platform_labels = {config["label"]: key for key, config in PLATFORM_CONFIGS.items()}
    selected_platform_label = st.selectbox(
        "Target Platform",
        options=list(platform_labels.keys()),
        index=0,
        help="Choose which platform-specific prompt should guide extraction.",
    )
    selected_platform = platform_labels[selected_platform_label]

    extra_instructions = st.text_area(
        "Additional extraction instructions",
        value="",
        height=140,
        placeholder=(
            "Examples:\n"
            "- Focus on implementation partners only\n"
            "- Look for Snowpark or data cloud references\n"
            "- For Custom mode, describe exactly what to extract"
        ),
        help="Optional instructions appended to the default extraction prompt for every URL in this job.",
    )

# ── Tabs for different sections ───────────────────────────────────────────────
tab_new_job, tab_job_history, tab_resume = st.tabs(
    ["🚀 New Batch Job", "📋 Job Results", "▶️ Resume Job"]
)

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1: NEW PROCESSING JOB
# ═══════════════════════════════════════════════════════════════════════════════

with tab_new_job:
    st.header("🚀 Start Data Processing")
    st.caption("Flow: Job Setup → File Upload → Run Processing → Review Final Output")

    processing_mode_options = {
        "URL Scraping + AI Extraction": "scrape",
        "Direct Company Input (Skip Scraping)": "direct_company",
    }
    selected_mode_label = st.radio(
        "Processing Mode",
        options=list(processing_mode_options.keys()),
        horizontal=True,
        help="Use direct mode when your Excel already has company name and company URL.",
    )
    processing_mode = processing_mode_options[selected_mode_label]

    job_name = st.text_input(
        "Batch job name",
        value="",
        placeholder="e.g., Snowflake EMEA Batch - Apr 2026",
        help="Optional human-readable label for this processing job.",
    )

    col1, col2 = st.columns([2, 1])

    with col1:
        # File upload
        uploaded_file = st.file_uploader(
            (
                "Upload Excel file (must include `URL` column)"
                if processing_mode == "scrape"
                else "Upload Excel file (must include `Company Name` and `Company URL` columns)"
            ),
            type=["xlsx", "xls"],
            help=(
                "Scrape mode: provide URL column with valid HTTP(S) links."
                if processing_mode == "scrape"
                else "Direct mode: provide Company Name + Company URL. Optional: Location, Industry, Segmentation, Company Size, Platform Products."
            ),
        )

    with col2:
        st.markdown("### 📋 Sample Format")
        if processing_mode == "scrape":
            st.markdown("""
            ```
            URL
            https://example.com
            https://company.org
            ```
            """)
        else:
            st.markdown("""
            ```
            Company Name,Company URL
            Acme Inc,https://acme.com
            Contoso,https://contoso.ai
            ```
            """)

    if uploaded_file:
        st.success("✓ File uploaded successfully")

        # Preview URLs
        with st.expander("👀 Preview URLs to Process"):
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
                    tmp.write(uploaded_file.getbuffer())
                    temp_input_path = tmp.name

                excel_proc = ExcelProcessor()
                if processing_mode == "scrape":
                    rows = excel_proc.read_urls_from_excel(temp_input_path)
                    preview_df = pd.DataFrame(rows[:20]).rename(columns={
                        "url": "URL",
                        "segmentation": "Segmentation",
                        "company_size": "Company_Size",
                        "platform_products": "Platform_Products",
                        "salesforce_products": "Salesforce_Products",
                    })
                else:
                    rows = excel_proc.read_companies_from_excel(temp_input_path)
                    preview_df = pd.DataFrame(rows[:20]).rename(columns={
                        "company_name": "Company_Name",
                        "company_url": "Company_URL",
                        "location": "Location",
                        "industry": "Industry",
                        "segmentation": "Segmentation",
                        "company_size": "Company_Size",
                        "platform_products": "Platform_Products",
                    })

                st.info(
                    f"Found {len(rows)} valid unique {'URLs' if processing_mode == 'scrape' else 'companies'}"
                )
                st.dataframe(preview_df, use_container_width=True)

                if len(rows) > 20:
                    st.caption(f"... and {len(rows) - 20} more URLs")

                os.unlink(temp_input_path)
            except Exception as e:
                st.error(f"Error reading Excel file: {e}")

        # Start processing button
        if st.button("🚀 Start Processing", use_container_width=True, type="primary"):
            # Save uploaded file
            with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp_input:
                tmp_input.write(uploaded_file.getbuffer())
                temp_input_path = tmp_input.name

            with tempfile.NamedTemporaryFile(delete=False, suffix='_results.xlsx') as tmp_output:
                temp_output_path = tmp_output.name

            # Create containers for progress
            progress_container = st.container()
            status_container = st.container()
            results_container = st.container()

            with progress_container:
                st.subheader("📊 Processing Progress")
                progress_bar = st.progress(0)
                status_text = st.empty()
                batch_info = st.empty()

            with status_container:
                st.subheader("🔍 Live Status")
                col1, col2, col3, col4 = st.columns(4)
                processed_metric = col1.empty()
                successful_metric = col2.empty()
                failed_metric = col3.empty()
                success_rate_metric = col4.empty()

            start_time = time.time()

            def progress_callback(job_stats: dict, batch_num: int, total_batches: int):
                """Update progress in real-time."""
                progress = job_stats["progress_percentage"] / 100 if job_stats["progress_percentage"] else 0
                progress_bar.progress(min(progress, 0.99))

                processed = job_stats["completed_urls"]
                successful = processed - job_stats["failed_urls"]
                failed = job_stats["failed_urls"]
                success_rate = (successful / max(processed, 1)) * 100
                unit_label = "URLs" if processing_mode == "scrape" else "companies"

                status_text.markdown(f"""
                **Batch {batch_num}/{total_batches}** | 
                **Progress:** {processed}/{job_stats['total_urls']} {unit_label}
                """)

                batch_info.info(
                    f"⏱️ Elapsed: {time.time() - start_time:.0f}s | "
                    f"⚡ Rate: {processed / max(time.time() - start_time, 1):.2f} URLs/sec"
                )

                processed_metric.metric("Processed", processed)
                successful_metric.metric("Successful", successful)
                failed_metric.metric("Failed", failed)
                success_rate_metric.metric("Success Rate", f"{success_rate:.1f}%")

            try:
                status_text.markdown("🚀 **Starting data processing pipeline...**")

                job_id = process_excel_file_with_db(
                    input_file=temp_input_path,
                    output_file=temp_output_path,
                    batch_size=batch_size,
                    ai_provider=ai_provider_lower,
                    ai_model=ai_model,
                    progress_callback=progress_callback,
                    db_url=db_url,
                    platform=selected_platform,
                    extra_instructions=extra_instructions,
                    job_name=job_name.strip() or None,
                    processing_mode=processing_mode,
                )

                st.session_state.current_job_id = job_id

                progress_bar.progress(1.0)
                status_text.markdown("✅ **Processing completed successfully**")

                # Fetch final statistics
                final_stats = db.get_job_stats(job_id)

                with results_container:
                    st.header("📈 Final Output")
                    st.caption("Review and download company, key people, and enrichment-ready outputs.")
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("Total URLs", final_stats["total_urls"])
                    with col2:
                        st.metric("Successful", final_stats["completed_urls"] - final_stats["failed_urls"])
                    with col3:
                        st.metric("Failed", final_stats["failed_urls"])
                    with col4:
                        success_rate = (final_stats["completed_urls"] - final_stats["failed_urls"]) / max(final_stats["completed_urls"], 1) * 100
                        st.metric("Success Rate", f"{success_rate:.1f}%")

                    st.markdown(f"""
                    ### ⏱️ Processing Time
                    **Total Time:** {(time.time() - start_time) / 60:.2f} minutes
                    **Started:** {final_stats['created_at']}
                    **Completed:** {final_stats['completed_at']}
                    """)

                    st.success("🎉 **Results ready for download!**")

                    saved_results = db.get_job_results(job_id)
                    company_df, key_person_df, enriched_contacts_df = build_export_dataframes(saved_results)

                    if processing_mode == "direct_company":
                        profiled_count = len(saved_results)
                        fallback_unknown_count = sum(
                            1
                            for result in saved_results
                            if (result.get("location") in (None, "", "Unknown"))
                            or (result.get("industry") in (None, "", "Unknown"))
                        )
                        st.info(
                            f"Direct mode summary: {profiled_count} companies profiled, "
                            f"{fallback_unknown_count} rows used Unknown fallback values."
                        )

                    st.subheader("Company Output")
                    st.dataframe(company_df, use_container_width=True, hide_index=True)

                    st.subheader("Key People Output")
                    if key_person_df.empty:
                        st.info("No key people rows available for this run.")
                    else:
                        st.dataframe(key_person_df, use_container_width=True, hide_index=True)

                    st.subheader("Enrichment Output")
                    if enriched_contacts_df.empty:
                        st.info("No Smartlead enrichment rows available yet.")
                    else:
                        st.dataframe(enriched_contacts_df, use_container_width=True, hide_index=True)

                    if os.path.exists(temp_output_path):
                        with open(temp_output_path, "rb") as file:
                            st.download_button(
                                label="📥 Download Full Results Excel",
                                data=file,
                                file_name=f"bulk_results_{job_id[:8]}_{int(time.time())}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                use_container_width=True,
                            )

                    render_job_downloads(job_id, db, f"job_{job_id[:8]}", render_context="current_job_results")

            except Exception as e:
                st.error(f"❌ Processing failed: {e}")
                status_text.markdown(f"💥 **Error:** {e}")

            finally:
                # Cleanup temp files
                try:
                    if os.path.exists(temp_input_path):
                        os.unlink(temp_input_path)
                    # Don't delete temp_output_path yet, user might want to download
                except OSError:
                    pass


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2: JOB HISTORY
# ═══════════════════════════════════════════════════════════════════════════════

with tab_job_history:
    st.header("📋 Job History & Results")

    # Get all jobs
    all_jobs = db.get_all_jobs(limit=100)

    job_stats_by_id = {job.job_id: db.get_job_stats(job.job_id) for job in all_jobs}
    completed_jobs = []
    for job in all_jobs:
        stats = job_stats_by_id.get(job.job_id, {})
        total_urls = int(stats.get("total_urls", 0) or 0)
        completed_urls = int(stats.get("completed_urls", 0) or 0)
        pending_urls = int(stats.get("pending_urls", 0) or 0)
        if total_urls > 0 and pending_urls == 0 and completed_urls >= total_urls:
            completed_jobs.append(job)

    with st.expander("📥 Download Exports", expanded=True):
        if completed_jobs:
            download_job_options = {
                f"{(job.job_name or 'Untitled Job')} - {job.job_id[:8]} ({job.created_at.strftime('%Y-%m-%d %H:%M')})": job.job_id
                for job in completed_jobs
            }
            selected_download_label = st.selectbox(
                "Select completed job for download",
                list(download_job_options.keys()),
                key="download_job_selection",
            )
            selected_download_job_id = download_job_options[selected_download_label]
            render_job_downloads(selected_download_job_id, db, f"job_{selected_download_job_id[:8]}", render_context="history_downloads")
        else:
            st.info("No completed jobs yet. Run processing to enable company and key-person downloads.")

    if all_jobs:
        # Create job summary dataframe
        job_data = []
        for job in all_jobs:
            stats = job_stats_by_id.get(job.job_id, {})
            job_data.append({
                "Job Name": job.job_name or "Untitled Job",
                "Job ID": job.job_id[:8],
                "Status": job.status.upper(),
                "Total URLs": stats["total_urls"],
                "Completed": stats["completed_urls"],
                "Failed": stats["failed_urls"],
                "Progress": f"{stats['progress_percentage']:.1f}%",
                "Created": job.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "Full ID": job.job_id,
            })

        job_df = st.dataframe(
            [
                {
                    "Job Name": d["Job Name"],
                    "Job ID": d["Job ID"],
                    "Status": d["Status"],
                    "Progress": d["Progress"],
                    "Completed/Total": f"{d['Completed']}/{d['Total URLs']}",
                    "Failed": d["Failed"],
                    "Created": d["Created"],
                }
                for d in job_data
            ],
            use_container_width=True,
        )

        # Detailed view
        st.subheader("📊 Detailed Job Information")
        selected_job_idx = st.selectbox(
            "Select a job to view details",
            range(len(job_data)),
            format_func=lambda i: f"{job_data[i]['Job Name']} | {job_data[i]['Job ID']} - {job_data[i]['Status']}"
        )

        selected_job = job_data[selected_job_idx]
        job_id = selected_job["Full ID"]

        with st.expander("Job Details", expanded=True):
            stats = db.get_job_stats(job_id)

            col1, col2 = st.columns(2)

            with col1:
                st.markdown(f"""
                **Job Name:** {stats.get('job_name') or 'Untitled Job'}
                **Job ID:** `{job_id}`
                **Status:** {stats['status'].upper()}
                **Total URLs:** {stats['total_urls']}
                **Processed:** {stats['completed_urls']}
                """)

            with col2:
                st.markdown(f"""
                **Failed:** {stats['failed_urls']}
                **Pending:** {stats['pending_urls']}
                **Progress:** {stats['progress_percentage']:.1f}%
                **Created:** {stats['created_at']}
                """)

            # Download results if completed
            if stats['status'] == 'completed':
                st.success("✓ This job is completed. Results are available.")
                historical_results = db.get_job_results(job_id)
                hist_company_df, hist_key_person_df, hist_enriched_contacts_df = build_export_dataframes(historical_results)

                st.subheader("Company Output")
                st.dataframe(hist_company_df, use_container_width=True, hide_index=True)

                st.subheader("Key People Output")
                if hist_key_person_df.empty:
                    st.info("No key people rows available for this job.")
                else:
                    st.dataframe(hist_key_person_df, use_container_width=True, hide_index=True)

                st.subheader("Enrichment Output")
                if hist_enriched_contacts_df.empty:
                    st.info("No Smartlead enrichment rows available for this job yet.")
                else:
                    st.dataframe(hist_enriched_contacts_df, use_container_width=True, hide_index=True)
                render_job_downloads(job_id, db, f"job_{job_id[:8]}", render_context="history_details")
    else:
        st.info("No processing jobs found. Start a new job to see history.")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3: RESUME PROCESSING
# ═══════════════════════════════════════════════════════════════════════════════

with tab_resume:
    st.header("▶️ Resume Interrupted Processing")

    # Get non-completed jobs
    all_jobs = db.get_all_jobs(limit=100)
    pending_jobs = [j for j in all_jobs if j.status in ["pending", "processing", "failed"]]

    if pending_jobs:
        st.info("🔄 Select a job to resume processing")

        job_options = {
            f"{(j.job_name or 'Untitled Job')} | {j.job_id[:8]} - {j.status.upper()} ({db.get_job_stats(j.job_id)['completed_urls']}/{j.total_urls})": j.job_id
            for j in pending_jobs
        }

        selected_job_display = st.selectbox(
            "Choose a job to resume",
            list(job_options.keys()),
            key="resume_selection"
        )

        selected_job_id = job_options[selected_job_display]
        selected_job = [j for j in pending_jobs if j.job_id == selected_job_id][0]

        # Show job details
        stats = db.get_job_stats(selected_job_id)

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total URLs", stats["total_urls"])
        col2.metric("Already Completed", stats["completed_urls"])
        col3.metric("Failed", stats["failed_urls"])
        col4.metric("Remaining", stats["pending_urls"])

        st.info(f"✓ {stats['pending_urls']} URLs remaining to process")

        if st.button("▶️ Resume This Job", use_container_width=True, type="primary"):
            st.warning("""
            Resume functionality is available via the processing pipeline.
            The system will:
            1. Skip already processed URLs
            2. Retry failed URLs up to 3 times
            3. Continue from where it left off
            4. Update results in the database
            
            This feature will be fully integrated in the next update.
            """)

    else:
        st.success("✓ All jobs are completed! No resumable jobs found.")
        st.info("Start a new processing job to get started.")
