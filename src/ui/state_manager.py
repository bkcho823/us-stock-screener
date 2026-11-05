"""
Session State Manager — Handles filter configuration state, active preset switching,
active watchlist row tracking, and multi-tier market data loading (RAM -> Supabase -> Live Fetch).
"""

from __future__ import annotations

from typing import Dict, Any, Tuple

import pandas as pd
import streamlit as st

from src.config import (
    BUILTIN_PRESETS,
    get_default_layer0_config,
    get_default_layer1_config,
    get_default_layer2_config,
)
from src.infrastructure.market_repo import load_cached_market_data
from src.infrastructure.user_prefs_repo import load_tv_layout_id
from src.providers.eod_sync_service import refresh_daily_market_data


def init_session_state() -> None:
    """Initializes default session state keys on first page load."""
    if "layer0_cfg" not in st.session_state:
        st.session_state["layer0_cfg"] = get_default_layer0_config()
    if "layer1_cfg" not in st.session_state:
        st.session_state["layer1_cfg"] = get_default_layer1_config()
    if "layer2_cfg" not in st.session_state:
        st.session_state["layer2_cfg"] = get_default_layer2_config()
    if "active_preset_name" not in st.session_state:
        st.session_state["active_preset_name"] = list(BUILTIN_PRESETS.keys())[0]
    if "active_row_idx" not in st.session_state:
        st.session_state["active_row_idx"] = 0
    if "last_table_sel" not in st.session_state:
        st.session_state["last_table_sel"] = []
    if "tv_layout_id" not in st.session_state:
        st.session_state["tv_layout_id"] = load_tv_layout_id()


def apply_preset_to_state(preset_name: str, presets: Dict[str, Dict[str, Any]]) -> None:
    """Applies a built-in or user-saved preset into `st.session_state`."""
    if preset_name in presets:
        p = presets[preset_name]
        l0 = {**get_default_layer0_config(), **p.get("layer0", {})}
        l1 = {**get_default_layer1_config(), **p.get("layer1", {})}
        l2 = {**get_default_layer2_config(), **p.get("layer2", {})}
        st.session_state["layer0_cfg"] = l0
        st.session_state["layer1_cfg"] = l1
        st.session_state["layer2_cfg"] = l2
        st.session_state["active_preset_name"] = preset_name


def ensure_market_data_loaded() -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    3-Stage Data Loader:
    1. Session RAM (`cached_df_universe`, `cached_sp500_bm`)
    2. Supabase Cloud DB (`daily_snapshot`, `benchmark_sp500`)
    3. Initial Live EOD Fetch via `refresh_daily_market_data`
    """
    df_universe = st.session_state.get("cached_df_universe")
    sp500_bm = st.session_state.get("cached_sp500_bm")

    if df_universe is None or df_universe.empty or sp500_bm is None:
        df_universe, sp500_bm = load_cached_market_data()
        if df_universe is not None and not df_universe.empty and sp500_bm is not None:
            st.session_state["cached_df_universe"] = df_universe
            st.session_state["cached_sp500_bm"] = sp500_bm

    if df_universe is None or df_universe.empty or sp500_bm is None:
        st.info("Fetching initial US Market Universe & S&P 500 Benchmark...")
        progress_bar = st.progress(0, text="Starting initial EOD data fetch...")
        df_universe, sp500_bm = refresh_daily_market_data(
            enrich_yf=True,
            max_symbols_for_yf=800,
            progress_callback=lambda p, msg: progress_bar.progress(int(p * 100), text=msg),
        )
        st.session_state["cached_df_universe"] = df_universe
        st.session_state["cached_sp500_bm"] = sp500_bm
        progress_bar.empty()

    return df_universe, sp500_bm
