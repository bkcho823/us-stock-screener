"""
US Stock Momentum Screener — Thin Application Orchestrator (`app.py`)
Architecture: Clean 4-Tier Modular Design + Multi-Tab Layer Pipeline
  - Each Screening Layer (Layer 0 through Layer 5) is organized into its own dedicated Tab
    combining that layer's Filter Pills and that layer's Filtered Result Table.
  - The Live Interactive TradingView Advanced Chart Cockpit is grouped inside the Layer 3 (VCP Setups) Tab.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

# Anchor application root directory to sys.path for robust Cloud runtime resolution
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st

from src.layers import run_screening_pipeline
from src.ui import (
    apply_custom_theme,
    init_session_state,
    ensure_market_data_loaded,
    render_top_header,
    render_bottleneck_strip,
    render_layer0_tab_results,
    render_layer1_tab_results,
    render_layer2_tab_results,
    render_layer3_tab_results_with_chart,
    render_layer4_tab_results,
    render_layer5_tab_results,
)
from src.ui.pills.layer0_pills import render_layer0_pills
from src.ui.pills.layer1_pills import render_layer1_pills
from src.ui.pills.layer2_pills import render_layer2_pills
from src.ui.pills.layer3_pills import render_layer3_pills
from src.ui.pills.layer4_pills import render_layer4_pills
from src.ui.pills.layer5_pills import render_layer5_pills


def _execute_pipeline(df_universe, sp500_bm):
    return run_screening_pipeline(
        df_universe=df_universe,
        sp500_bm=sp500_bm,
        layer0_cfg=st.session_state["layer0_cfg"],
        layer1_cfg=st.session_state["layer1_cfg"],
        layer2_cfg=st.session_state.get("layer2_cfg"),
        layer3_cfg=st.session_state.get("layer3_cfg"),
        layer4_cfg=st.session_state.get("layer4_cfg"),
        layer5_cfg=st.session_state.get("layer5_cfg"),
    )


def main() -> None:
    # 1. Configure page theme & initialize session state
    apply_custom_theme()
    init_session_state()

    # 2. Load market snapshot & Multi-Index benchmark (Session RAM -> Supabase DB -> Live Fetch)
    df_universe, sp500_bm = ensure_market_data_loaded()

    # 3. Render Top Bar (Title, Regime Traffic Light, Preset Selector, Save Preset, BKCHO Chart URL, Refresh)
    render_top_header(sp500_bm)

    # 4. Initial pipeline pass (<15ms) to populate live tab badge counts
    result = _execute_pipeline(df_universe, sp500_bm)
    meta = result.summary_meta
    l0_cnt = meta.get("layer0_count", len(result.df_l0))
    l1_cnt = meta.get("qualified_count", 0)
    l2_cnt = meta.get("l2_qualified_count", l1_cnt)
    l3_cnt = meta.get("l3_qualified_count", 0)
    l4_cnt = meta.get("l4_qualified_count", 0)
    l5_cnt = meta.get("l5_qualified_count", 0)

    # 5. Separate Each Layer into its Own Dedicated Tab (Filter Pills + Result Table Together)
    tab_l0, tab_l1, tab_l2, tab_l3, tab_l4, tab_l5 = st.tabs(
        [
            f"🌐 Layer 0: Universe [{l0_cnt}]",
            f"📈 Layer 1: Trend (11 Rules) [{l1_cnt}]",
            f"🏆 Layer 2: Industry & CAN SLIM [{l2_cnt}]",
            f"🎯 Layer 3: VCP & TradingView Chart [{l3_cnt}]",
            f"⚡ Layer 4: Entry Triggers [{l4_cnt}]",
            f"🛡️ Layer 5: Risk & Position Sizing [{l5_cnt}]",
        ]
    )

    # --- TAB 0: Layer 0 (Universe Pre-Filter Pills + Universe Result Table) ---
    with tab_l0:
        snap_l0 = copy.deepcopy(st.session_state["layer0_cfg"])
        render_layer0_pills(st.session_state["layer0_cfg"])
        if st.session_state["layer0_cfg"] != snap_l0:
            result = _execute_pipeline(df_universe, sp500_bm)
        st.markdown("---")
        render_layer0_tab_results(result.df_scored, result.summary_meta, sp500_bm)

    # --- TAB 1: Layer 1 (11-Rule Trend Pills + Bottleneck Strip + Layer 1 Result Table) ---
    with tab_l1:
        snap_l1 = copy.deepcopy(st.session_state["layer1_cfg"])
        render_layer1_pills(st.session_state["layer1_cfg"], sp500_bm)
        if st.session_state["layer1_cfg"] != snap_l1:
            result = _execute_pipeline(df_universe, sp500_bm)
        render_bottleneck_strip(result.summary_meta)
        st.markdown("---")
        render_layer1_tab_results(result.df_scored, result.summary_meta, sp500_bm)

    # --- TAB 2: Layer 2 (Industry & CAN SLIM Fundamental Pills + Layer 2 Result Table) ---
    with tab_l2:
        snap_l2 = copy.deepcopy(st.session_state["layer2_cfg"])
        render_layer2_pills(st.session_state["layer2_cfg"], result.l2_meta)
        if st.session_state["layer2_cfg"] != snap_l2:
            result = _execute_pipeline(df_universe, sp500_bm)
        st.markdown("---")
        render_layer2_tab_results(result.df_scored, result.summary_meta, sp500_bm)

    # --- TAB 3: Layer 3 (VCP & EMA Structure Pills + VCP Result Table + Grouped TradingView Chart Cockpit) ---
    with tab_l3:
        snap_l3 = copy.deepcopy(st.session_state["layer3_cfg"])
        render_layer3_pills(st.session_state["layer3_cfg"], result.l3_meta)
        if st.session_state["layer3_cfg"] != snap_l3:
            result = _execute_pipeline(df_universe, sp500_bm)
        st.markdown("---")
        render_layer3_tab_results_with_chart(result.df_scored, result.summary_meta, sp500_bm)

    # --- TAB 4: Layer 4 (Actionable Breakout Entry Trigger Pills + Layer 4 Result Table) ---
    with tab_l4:
        snap_l4 = copy.deepcopy(st.session_state["layer4_cfg"])
        render_layer4_pills(st.session_state["layer4_cfg"], result.l4_meta)
        if st.session_state["layer4_cfg"] != snap_l4:
            result = _execute_pipeline(df_universe, sp500_bm)
        st.markdown("---")
        render_layer4_tab_results(result.df_scored, result.summary_meta, sp500_bm)

    # --- TAB 5: Layer 5 (Risk Management & Position Sizing Pills + Layer 5 Order Sheet Result Table) ---
    with tab_l5:
        snap_l5 = copy.deepcopy(st.session_state["layer5_cfg"])
        render_layer5_pills(st.session_state["layer5_cfg"], result.l5_meta)
        if st.session_state["layer5_cfg"] != snap_l5:
            result = _execute_pipeline(df_universe, sp500_bm)
        st.markdown("---")
        render_layer5_tab_results(result.df_scored, result.summary_meta, sp500_bm)


if __name__ == "__main__":
    main()
