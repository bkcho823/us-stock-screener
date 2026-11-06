"""
US Stock Momentum Screener — Thin Application Orchestrator (`app.py`)
Architecture: Clean 4-Tier Modular Design + Pluggable Multi-Layer Pipeline
  1. Presentation Tier (`src/ui/`): Theme, Session State, Top Header, Filter Pills, Bottleneck Strip, Watchlist Grid, TradingView Cockpit
  2. Domain / Screening Pipeline Tier (`src/layers/`): Layer 0 (Universe) -> Layer 1 (Trend) -> Layer 2 (Industry Momentum) -> Layer 3 (VCP & EMA)
  3. External Market Data Providers (`src/providers/`): TradingView Scanner + Yahoo Finance + EOD Sync Service
  4. Infrastructure & Config (`src/infrastructure/`, `src/config/`): Supabase PostgREST Repositories & Built-In Presets
"""

from __future__ import annotations

import os
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
    render_watchlist_grid,
    render_tradingview_cockpit,
)
from src.ui.pills import (
    render_layer0_pills,
    render_layer1_pills,
    render_layer2_pills,
    render_layer3_pills,
)


def main() -> None:
    # 1. Configure page theme & initialize session state
    apply_custom_theme()
    init_session_state()

    # 2. Load market snapshot & S&P 500 benchmark (Session RAM -> Supabase DB -> Live Fetch)
    df_universe, sp500_bm = ensure_market_data_loaded()

    # 3. Render Top Bar & All Layer 0 + Layer 1 Filter Pills
    render_top_header(sp500_bm)
    render_layer0_pills(st.session_state["layer0_cfg"])
    render_layer1_pills(st.session_state["layer1_cfg"], sp500_bm)

    # 4. Run Pluggable Multi-Layer Screening Pipeline (Layers 0 -> 1 -> 2 -> 3 in <1s)
    result = run_screening_pipeline(
        df_universe=df_universe,
        sp500_bm=sp500_bm,
        layer0_cfg=st.session_state["layer0_cfg"],
        layer1_cfg=st.session_state["layer1_cfg"],
        layer2_cfg=st.session_state.get("layer2_cfg"),
        layer3_cfg=st.session_state.get("layer3_cfg"),
    )

    # 5. Render Layer 2 Industry Pills & Layer 3 VCP / EMA Structure Pills
    render_layer2_pills(st.session_state["layer2_cfg"], result.l2_meta)
    render_layer3_pills(st.session_state["layer3_cfg"], result.l3_meta)

    # 6. Render Bottleneck Strip, Highlighted Watchlist Grid, & Live TradingView Chart Cockpit
    render_bottleneck_strip(result.summary_meta)
    df_view = render_watchlist_grid(result.df_scored, result.summary_meta, sp500_bm)
    render_tradingview_cockpit(df_view)


if __name__ == "__main__":
    main()
