"""
Presentation Theme & Custom CSS Styling — Configures wide layout, hides left sidebar,
gives top header safe clearance, and styles TradingView-like filter pills & bottleneck chips.
"""

from __future__ import annotations

import streamlit as st


def apply_custom_theme() -> None:
    """Applies page config and custom CSS rules for the TradingView Top-Pill Screener UI."""
    st.set_page_config(
        page_title="US Stock Screener — TradingView Pill Layout",
        page_icon="📈",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    st.markdown(
        """
        <style>
        /* Hide left sidebar and its toggle arrow completely */
        [data-testid="stSidebar"], [data-testid="collapsedControl"] {
            display: none !important;
        }
        /* Make top Streamlit header bar transparent and give top row safe clearance */
        header[data-testid="stHeader"] {
            background: transparent !important;
            height: 2.5rem !important;
        }
        .block-container {
            padding-top: 3.2rem !important;
            padding-bottom: 1.5rem !important;
            max-width: 98% !important;
        }
        /* Style st.popover buttons to look like TradingView Filter Pills (prevent text truncation) */
        div[data-testid="stPopover"] > div > button {
            border-radius: 8px !important;
            padding: 0.2rem 0.5rem !important;
            min-height: 2.15rem !important;
            font-size: 0.78rem !important;
            font-weight: 600 !important;
            white-space: nowrap !important;
            border: 1px solid rgba(255, 255, 255, 0.22) !important;
            background-color: rgba(30, 41, 59, 0.85) !important;
            transition: all 0.15s ease-in-out !important;
        }
        div[data-testid="stPopover"] > div > button:hover {
            border-color: #38bdf8 !important;
            background-color: rgba(56, 189, 248, 0.15) !important;
        }
        .bottleneck-bar {
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            margin: 4px 0 8px 0;
        }
        .bn-chip {
            padding: 3px 8px;
            border-radius: 6px;
            font-size: 0.76rem;
            font-weight: 600;
            border: 1px solid rgba(128, 128, 128, 0.25);
        }
        .bn-tight {
            background-color: rgba(239, 68, 68, 0.14);
            color: #f87171;
            border-color: rgba(239, 68, 68, 0.4);
        }
        .bn-mid {
            background-color: rgba(245, 158, 11, 0.14);
            color: #fbbf24;
            border-color: rgba(245, 158, 11, 0.4);
        }
        .bn-open {
            background-color: rgba(16, 185, 129, 0.14);
            color: #34d399;
            border-color: rgba(16, 185, 129, 0.4);
        }
        .bn-off {
            background-color: rgba(148, 163, 184, 0.1);
            color: #94a3b8;
            text-decoration: line-through;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
