"""Shared Streamlit UI styling utilities."""

import streamlit as st


def apply_app_shell_styles(active_section: str) -> None:
    """Apply consistent typography and interactive sidebar navigation styles."""
    st.markdown(
        f"""
        <style>
            :root {{
                --ui-primary: #4f46e5;
                --ui-primary-soft: rgba(79, 70, 229, 0.12);
                --ui-success: #059669;
                --ui-warning: #d97706;
                --ui-danger: #dc2626;
                --ui-border: rgba(63, 63, 70, 0.2);
                --ui-surface: rgba(2, 6, 23, 0.02);
            }}

            .block-container {{
                padding-top: 1.1rem;
                padding-bottom: 2rem;
            }}

            html, body, [data-testid="stAppViewContainer"] {{
                font-size: 14px;
            }}

            p, li, label, [data-testid="stMarkdownContainer"] {{
                font-size: 0.96rem;
            }}

            h1, h2, h3 {{
                letter-spacing: 0.2px;
                line-height: 1.2;
            }}

            h1 {{
                font-size: clamp(2rem, 2.6vw, 2.4rem);
            }}

            h2 {{
                font-size: clamp(1.45rem, 1.8vw, 1.75rem);
            }}

            h3 {{
                font-size: clamp(1.15rem, 1.4vw, 1.28rem);
            }}

            hr {{
                margin: 0.8rem 0 1.1rem 0;
            }}

            [data-testid="stMetric"] [data-testid="stMetricLabel"] {{
                font-size: 0.88rem;
                font-weight: 600;
            }}

            [data-testid="stMetric"] [data-testid="stMetricValue"] {{
                font-size: clamp(1.35rem, 1.75vw, 1.7rem);
                line-height: 1.15;
            }}

            [data-testid="stMetric"] [data-testid="stMetricDelta"] {{
                font-size: 0.82rem;
            }}

            [data-baseweb="tab-list"] button [data-testid="stMarkdownContainer"] p {{
                font-size: 0.94rem;
                font-weight: 500;
            }}

            [data-testid="stButton"] button,
            [data-testid="baseButton-secondary"] {{
                border-radius: 10px;
                font-size: 0.92rem;
                border: 1px solid var(--ui-border);
                transition: all 0.16s ease;
            }}

            [data-testid="stButton"] button[kind="primary"] {{
                box-shadow: 0 4px 14px rgba(79, 70, 229, 0.2);
            }}

            [data-testid="stButton"] button:hover {{
                transform: translateY(-1px);
            }}

            [data-testid="stTextInput"] input,
            [data-testid="stSelectbox"] div[data-baseweb="select"],
            [data-testid="stTextArea"] textarea,
            [data-testid="stNumberInput"] input {{
                border-radius: 10px;
            }}

            .ui-hero {{
                border: 1px solid var(--ui-border);
                border-radius: 14px;
                padding: 0.85rem 1rem;
                background: linear-gradient(90deg, var(--ui-primary-soft), rgba(99, 102, 241, 0.02));
                margin-bottom: 0.75rem;
            }}

            .ui-kpi-card {{
                border: 1px solid var(--ui-border);
                border-radius: 12px;
                padding: 0.75rem 0.95rem;
                background: var(--ui-surface);
                min-height: 78px;
            }}

            .ui-kpi-label {{
                font-size: 0.78rem;
                text-transform: uppercase;
                letter-spacing: 0.06em;
                opacity: 0.72;
                margin-bottom: 0.15rem;
            }}

            .ui-kpi-value {{
                font-size: 1.35rem;
                font-weight: 700;
                line-height: 1.15;
            }}

            .ui-success {{ color: var(--ui-success); }}
            .ui-warning {{ color: var(--ui-warning); }}
            .ui-danger {{ color: var(--ui-danger); }}

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

            [data-testid="stSidebar"] [data-testid="stVerticalBlock"] > div:has(> [data-testid="stMetric"]) {{
                border: 1px solid var(--ui-border);
                border-radius: 12px;
                padding: 0.4rem 0.55rem;
                background: var(--ui-surface);
            }}
        </style>
        """,
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.markdown("### ⚡ Data Pipeline Studio")
        st.caption(f"Active section: **{active_section}**")
