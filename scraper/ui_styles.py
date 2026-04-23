"""Shared Streamlit UI styling utilities."""

import streamlit as st


def apply_app_shell_styles(active_section: str) -> None:
    """Apply consistent typography and interactive sidebar navigation styles."""
    st.markdown(
        f"""
        <style>
            .block-container {{
                padding-top: 1.25rem;
            }}

            html, body, [data-testid="stAppViewContainer"] {{
                font-size: 15px;
            }}

            h1, h2, h3 {{
                letter-spacing: 0.2px;
                line-height: 1.2;
            }}

            h1 {{
                font-size: clamp(2rem, 2.6vw, 2.4rem);
            }}

            h2 {{
                font-size: clamp(1.55rem, 2vw, 1.9rem);
            }}

            h3 {{
                font-size: clamp(1.2rem, 1.5vw, 1.35rem);
            }}

            [data-testid="stMetric"] [data-testid="stMetricLabel"] {{
                font-size: 0.92rem;
                font-weight: 600;
            }}

            [data-testid="stMetric"] [data-testid="stMetricValue"] {{
                font-size: clamp(1.7rem, 2.2vw, 2rem);
                line-height: 1.15;
            }}

            [data-testid="stMetric"] [data-testid="stMetricDelta"] {{
                font-size: 0.88rem;
            }}

            [data-baseweb="tab-list"] button [data-testid="stMarkdownContainer"] p {{
                font-size: 0.98rem;
                font-weight: 500;
            }}

            [data-testid="stSidebarNav"] {{
                padding-top: 0.4rem;
            }}

            [data-testid="stSidebarNav"] ul {{
                gap: 0.3rem;
            }}

            [data-testid="stSidebarNav"] a {{
                border-radius: 10px;
                transition: all 0.18s ease-in-out;
                border: 1px solid transparent;
            }}

            [data-testid="stSidebarNav"] a:hover {{
                background: rgba(80, 120, 255, 0.08);
                border-color: rgba(80, 120, 255, 0.25);
            }}

            [data-testid="stSidebarNav"] a[aria-current="page"] {{
                background: rgba(80, 120, 255, 0.14);
                border-color: rgba(80, 120, 255, 0.42);
                font-weight: 600;
            }}

            [data-testid="stSidebarNav"] span {{
                text-transform: capitalize;
                font-size: 0.98rem;
            }}

            [data-testid="stSidebarNav"]::before {{
                content: "Workspace Modules";
                display: block;
                font-size: 0.78rem;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 0.08em;
                opacity: 0.75;
                margin: 0 0 0.35rem 0.15rem;
            }}
        </style>
        """,
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.caption(f"Active section: **{active_section}**")
