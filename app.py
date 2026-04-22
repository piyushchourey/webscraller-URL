"""Streamlit UI — Web Scraper + AI Analysis (Gemini or Ollama)."""

import os
import streamlit as st

from scraper import WebScraper
from scraper.core import ScraperError
from scraper.ai_analyzer import ANALYSIS_TEMPLATES, get_analyzer

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(page_title="Web Scraper + AI", page_icon="🔍", layout="wide")

# ── Navigation ───────────────────────────────────────────────────────────────
st.sidebar.title("🧭 Navigation")
page = st.sidebar.radio(
    "Choose a page:",
    ["🔍 Single URL Processing", "📊 Bulk Processing"],
    help="Select processing mode"
)

if page == "📊 Bulk Processing":
    st.switch_page("pages/bulk_processing.py")

# ── Single URL Processing (Main Page) ────────────────────────────────────────
st.title("🔍 Web Scraper + AI Analysis")
st.markdown("Scrape any webpage and use AI to extract exactly the information you need.")

# ── Sidebar: settings ───────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Settings")
    
    # AI Provider Selection
    ai_provider = st.radio(
        "AI Provider",
        ["Gemini", "Ollama"],
        help="Choose between Gemini (cloud) or Ollama (local)"
    )
    
    st.divider()
    
    if ai_provider == "Gemini":
        api_key = st.text_input("Gemini API Key", type="password", help="Get yours at aistudio.google.com")
        model_choice = st.selectbox("Gemini Model", ["gemini-2.5-flash","gemini-2.0-flash", "gemini-2.5-flash-preview-04-17", "gemini-2.5-pro-preview-03-25"])
    else:  # Ollama
        api_key = None
        ollama_base_url = st.text_input("Ollama Server URL", value="http://localhost:11434", help="URL where Ollama is running")
        model_choice = st.text_input("Ollama Model", value="mistral:7b", help="e.g., mistral:7b, llama2:7b, neural-chat")
    
    st.divider()
    st.markdown(
        "**How it works**\n"
        "1. Enter a URL to scrape\n"
        "2. Raw content is extracted\n"
        "3. AI analyzes it with your prompt"
    )

# ── Cached instances ────────────────────────────────────────────────────────
@st.cache_resource
def get_scraper() -> WebScraper:
    return WebScraper()


# ── Main UI ──────────────────────────────────────────────────────────────────
# URL input
url = st.text_input("🌐 URL", placeholder="https://example.com/article")

# Scrape button
if st.button("Scrape", type="primary", disabled=not url):
    with st.spinner("Fetching and extracting content…"):
        try:
            result = get_scraper().scrape(url)
            st.session_state["scraped"] = result
            st.session_state.pop("analysis_history", None)
        except ScraperError as exc:
            st.error(f"**Scraping failed:** {exc}")
        except Exception as exc:
            st.error(f"**Unexpected error:** {exc}")

# ── Show scraped content ─────────────────────────────────────────────────────
if "scraped" in st.session_state:
    r = st.session_state["scraped"]
    st.divider()

    # Metrics row
    cols = st.columns(4)
    cols[0].metric("Title", r.title[:50] + ("…" if len(r.title) > 50 else ""))
    cols[1].metric("Words", f"{r.word_count:,}")
    cols[2].metric("Links", len(r.links))
    cols[3].metric("HTTP Status", r.status_code)

    # Scraped content tabs
    tab_text, tab_meta, tab_links = st.tabs(["📄 Extracted Text", "📋 Metadata", "🔗 Links"])

    with tab_text:
        with st.expander("View raw extracted text", expanded=False):
            st.text(r.main_text[:5000] + ("\n\n[…truncated for display]" if len(r.main_text) > 5000 else ""))

    with tab_meta:
        st.json({
            "url": r.url,
            "title": r.title,
            "meta_description": r.meta_description,
            "author": r.author,
            "publish_date": r.publish_date,
            "word_count": r.word_count,
            "scraped_at": r.scraped_at,
        })

    with tab_links:
        if r.links:
            for link in r.links[:30]:
                st.markdown(f"- {link}")
        else:
            st.info("No links found.")

    # ── AI Analysis Section ──────────────────────────────────────────────────
    st.divider()
    provider_display = "Gemini" if ai_provider == "Gemini" else f"Ollama ({model_choice})"
    st.subheader(f"🤖 AI Analysis with {provider_display}")

    # Check configuration validity
    if ai_provider == "Gemini" and not api_key:
        st.warning("Enter your Gemini API key in the sidebar to enable AI analysis.")
    elif ai_provider == "Ollama":
        st.info(f"Using Ollama at {ollama_base_url}")
    
    if (ai_provider == "Gemini" and api_key) or ai_provider == "Ollama":
        # Template buttons
        st.markdown("**Quick analysis templates:**")
        template_cols = st.columns(len(ANALYSIS_TEMPLATES))
        selected_template = None
        for i, (name, _) in enumerate(ANALYSIS_TEMPLATES.items()):
            if template_cols[i].button(name, use_container_width=True):
                selected_template = name

        # Custom prompt
        custom_prompt = st.text_area(
            "Or write your own analysis prompt:",
            placeholder="e.g., Extract all product prices and features mentioned in this page…",
            height=100,
        )

        # Determine which prompt to use
        analysis_prompt = None
        if selected_template:
            analysis_prompt = ANALYSIS_TEMPLATES[selected_template]
            st.info(f"**Template:** {selected_template}")
        elif custom_prompt:
            if st.button("🚀 Analyze", type="primary"):
                analysis_prompt = custom_prompt

        # Run analysis
        if analysis_prompt:
            spinner_text = f"{ai_provider} is analyzing the content…"
            with st.spinner(spinner_text):
                try:
                    if ai_provider == "Gemini":
                        analyzer = get_analyzer(provider="gemini", api_key=api_key, model=model_choice)
                    else:  # Ollama
                        analyzer = get_analyzer(provider="ollama", base_url=ollama_base_url, model=model_choice)
                    
                    analysis = analyzer.analyze(
                        text=r.main_text,
                        user_prompt=analysis_prompt,
                        source_url=r.url,
                        page_title=r.title,
                    )
                    # Store in history
                    if "analysis_history" not in st.session_state:
                        st.session_state["analysis_history"] = []
                    st.session_state["analysis_history"].append(analysis)
                except (ValueError, ConnectionError) as exc:
                    st.error(str(exc))
                except Exception as exc:
                    st.error(f"**Gemini error:** {exc}")

        # Display analysis history
        if "analysis_history" in st.session_state and st.session_state["analysis_history"]:
            for i, a in enumerate(reversed(st.session_state["analysis_history"])):
                with st.container(border=True):
                    st.markdown(f"**Prompt:** {a.prompt_used}")
                    st.markdown(a.response_text)
                    footer_cols = st.columns(3)
                    footer_cols[0].caption(f"Model: {a.model}")
                    footer_cols[1].caption(f"Tokens: {a.tokens_used:,}")
                    footer_cols[2].download_button(
                        "⬇️ Download",
                        data=a.response_text,
                        file_name=f"analysis_{i}.md",
                        mime="text/markdown",
                        key=f"dl_{i}",
                    )

    # Download raw text
    st.divider()
    st.download_button(
        "⬇️ Download raw scraped text",
        data=r.main_text,
        file_name="scraped_content.txt",
        mime="text/plain",
    )