"""Bulk Processing Page for handling multiple URLs from Excel files."""

import os
import tempfile
import time
from typing import List

import streamlit as st

from scraper.bulk_processor import ExcelProcessor, process_excel_file
from scraper.models import BulkJob

# Page configuration
st.set_page_config(
    page_title="Bulk URL Processing",
    page_icon="📊",
    layout="wide"
)

# ── Page Header ──────────────────────────────────────────────────────────────
st.title("📊 Bulk URL Processing")
st.markdown("""
Process multiple URLs from an Excel file with intelligent batching and AI analysis.
Perfect for large-scale company data extraction.
""")


def _run_bulk_processing(
    urls: List[str],
    temp_input_path: str,
    batch_size: int,
    ai_provider: str,
    ai_model: str
):
    """Execute bulk processing with progress tracking."""

    progress_container = st.container()
    status_container = st.container()
    results_container = st.container()

    with progress_container:
        st.subheader("📊 Processing Progress")
        progress_bar = st.progress(0)
        status_text = st.empty()
        batch_status = st.empty()

    with status_container:
        st.subheader("🔍 Current Status")
        current_batch_text = st.empty()
        current_url_text = st.empty()
        time_elapsed_text = st.empty()

    start_time = time.time()

    def progress_callback(job: BulkJob, batch_num: int, total_batches: int):
        progress_bar.progress(job.progress_percentage / 100)
        status_text.markdown(f"""
**Overall Progress:** {job.processed_urls}/{job.total_urls} URLs processed
**Success Rate:** {((job.processed_urls - job.failed_urls) / max(job.processed_urls, 1)) * 100:.1f}%
**Failed URLs:** {job.failed_urls}
""")
        batch_status.markdown(f"**Batch {batch_num}/{total_batches} completed**")
        current_batch_text.markdown(f"**Current Batch:** {batch_num}/{total_batches}")
        time_elapsed_text.markdown(f"**Time Elapsed:** {time.time() - start_time:.1f} seconds")
        time.sleep(0.1)

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='_results.xlsx') as tmp_output:
            temp_output_path = tmp_output.name

        status_text.markdown("🚀 **Starting bulk processing...**")

        job = process_excel_file(
            input_file=temp_input_path,
            output_file=temp_output_path,
            batch_size=batch_size,
            ai_provider=ai_provider,
            ai_model=ai_model,
            progress_callback=progress_callback
        )

        progress_bar.progress(1.0)
        status_text.markdown("✅ **Processing completed!**")

        with results_container:
            st.header("📈 Final Results")
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total URLs", job.total_urls)
            with col2:
                st.metric("Successful", job.processed_urls - job.failed_urls)
            with col3:
                st.metric("Failed", job.failed_urls)
            with col4:
                success_rate = ((job.processed_urls - job.failed_urls) / max(job.processed_urls, 1)) * 100
                st.metric("Success Rate", f"{success_rate:.1f}%")

            if job.error_summary:
                st.subheader("⚠️ Error Summary")
                error_df = {
                    "Error Type": list(job.error_summary.keys()),
                    "Count": list(job.error_summary.values())
                }
                st.dataframe(error_df, use_container_width=True)

            st.success("🎉 **Results ready for download!**")
            with open(temp_output_path, "rb") as file:
                st.download_button(
                    label="📥 Download Results Excel",
                    data=file,
                    file_name=f"bulk_processing_results_{int(time.time())}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )

        try:
            os.unlink(temp_input_path)
            os.unlink(temp_output_path)
        except OSError:
            pass

    except Exception as e:
        st.error(f"❌ Processing failed: {e}")
        status_text.markdown("💥 **Processing failed**")
        try:
            os.unlink(temp_input_path)
        except OSError:
            pass


# ── Sidebar Configuration ─────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Processing Configuration")

    ai_provider = st.radio(
        "AI Provider",
        ["Ollama", "Gemini"],
        help="Choose between local Ollama or cloud Gemini"
    )

    st.subheader("Batch Settings")
    batch_size = st.slider(
        "URLs per batch",
        min_value=10,
        max_value=100,
        value=50,
        step=10,
        help="Smaller batches = slower but more reliable"
    )

    max_workers = st.slider(
        "Concurrent workers per batch",
        min_value=1,
        max_value=5,
        value=3,
        help="Workers process URLs simultaneously"
    )

    if ai_provider == "Ollama":
        ai_model = st.text_input("Ollama Model", value="mistral:7b")
    else:
        ai_model = st.selectbox("Gemini Model", [
            "gemini-2.5-flash",
            "gemini-2.0-flash",
            "gemini-2.5-flash-preview-04-17"
        ])

    st.divider()
    st.markdown("""
**💡 Tips:**
- Start with smaller batches (20-30) for testing
- Use Ollama for cost-free local processing
- Monitor progress in the main panel
""")


st.header("📁 Upload Excel File")
st.markdown("Upload an Excel file with a 'URL' column containing the websites to process.")

uploaded_file = st.file_uploader(
    "Choose Excel file",
    type=["xlsx", "xls"],
    help="File should contain a column named 'URL' with website addresses"
)

if uploaded_file is not None:
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp_file:
            tmp_file.write(uploaded_file.getvalue())
            temp_input_path = tmp_file.name

        excel_processor = ExcelProcessor()
        urls = excel_processor.read_urls_from_excel(temp_input_path)

        if urls:
            st.success(f"✅ Found {len(urls)} valid URLs in the Excel file")

            with st.expander("📋 Preview URLs (first 10)", expanded=True):
                preview_df = {"URL": urls[:10]}
                if len(urls) > 10:
                    st.markdown(f"*... and {len(urls) - 10} more URLs*")
                st.dataframe(preview_df, use_container_width=True)

            total_batches = (len(urls) + batch_size - 1) // batch_size
            estimated_time = len(urls) * 8

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total URLs", len(urls))
            with col2:
                st.metric("Batches", total_batches)
            with col3:
                st.metric("Est. Time", f"{estimated_time // 60}m {estimated_time % 60}s")

            st.header("🚀 Start Processing")

            if st.button("🔥 Start Bulk Processing", type="primary", use_container_width=True):
                _run_bulk_processing(
                    urls=urls,
                    temp_input_path=temp_input_path,
                    batch_size=batch_size,
                    ai_provider=ai_provider.lower(),
                    ai_model=ai_model
                )
        else:
            st.error("❌ No valid URLs found in the Excel file. Please ensure there's a 'URL' column with valid HTTP/HTTPS URLs.")

    except Exception as e:
        st.error(f"❌ Error reading Excel file: {e}")
        st.info("**Expected format:** Excel file with a column named 'URL' containing website addresses.")

else:
    st.info("💡 **Need a template?** Create an Excel file with a column named 'URL' and add your website addresses.")
    st.markdown("""
**Example Excel format:**
| URL |
|-----|
| https://www.company1.com |
| https://www.company2.com |
| https://www.company3.com |
""")


st.divider()
st.markdown("""
**🎯 Bulk Processing Features:**
- **Batch Processing**: Process URLs in configurable batches to avoid blocking
- **Concurrent Workers**: Multiple URLs processed simultaneously per batch
- **Progress Tracking**: Real-time progress updates and status monitoring
- **Error Recovery**: Robust error handling with detailed error summaries
- **AI Integration**: Structured data extraction using Ollama or Gemini
- **Memory Efficient**: Batch-wise processing prevents memory overload

**📊 Output Format:**
The results Excel file contains structured company data with columns for:
Company Name, Location, Website, Industry, Key Persons, and processing status.
""")


def _run_bulk_processing(
    urls: List[str],
    temp_input_path: str,
    batch_size: int,
    ai_provider: str,
    ai_model: str
):
    """Execute bulk processing with progress tracking."""

    # Create progress containers
    progress_container = st.container()
    status_container = st.container()
    results_container = st.container()

    with progress_container:
        st.subheader("📊 Processing Progress")
        progress_bar = st.progress(0)
        status_text = st.empty()
        batch_status = st.empty()

    with status_container:
        st.subheader("🔍 Current Status")
        current_batch_text = st.empty()
        current_url_text = st.empty()
        time_elapsed_text = st.empty()

    # Initialize processing variables
    start_time = time.time()
    processed_urls = 0
    current_batch = 0
    total_batches = (len(urls) + batch_size - 1) // batch_size

    def progress_callback(job: BulkJob, batch_num: int, total_batches: int):
        """Update progress in real-time."""
        nonlocal processed_urls, current_batch

        current_batch = batch_num
        processed_urls = job.processed_urls

        # Update progress bar
        progress = job.progress_percentage / 100
        progress_bar.progress(progress)

        # Update status text
        status_text.markdown(f"""
        **Overall Progress:** {job.processed_urls}/{job.total_urls} URLs processed
        **Success Rate:** {((job.processed_urls - job.failed_urls) / max(job.processed_urls, 1)) * 100:.1f}%
        **Failed URLs:** {job.failed_urls}
        """)

        # Update batch status
        batch_status.markdown(f"**Batch {batch_num}/{total_batches} completed**")

        # Update current status
        elapsed = time.time() - start_time
        current_batch_text.markdown(f"**Current Batch:** {batch_num}/{total_batches}")
        time_elapsed_text.markdown(f"**Time Elapsed:** {elapsed:.1f} seconds")

        # Force UI update
        time.sleep(0.1)

    try:
        # Create temporary output file
        with tempfile.NamedTemporaryFile(delete=False, suffix='_results.xlsx') as tmp_output:
            temp_output_path = tmp_output.name

        # Process the file
        status_text.markdown("🚀 **Starting bulk processing...**")

        job = process_excel_file(
            input_file=temp_input_path,
            output_file=temp_output_path,
            batch_size=batch_size,
            ai_provider=ai_provider,
            ai_model=ai_model,
            progress_callback=progress_callback
        )

        # Processing completed
        progress_bar.progress(1.0)
        status_text.markdown("✅ **Processing completed!**")

        # Show final results
        with results_container:
            st.header("📈 Final Results")

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total URLs", job.total_urls)
            with col2:
                st.metric("Successful", job.processed_urls - job.failed_urls)
            with col3:
                st.metric("Failed", job.failed_urls)
            with col4:
                success_rate = ((job.processed_urls - job.failed_urls) / max(job.processed_urls, 1)) * 100
                st.metric("Success Rate", f"{success_rate:.1f}%")

            # Error summary
            if job.error_summary:
                st.subheader("⚠️ Error Summary")
                error_df = {
                    "Error Type": list(job.error_summary.keys()),
                    "Count": list(job.error_summary.values())
                }
                st.dataframe(error_df, use_container_width=True)

            # Download button
            st.success("🎉 **Results ready for download!**")

            with open(temp_output_path, "rb") as file:
                st.download_button(
                    label="📥 Download Results Excel",
                    data=file,
                    file_name=f"bulk_processing_results_{int(time.time())}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )

        # Cleanup temporary files
        try:
            os.unlink(temp_input_path)
            os.unlink(temp_output_path)
        except:
            pass

    except Exception as e:
        st.error(f"❌ Processing failed: {e}")
        status_text.markdown("💥 **Processing failed**")

        # Cleanup on error
        try:
            os.unlink(temp_input_path)
        except:
            pass


# ── Footer ───────────────────────────────────────────────────────────────────
st.divider()
st.markdown("""
**🎯 Bulk Processing Features:**
- **Batch Processing**: Process URLs in configurable batches to avoid blocking
- **Concurrent Workers**: Multiple URLs processed simultaneously per batch
- **Progress Tracking**: Real-time progress updates and status monitoring
- **Error Recovery**: Robust error handling with detailed error summaries
- **AI Integration**: Structured data extraction using Ollama or Gemini
- **Memory Efficient**: Batch-wise processing prevents memory overload

**📊 Output Format:**
The results Excel file contains structured company data with columns for:
Company Name, Location, Website, Industry, Key Persons, and processing status.
""")