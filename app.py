"""
Step 5 (TradingView Top-Pill Architecture + Supabase Cloud DB): Interactive Streamlit Web Dashboard (app.py)
US Short/Mid-Term Breakout Stock Scoring & Ranking System — Layer 0 + Layer 1
Features:
- Zero Left Sidebar! 100% of filtering criteria placed at the TOP of the page as interactive TradingView-style filter pills (`st.popover`)
- Row 1: Preset Dropdown + Action Buttons (Save Preset, Log Run, Refresh Data)
- Row 2 (Layer 0 Pills): US Market/Exchanges | Price >= $10 | Mkt Cap >= $3B | Vol 1D > 500K | Avg Vol 10D/30D/60D/90D > 500K | Price × Vol > $50M
- Row 3 (Layer 1 Pills): C1..C8 Minervini Trend Template Pills | C9 SMA10 >= SMA20 | C10 1M Perf > Y% | C11 6M Perf > Y%
- Full-width Watchlist Table + Click-a-Row Docked Stock Cockpit Drawer (1Y Daily Price + 5 Moving Averages Chart & 11-Condition Scorecard)
"""

from __future__ import annotations

import time
from typing import Dict, Any, Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

from src.config import (
    ALL_EXCHANGES,
    BUILTIN_PRESETS,
    get_default_layer0_config,
    get_default_layer1_config,
    compute_dynamic_sp500_threshold,
)
from src.data_pipeline import (
    load_cached_market_data,
    refresh_daily_market_data,
)
from src.screener_engine import (
    apply_layer0_filter,
    evaluate_layer1_conditions,
    build_stock_condition_breakdown,
)
from src.storage import (
    load_all_presets,
    save_custom_preset,
    load_run_history,
    log_screening_run,
)
from src.supabase_client import is_supabase_configured

st.set_page_config(
    page_title="US Stock Screener — TradingView Pill Layout",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Custom CSS to hide the left sidebar completely and style the top filter pills like TradingView
st.markdown(
    """
    <style>
    /* Hide left sidebar and its toggle arrow completely */
    [data-testid="stSidebar"], [data-testid="collapsedControl"] {
        display: none !important;
    }
    .block-container {
        padding-top: 1.0rem !important;
        padding-bottom: 2.0rem !important;
        max-width: 98% !important;
    }
    /* Style st.popover buttons to look like TradingView Filter Pills */
    div[data-testid="stPopover"] > div > button {
        border-radius: 8px !important;
        padding: 0.25rem 0.65rem !important;
        min-height: 2.2rem !important;
        font-size: 0.82rem !important;
        font-weight: 600 !important;
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
        margin: 4px 0 10px 0;
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


def _fmt_vol(val: int | float) -> str:
    v = float(val)
    if v >= 1_000_000:
        return f"{v / 1_000_000:.1f}M".replace(".0M", "M")
    if v >= 1_000:
        return f"{v / 1_000:.0f}K"
    return str(int(v))


def _init_session_state() -> None:
    if "layer0_cfg" not in st.session_state:
        st.session_state["layer0_cfg"] = get_default_layer0_config()
    if "layer1_cfg" not in st.session_state:
        st.session_state["layer1_cfg"] = get_default_layer1_config()
    if "active_preset_name" not in st.session_state:
        st.session_state["active_preset_name"] = list(BUILTIN_PRESETS.keys())[0]
    if "inspected_ticker" not in st.session_state:
        st.session_state["inspected_ticker"] = None


def _apply_preset_to_state(preset_name: str, presets: Dict[str, Dict[str, Any]]) -> None:
    if preset_name in presets:
        p = presets[preset_name]
        l0 = {**get_default_layer0_config(), **p.get("layer0", {})}
        l1 = {**get_default_layer1_config(), **p.get("layer1", {})}
        st.session_state["layer0_cfg"] = l0
        st.session_state["layer1_cfg"] = l1
        st.session_state["active_preset_name"] = preset_name


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_stock_1y_chart_data(ticker: str) -> Optional[pd.DataFrame]:
    """Fetches 1 year of daily OHLCV via yfinance for the interactive Stock Cockpit chart."""
    try:
        yf_sym = ticker.replace(".", "-")
        hist = yf.Ticker(yf_sym).history(period="18mo", interval="1d", auto_adjust=True)
        if hist is None or hist.empty:
            return None
        hist = hist.dropna(subset=["Close"]).copy()
        hist["SMA10"] = hist["Close"].rolling(10).mean()
        hist["SMA20"] = hist["Close"].rolling(20).mean()
        hist["SMA50"] = hist["Close"].rolling(50).mean()
        hist["SMA150"] = hist["Close"].rolling(150).mean()
        hist["SMA200"] = hist["Close"].rolling(200).mean()
        return hist.tail(252)
    except Exception:
        return None


def _build_stock_plotly_chart(ticker: str, company_name: str, row: pd.Series) -> go.Figure:
    """Builds an interactive 1-Year Candlestick/Line + 5 Moving Averages (10/20/50/150/200) chart."""
    hist = _fetch_stock_1y_chart_data(ticker)
    fig = go.Figure()

    if hist is not None and not hist.empty:
        fig.add_trace(
            go.Candlestick(
                x=hist.index,
                open=hist["Open"],
                high=hist["High"],
                low=hist["Low"],
                close=hist["Close"],
                name="Price",
                increasing_line_color="#10b981",
                decreasing_line_color="#ef4444",
            )
        )
        ma_specs = [
            ("SMA10", "#38bdf8", "dot", 1.3),
            ("SMA20", "#a855f7", "dot", 1.3),
            ("SMA50", "#f59e0b", "solid", 2.0),
            ("SMA150", "#3b82f6", "solid", 2.0),
            ("SMA200", "#ec4899", "solid", 2.4),
        ]
        for col, color, dash, width in ma_specs:
            if col in hist.columns:
                fig.add_trace(
                    go.Scatter(
                        x=hist.index,
                        y=hist[col],
                        mode="lines",
                        name=col,
                        line=dict(color=color, width=width, dash=dash),
                    )
                )
    else:
        levels = ["52W Low", "SMA 200", "SMA 150", "SMA 50", "SMA 20", "SMA 10", "Current Close", "52W High"]
        vals = [
            row.get("low_52w", 0),
            row.get("sma_200", 0),
            row.get("sma_150", 0),
            row.get("sma_50", 0),
            row.get("sma_20", 0),
            row.get("sma_10", 0),
            row.get("close", 0),
            row.get("high_52w", 0),
        ]
        fig.add_trace(go.Bar(x=levels, y=vals, marker_color="#3b82f6"))

    fig.update_layout(
        title=f"{ticker} — {company_name} (1Y Daily Structure & SMA 10/20/50/150/200)",
        height=420,
        margin=dict(l=10, r=10, t=40, b=10),
        xaxis_rangeslider_visible=False,
        template="plotly_dark",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


def main() -> None:
    _init_session_state()

    # 1. Check Session RAM first -> 2. Check Supabase Cloud DB -> 3. Live Fetch once into Session RAM
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

    presets = load_all_presets()
    preset_names = list(presets.keys())
    l0 = st.session_state["layer0_cfg"]
    l1 = st.session_state["layer1_cfg"]
    sp_1m = float(sp500_bm.get("perf_1m_pct", 0.0))
    sp_6m = float(sp500_bm.get("perf_6m_pct", 0.0))

    # =========================================================================
    # TOP BAR ROW 1: TradingView-Style Title / Preset Dropdown + Actions
    # =========================================================================
    top_c1, top_c2, top_c3, top_c4, top_c5 = st.columns([2.8, 2.2, 1.1, 1.1, 1.2])
    with top_c1:
        db_badge = "🟢 Supabase DB" if is_supabase_configured() else "🟡 Session RAM"
        st.markdown(f"### 📈 Stock Screener · <small>`{sp500_bm.get('as_of_date', 'EOD')}` ({db_badge})</small>", unsafe_allow_html=True)
    with top_c2:
        def _on_preset_change() -> None:
            chosen = st.session_state["preset_selector_widget"]
            _apply_preset_to_state(chosen, presets)

        st.selectbox(
            "Preset Template",
            options=preset_names,
            index=preset_names.index(st.session_state["active_preset_name"])
            if st.session_state["active_preset_name"] in preset_names
            else 0,
            key="preset_selector_widget",
            on_change=_on_preset_change,
            label_visibility="collapsed",
        )
    with top_c3:
        with st.popover("💾 Save Preset", use_container_width=True):
            st.markdown("**Save Current Filter Pill Setup**")
            new_preset_name = st.text_input("Preset Name", placeholder="e.g. Above 200MA + 1+6M Per")
            if st.button("Save Preset Now", use_container_width=True, type="primary") and new_preset_name.strip():
                save_custom_preset(new_preset_name.strip(), "Custom user preset", l0, l1)
                st.session_state["active_preset_name"] = new_preset_name.strip()
                st.toast(f"Saved preset: {new_preset_name.strip()}", icon="💾")
                st.rerun()
    with top_c4:
        log_clicked = st.button("📝 Log Run", use_container_width=True)
    with top_c5:
        if st.button("🔄 Refresh Data", use_container_width=True):
            prog = st.progress(0, text="Refreshing live market data...")
            df_universe, sp500_bm = refresh_daily_market_data(
                enrich_yf=True,
                max_symbols_for_yf=800,
                progress_callback=lambda p, msg: prog.progress(int(p * 100), text=msg),
            )
            st.session_state["cached_df_universe"] = df_universe
            st.session_state["cached_sp500_bm"] = sp500_bm
            prog.empty()
            st.rerun()

    # =========================================================================
    # TOP FILTER PILLS — ROW 1: LAYER 0 UNIVERSE PRE-FILTER (TradingView Style)
    # =========================================================================
    r1_c1, r1_c2, r1_c3, r1_c4, r1_c5, r1_c6, r1_c7, r1_c8, r1_c9 = st.columns(
        [1.15, 1.15, 1.25, 1.1, 1.25, 1.25, 1.25, 1.25, 1.35]
    )

    with r1_c1:
        ex_count = len(l0.get("exchanges", ALL_EXCHANGES))
        ex_label = "🇺🇸 US" if ex_count == 3 else f"🇺🇸 US ({ex_count})"
        with st.popover(ex_label, use_container_width=True):
            st.markdown("**Market & Security Type**")
            l0["exchanges"] = st.multiselect(
                "US Exchanges",
                options=ALL_EXCHANGES,
                default=l0.get("exchanges", ALL_EXCHANGES),
            )
            l0["exclude_etfs"] = st.toggle("Exclude ETFs / Funds", value=bool(l0.get("exclude_etfs", True)))
            l0["include_adrs"] = st.toggle("Include Foreign ADRs", value=bool(l0.get("include_adrs", True)))

    with r1_c2:
        with st.popover(f"Price ≥ {l0['min_price']:.0f} USD", use_container_width=True):
            l0["min_price"] = st.number_input(
                "Minimum Share Price (USD)",
                min_value=1.0,
                max_value=1000.0,
                value=float(l0.get("min_price", 10.0)),
                step=1.0,
            )

    with r1_c3:
        mc_label = (
            f"Mkt cap ≥ {l0['min_market_cap_b']:g} B USD"
            if float(l0.get("max_market_cap_b", 0.0)) <= 0
            else f"Mkt cap {l0['min_market_cap_b']:g}–{l0['max_market_cap_b']:g}B"
        )
        with st.popover(mc_label, use_container_width=True):
            l0["min_market_cap_b"] = st.number_input(
                "Min Market Cap ($ Billions)",
                min_value=0.1,
                max_value=500.0,
                value=float(l0.get("min_market_cap_b", 3.0)),
                step=0.5,
            )
            l0["max_market_cap_b"] = st.number_input(
                "Max Market Cap ($B, 0 = No Limit)",
                min_value=0.0,
                max_value=5000.0,
                value=float(l0.get("max_market_cap_b", 0.0)),
                step=5.0,
            )

    with r1_c4:
        with st.popover(f"Vol > {_fmt_vol(l0['min_vol_1d'])}", use_container_width=True):
            l0["min_vol_1d"] = st.number_input(
                "Current Day Volume (1D Shares)",
                min_value=0,
                max_value=50_000_000,
                value=int(l0.get("min_vol_1d", 500_000)),
                step=50_000,
            )
            if st.button("Apply this volume to 10D/30D/60D/90D", use_container_width=True):
                v = int(l0["min_vol_1d"])
                l0["min_vol_10d"] = l0["min_vol_30d"] = l0["min_vol_60d"] = l0["min_vol_90d"] = v
                st.rerun()

    with r1_c5:
        with st.popover(f"Avg vol, 10D > {_fmt_vol(l0['min_vol_10d'])}", use_container_width=True):
            l0["min_vol_10d"] = st.number_input(
                "10-Day Average Volume (Shares)",
                min_value=0,
                max_value=50_000_000,
                value=int(l0.get("min_vol_10d", 500_000)),
                step=50_000,
            )

    with r1_c6:
        with st.popover(f"Avg vol, 30D > {_fmt_vol(l0['min_vol_30d'])}", use_container_width=True):
            l0["min_vol_30d"] = st.number_input(
                "30-Day Average Volume (Shares)",
                min_value=0,
                max_value=50_000_000,
                value=int(l0.get("min_vol_30d", 500_000)),
                step=50_000,
            )

    with r1_c7:
        with st.popover(f"Avg vol, 60D > {_fmt_vol(l0['min_vol_60d'])}", use_container_width=True):
            l0["min_vol_60d"] = st.number_input(
                "60-Day Average Volume (Shares)",
                min_value=0,
                max_value=50_000_000,
                value=int(l0.get("min_vol_60d", 500_000)),
                step=50_000,
            )

    with r1_c8:
        with st.popover(f"Avg vol, 90D > {_fmt_vol(l0['min_vol_90d'])}", use_container_width=True):
            l0["min_vol_90d"] = st.number_input(
                "90-Day Average Volume (Shares)",
                min_value=0,
                max_value=50_000_000,
                value=int(l0.get("min_vol_90d", 500_000)),
                step=50_000,
            )

    with r1_c9:
        with st.popover(f"Price × vol > {l0['min_dollar_vol_m']:g} M USD", use_container_width=True):
            l0["min_dollar_vol_m"] = st.number_input(
                "Min Daily Dollar Volume ($ Millions)",
                min_value=0.0,
                max_value=1000.0,
                value=float(l0.get("min_dollar_vol_m", 50.0)),
                step=5.0,
            )

    # =========================================================================
    # TOP FILTER PILLS — ROW 2: LAYER 1 TREND & MOMENTUM PILLS (11 Conditions)
    # =========================================================================
    y_1m_preview = compute_dynamic_sp500_threshold(
        sp_1m,
        bool(l1.get("c10_use_dynamic_sp500", True)),
        float(l1.get("c10_pos_multiplier", 2.0)),
        float(l1.get("c10_neg_multiplier", 0.5)),
        float(l1.get("c10_manual_min_pct", 7.0)),
    )
    y_6m_preview = compute_dynamic_sp500_threshold(
        sp_6m,
        bool(l1.get("c11_use_dynamic_sp500", True)),
        float(l1.get("c11_pos_multiplier", 2.0)),
        float(l1.get("c11_neg_multiplier", 0.5)),
        float(l1.get("c11_manual_min_pct", 24.0)),
    )

    r2_c1, r2_c2, r2_c3, r2_c4, r2_c5, r2_c6, r2_c7, r2_c8 = st.columns(
        [1.35, 1.35, 1.25, 1.3, 1.35, 1.35, 1.2, 1.45]
    )

    with r2_c1:
        p_c1 = "✅ SMA 150/200 < Price" if l1["c1_enabled"] else "⚪ SMA 150/200 < Price"
        with st.popover(p_c1, use_container_width=True):
            l1["c1_enabled"] = st.toggle("Enable C1: Price > SMA 150 & SMA 200", value=bool(l1.get("c1_enabled", True)))
            st.markdown("---")
            l1["c2_enabled"] = st.toggle("Enable C2: SMA 150 > SMA 200", value=bool(l1.get("c2_enabled", True)))
            l1["c4_enabled"] = st.toggle("Enable C4: SMA 50 > SMA 150 > SMA 200", value=bool(l1.get("c4_enabled", True)))
            l1["c5_enabled"] = st.toggle("Enable C5: Price > SMA 50", value=bool(l1.get("c5_enabled", True)))

    with r2_c2:
        p_c3 = f"✅ SMA 200 ↑ ({l1['c3_lookback_days']}D)" if l1["c3_enabled"] else "⚪ SMA 200 ↑ (OFF)"
        with st.popover(p_c3, use_container_width=True):
            l1["c3_enabled"] = st.toggle("Enable C3: SMA 200 Trending Upward", value=bool(l1.get("c3_enabled", True)))
            l1["c3_lookback_days"] = st.select_slider(
                "Lookback Trading Days (N)",
                options=[5, 10, 15, 20, 30, 40, 60],
                value=int(l1.get("c3_lookback_days", 20))
                if int(l1.get("c3_lookback_days", 20)) in [5, 10, 15, 20, 30, 40, 60]
                else 20,
            )

    with r2_c3:
        p_c9 = "✅ SMA, 10 ≥ SMA, 20" if l1["c9_enabled"] else "⚪ SMA, 10 ≥ SMA, 20"
        with st.popover(p_c9, use_container_width=True):
            l1["c9_enabled"] = st.toggle("Enable C9: Short-Term Swing Alignment (SMA 10 ≥ SMA 20)", value=bool(l1.get("c9_enabled", True)))

    with r2_c4:
        p_c10 = f"✅ Perf, 1M > {y_1m_preview:+.1f}%" if l1["c10_enabled"] else "⚪ Perf, 1M (OFF)"
        with st.popover(p_c10, use_container_width=True):
            l1["c10_enabled"] = st.toggle("Enable C10: 1-Month Performance Filter", value=bool(l1.get("c10_enabled", True)))
            l1["c10_use_dynamic_sp500"] = st.toggle(
                f"Dynamic vs S&P 500 1M ({sp_1m:+.2f}%)",
                value=bool(l1.get("c10_use_dynamic_sp500", True)),
                help="2.0x S&P 500 when positive; 0.5x when negative.",
            )
            if not l1["c10_use_dynamic_sp500"]:
                l1["c10_manual_min_pct"] = st.number_input(
                    "Manual Min 1M Perf (%)",
                    value=float(l1.get("c10_manual_min_pct", 7.0)),
                    step=1.0,
                )

    with r2_c5:
        p_c11 = f"✅ Perf, 6M > {y_6m_preview:+.1f}%" if l1["c11_enabled"] else "⚪ Perf, 6M (OFF)"
        with st.popover(p_c11, use_container_width=True):
            l1["c11_enabled"] = st.toggle("Enable C11: 6-Month Performance Filter", value=bool(l1.get("c11_enabled", True)))
            l1["c11_use_dynamic_sp500"] = st.toggle(
                f"Dynamic vs S&P 500 6M ({sp_6m:+.2f}%)",
                value=bool(l1.get("c11_use_dynamic_sp500", True)),
                help="2.0x S&P 500 when positive; 0.5x when negative.",
            )
            if not l1["c11_use_dynamic_sp500"]:
                l1["c11_manual_min_pct"] = st.number_input(
                    "Manual Min 6M Perf (%)",
                    value=float(l1.get("c11_manual_min_pct", 24.0)),
                    step=2.0,
                )

    with r2_c6:
        p_c6 = f"✅ 52W Low +{l1['c6_min_pct_above_52w_low']:g}%" if l1["c6_enabled"] else "⚪ 52W Low (OFF)"
        with st.popover(p_c6, use_container_width=True):
            l1["c6_enabled"] = st.toggle("Enable C6: Price Cleared 52-Week Low", value=bool(l1.get("c6_enabled", True)))
            l1["c6_min_pct_above_52w_low"] = st.number_input(
                "Min % Above 52-Week Low",
                min_value=0.0,
                max_value=300.0,
                value=float(l1.get("c6_min_pct_above_52w_low", 30.0)),
                step=5.0,
            )

    with r2_c7:
        p_c7 = f"✅ 52W High -{l1['c7_max_pct_below_52w_high']:g}%" if l1["c7_enabled"] else "⚪ 52W High (OFF)"
        with st.popover(p_c7, use_container_width=True):
            l1["c7_enabled"] = st.toggle("Enable C7: Price Near 52-Week High", value=bool(l1.get("c7_enabled", True)))
            l1["c7_max_pct_below_52w_high"] = st.number_input(
                "Max % Below 52-Week High",
                min_value=1.0,
                max_value=80.0,
                value=float(l1.get("c7_max_pct_below_52w_high", 25.0)),
                step=5.0,
            )

    with r2_c8:
        p_c8 = f"✅ RS Rating ≥ {l1['c8_min_rs_percentile']}" if l1["c8_enabled"] else "⚪ RS Rating (OFF)"
        with st.popover(p_c8, use_container_width=True):
            l1["c8_enabled"] = st.toggle("Enable C8: Relative Strength Percentile", value=bool(l1.get("c8_enabled", True)))
            l1["c8_min_rs_percentile"] = st.slider(
                "Minimum RS Percentile (1-99)",
                min_value=1,
                max_value=99,
                value=int(l1.get("c8_min_rs_percentile", 70)),
            )

    # =========================================================================
    # EXECUTE INSTANT SCREENING (<1 SECOND)
    # =========================================================================
    t_start = time.perf_counter()
    df_l0 = apply_layer0_filter(df_universe, st.session_state["layer0_cfg"])
    df_scored, summary_meta = evaluate_layer1_conditions(
        df_l0, st.session_state["layer1_cfg"], sp500_bm
    )
    elapsed_ms = (time.perf_counter() - t_start) * 1000.0

    if log_clicked:
        q_tickers = (
            df_scored[df_scored["qualified_all"]]["ticker"].tolist()
            if not df_scored.empty
            else []
        )
        log_screening_run(
            preset_name=st.session_state["active_preset_name"],
            layer0_cfg=st.session_state["layer0_cfg"],
            layer1_cfg=st.session_state["layer1_cfg"],
            summary_meta=summary_meta,
            qualifying_tickers=q_tickers,
            elapsed_ms=elapsed_ms,
        )
        st.toast("Screening run logged to Run History!", icon="✅")

    # =========================================================================
    # COMPACT BOTTLENECK DETECTOR & FUNNEL SUMMARY STRIP
    # =========================================================================
    l0_cnt = summary_meta["layer0_count"]
    qual_cnt = summary_meta["qualified_count"]
    near_cnt = summary_meta["near_miss_count"]
    active_cnt = summary_meta["active_condition_count"]

    if summary_meta.get("condition_bottlenecks"):
        chips_html = []
        for b in summary_meta["condition_bottlenecks"]:
            if not b["enabled"]:
                cls = "bn-chip bn-off"
                txt = f"{b['short_label']}: OFF"
            else:
                pct = b["pass_pct"]
                cls = "bn-chip bn-tight" if pct < 45 else ("bn-chip bn-mid" if pct < 70 else "bn-chip bn-open")
                txt = f"{b['short_label']}: {b['pass_count']} ({pct:.0f}%)"
            chips_html.append(f'<span class="{cls}" title="{b["name"]}">{txt}</span>')
        st.markdown(
            f'<div class="bottleneck-bar">'
            f'<span class="bn-chip" style="background:rgba(56,189,248,0.15);color:#38bdf8;"><b>Layer 0 Pool:</b> {l0_cnt:,}</span>'
            f'<span class="bn-chip" style="background:rgba(16,185,129,0.2);color:#34d399;"><b>Qualified ({active_cnt}/{active_cnt}):</b> {qual_cnt:,}</span>'
            f'<span class="bn-chip" style="background:rgba(245,158,11,0.18);color:#fbbf24;"><b>Near-Miss ({max(0, active_cnt - 1)}/{active_cnt}):</b> {near_cnt:,}</span>'
            f'{"".join(chips_html)}</div>',
            unsafe_allow_html=True,
        )

    # =========================================================================
    # WORKSPACE TABS: Overview Watchlist vs. Historical Run Logs
    # =========================================================================
    tab_cockpit, tab_history = st.tabs(
        [
            f"📊 Overview ({qual_cnt} Qualified · {near_cnt} Near-Misses · {l0_cnt} Layer 0 Pool)",
            "📜 Historical Screening Run Logs",
        ]
    )

    with tab_cockpit:
        if df_scored.empty:
            st.warning("No stocks passed your current Layer 0 Pre-Filter pills above. Click any top filter pill (e.g. Mkt cap or Vol) to loosen the threshold.")
        else:
            # One-Click Quick Filter Toolbar + Sector Leadership
            tb1, tb2, tb3, tb4 = st.columns([2.6, 1.5, 1.3, 0.8])
            with tb1:
                view_mode = st.radio(
                    "Watchlist View Mode",
                    options=[
                        f"🏆 Qualified ({active_cnt}/{active_cnt}) [{qual_cnt}]",
                        f"🎯 Near-Miss ({max(0, active_cnt - 1)}/{active_cnt}) [{near_cnt}]",
                        f"👀 Broad ({max(0, active_cnt - 2)}+) ",
                        f"🌐 Full Layer 0 [{l0_cnt}]",
                    ],
                    horizontal=True,
                    label_visibility="collapsed",
                )
            with tb2:
                all_sectors = sorted(df_scored["sector"].dropna().unique().tolist())
                selected_sectors = st.multiselect(
                    "Filter by Sector",
                    options=all_sectors,
                    placeholder="All Sectors...",
                    label_visibility="collapsed",
                )
            with tb3:
                search_query = st.text_input(
                    "Search Ticker / Company",
                    placeholder="🔍 Symbol / Company (e.g. LLY, NVDA)...",
                    label_visibility="collapsed",
                )

            if view_mode.startswith("🏆"):
                df_view = df_scored[df_scored["qualified_all"]].copy()
            elif view_mode.startswith("🎯"):
                df_view = df_scored[df_scored["passed_count"] == max(0, active_cnt - 1)].copy()
            elif view_mode.startswith("👀"):
                df_view = df_scored[df_scored["passed_count"] >= max(0, active_cnt - 2)].copy()
            else:
                df_view = df_scored.copy()

            if selected_sectors:
                df_view = df_view[df_view["sector"].isin(selected_sectors)]

            if search_query.strip():
                q = search_query.strip().lower()
                df_view = df_view[
                    df_view["ticker"].str.lower().str.contains(q)
                    | df_view["company_name"].fillna("").str.lower().str.contains(q)
                ]

            df_view = df_view.reset_index(drop=True)
            df_view["tv_url"] = (
                "https://www.tradingview.com/chart/?symbol="
                + df_view["exchange"].astype(str)
                + "%3A"
                + df_view["ticker"].astype(str)
            )

            with tb4:
                csv_bytes = df_view.to_csv(index=False).encode("utf-8")
                st.download_button(
                    label=f"⬇️ CSV ({len(df_view)})",
                    data=csv_bytes,
                    file_name=f"watchlist_{sp500_bm.get('as_of_date', 'eod')}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

            # =================================================================
            # 100% FULL-WIDTH HIGH-DENSITY WATCHLIST TABLE (TradingView Style)
            # =================================================================
            display_cols = [
                "ticker",
                "company_name",
                "close",
                "vol_1d",
                "market_cap_b",
                "rs_percentile",
                "perf_1m",
                "perf_6m",
                "pct_of_52w_high",
                "dollar_vol_m",
                "sector",
                "pass_summary",
                "diagnostic_badge",
                "tv_url",
            ]

            selection_event = st.dataframe(
                df_view[display_cols],
                use_container_width=True,
                height=470,
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row",
                column_config={
                    "ticker": st.column_config.TextColumn(f"Symbol ({len(df_view)})", width="small"),
                    "company_name": st.column_config.TextColumn("Company", width="medium"),
                    "close": st.column_config.NumberColumn("Price", format="$%.2f"),
                    "vol_1d": st.column_config.NumberColumn("Vol", format="%d"),
                    "market_cap_b": st.column_config.NumberColumn("Mkt cap", format="$%.2fB"),
                    "rs_percentile": st.column_config.ProgressColumn(
                        "RS Rank",
                        format="%d",
                        min_value=1,
                        max_value=99,
                    ),
                    "perf_1m": st.column_config.NumberColumn("Perf 1M", format="%+.2f%%"),
                    "perf_6m": st.column_config.NumberColumn("Perf 6M", format="%+.2f%%"),
                    "pct_of_52w_high": st.column_config.ProgressColumn(
                        "% of 52W High",
                        format="%.1f%%",
                        min_value=0,
                        max_value=100,
                    ),
                    "dollar_vol_m": st.column_config.NumberColumn("Price×Vol", format="$%.0fM"),
                    "sector": st.column_config.TextColumn("Sector", width="medium"),
                    "pass_summary": st.column_config.TextColumn("Score", width="small"),
                    "diagnostic_badge": st.column_config.TextColumn("Status / Missed Rules", width="medium"),
                    "tv_url": st.column_config.LinkColumn("Chart", display_text="TradingView ↗"),
                },
            )

            # =================================================================
            # DOCKED STOCK COCKPIT DRAWER (Below Full-Width Table)
            # =================================================================
            st.divider()
            if not df_view.empty:
                selected_rows = (
                    selection_event.selection.rows
                    if selection_event and hasattr(selection_event, "selection")
                    else []
                )
                if selected_rows and selected_rows[0] < len(df_view):
                    inspected_row = df_view.iloc[selected_rows[0]]
                else:
                    inspected_row = df_view.iloc[0]

                sel_ticker = str(inspected_row["ticker"])
                sel_name = str(inspected_row.get("company_name", ""))
                sel_exch = str(inspected_row.get("exchange", "NASDAQ"))
                tv_link = f"https://www.tradingview.com/chart/?symbol={sel_exch}%3A{sel_ticker}"

                dr_hdr1, dr_hdr2 = st.columns([3.5, 1.5])
                with dr_hdr1:
                    st.markdown(
                        f"### 🔍 Stock Cockpit Inspector: **{sel_ticker}** — {sel_name} "
                        f"(`{inspected_row['pass_summary']}` · `{inspected_row['diagnostic_badge']}`)"
                    )
                with dr_hdr2:
                    st.link_button(
                        f"📈 Open {sel_ticker} Full Chart in TradingView ↗",
                        url=tv_link,
                        use_container_width=True,
                    )

                cockpit_left, cockpit_right = st.columns([1.25, 1.0])
                with cockpit_left:
                    fig = _build_stock_plotly_chart(sel_ticker, sel_name, inspected_row)
                    st.plotly_chart(fig, use_container_width=True)

                with cockpit_right:
                    breakdown = build_stock_condition_breakdown(
                        inspected_row, st.session_state["layer1_cfg"], summary_meta
                    )
                    df_bd = pd.DataFrame(breakdown)
                    df_bd["Result"] = df_bd.apply(
                        lambda r: "⚪ OFF"
                        if not r["Enabled"]
                        else ("✅ PASS" if r["Passed"] else "❌ FAIL"),
                        axis=1,
                    )
                    st.dataframe(
                        df_bd[["Condition", "Result", "Stock Value", "Required Threshold"]],
                        use_container_width=True,
                        hide_index=True,
                        height=405,
                    )

    with tab_history:
        st.subheader("📜 Past Screening Run Logs & Market Breadth History")
        history = load_run_history()
        if not history:
            st.info("No screening runs logged yet. Click **'📝 Log Run'** at the top right to record daily snapshots.")
        else:
            df_hist = pd.DataFrame(history)
            df_hist["Top Qualifying Tickers"] = df_hist["top_tickers"].apply(
                lambda lst: ", ".join(lst[:12]) + ("..." if len(lst) > 12 else "")
                if isinstance(lst, list)
                else ""
            )
            st.dataframe(
                df_hist[
                    [
                        "timestamp_utc",
                        "preset_name",
                        "min_market_cap_b",
                        "layer0_candidates",
                        "layer1_qualified",
                        "active_conditions",
                        "sp500_1m_pct",
                        "y_1m_threshold_pct",
                        "sp500_6m_pct",
                        "y_6m_threshold_pct",
                        "Top Qualifying Tickers",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
            )


if __name__ == "__main__":
    main()
