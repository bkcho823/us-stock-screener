"""
Step 5 (Chief UI Designer Edition + Supabase Cloud DB): Interactive Streamlit Web Dashboard (app.py)
US Short/Mid-Term Breakout Stock Scoring & Ranking System — Layer 0 + Layer 1
Features:
- Reads/Writes to Supabase Online DB + caches in Streamlit Session RAM so it never loops on rerun
- 100% Full-Width High-Density Watchlist Table with Visual Progress Bars & Plain-English Diagnostic Badges
- Condition Bottleneck Bar (shows pass rate % for C1..C11 across the Layer 0 pool)
- Sector Leadership Breakdown Pills with 1-Click Filtering
- Click-a-Row Docked Stock Cockpit Drawer:
  - Left (55%): Interactive 1-Year Daily Price + 5 Moving Averages (SMA 10/20/50/150/200) Plotly Chart
  - Right (45%): Structured 11-Condition Pass/Fail Scorecard
- Streamlined Sidebar with Instant Preset Switching & Sync-All-Volumes Toggle
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
    page_title="US Stock Momentum Screener — Trading Cockpit",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for high-density financial cockpit layout
st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1.2rem;
        padding-bottom: 2rem;
    }
    .bottleneck-bar {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        margin: 6px 0 12px 0;
    }
    .bn-chip {
        padding: 4px 9px;
        border-radius: 6px;
        font-size: 0.78rem;
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


def _init_session_state() -> None:
    if "layer0_cfg" not in st.session_state:
        st.session_state["layer0_cfg"] = get_default_layer0_config()
    if "layer1_cfg" not in st.session_state:
        st.session_state["layer1_cfg"] = get_default_layer1_config()
    if "active_preset_name" not in st.session_state:
        st.session_state["active_preset_name"] = list(BUILTIN_PRESETS.keys())[0]
    if "sync_volumes" not in st.session_state:
        st.session_state["sync_volumes"] = True
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

    # =========================================================================
    # SIDEBAR: Instant Preset Bar + Streamlined Layer 0 & Layer 1 Controls
    # =========================================================================
    presets = load_all_presets()
    preset_names = list(presets.keys())

    with st.sidebar:
        st.markdown("### ⚡ Strategy Preset")

        def _on_preset_change() -> None:
            chosen = st.session_state["preset_selector_widget"]
            _apply_preset_to_state(chosen, presets)

        st.selectbox(
            "Select Preset (Auto-Applies Instantly)",
            options=preset_names,
            index=preset_names.index(st.session_state["active_preset_name"])
            if st.session_state["active_preset_name"] in preset_names
            else 0,
            key="preset_selector_widget",
            on_change=_on_preset_change,
            label_visibility="collapsed",
        )

        # ---------------------------------------------------------------------
        # LAYER 0 CONTROLS (With Master Volume Sync Toggle)
        # ---------------------------------------------------------------------
        l0 = st.session_state["layer0_cfg"]
        with st.expander("🌐 Layer 0: Universe Pre-Filter", expanded=True):
            col_mc1, col_mc2 = st.columns(2)
            with col_mc1:
                l0["min_market_cap_b"] = st.number_input(
                    "Min Mkt Cap ($B)",
                    min_value=0.1,
                    max_value=500.0,
                    value=float(l0.get("min_market_cap_b", 3.0)),
                    step=0.5,
                    help="Switch between $2B, $3B, $10B etc.",
                )
            with col_mc2:
                l0["max_market_cap_b"] = st.number_input(
                    "Max Cap ($B, 0=All)",
                    min_value=0.0,
                    max_value=5000.0,
                    value=float(l0.get("max_market_cap_b", 0.0)),
                    step=5.0,
                )

            col_p, col_dv = st.columns(2)
            with col_p:
                l0["min_price"] = st.number_input(
                    "Min Price ($)",
                    min_value=1.0,
                    max_value=1000.0,
                    value=float(l0.get("min_price", 10.0)),
                    step=1.0,
                )
            with col_dv:
                l0["min_dollar_vol_m"] = st.number_input(
                    "Min Price×Vol ($M)",
                    min_value=0.0,
                    max_value=1000.0,
                    value=float(l0.get("min_dollar_vol_m", 50.0)),
                    step=5.0,
                )

            st.session_state["sync_volumes"] = st.toggle(
                "Link All 5 Volume Horizons (1D–90D)",
                value=bool(st.session_state.get("sync_volumes", True)),
                help="When ON, one volume box sets 1D, 10D, 30D, 60D, and 90D simultaneously. Turn OFF to set each horizon separately.",
            )
            if st.session_state["sync_volumes"]:
                master_vol = st.number_input(
                    "Min Volume (1D, 10D, 30D, 60D, 90D Shares)",
                    min_value=0,
                    max_value=50_000_000,
                    value=int(l0.get("min_vol_1d", 500_000)),
                    step=50_000,
                )
                l0["min_vol_1d"] = master_vol
                l0["min_vol_10d"] = master_vol
                l0["min_vol_30d"] = master_vol
                l0["min_vol_60d"] = master_vol
                l0["min_vol_90d"] = master_vol
            else:
                v_c1, v_c2 = st.columns(2)
                with v_c1:
                    l0["min_vol_1d"] = st.number_input("1D Vol >", min_value=0, value=int(l0.get("min_vol_1d", 500_000)), step=50_000)
                    l0["min_vol_30d"] = st.number_input("30D Avg Vol >", min_value=0, value=int(l0.get("min_vol_30d", 500_000)), step=50_000)
                    l0["min_vol_90d"] = st.number_input("90D Avg Vol >", min_value=0, value=int(l0.get("min_vol_90d", 500_000)), step=50_000)
                with v_c2:
                    l0["min_vol_10d"] = st.number_input("10D Avg Vol >", min_value=0, value=int(l0.get("min_vol_10d", 500_000)), step=50_000)
                    l0["min_vol_60d"] = st.number_input("60D Avg Vol >", min_value=0, value=int(l0.get("min_vol_60d", 500_000)), step=50_000)

            l0["exchanges"] = st.multiselect(
                "Exchanges",
                options=ALL_EXCHANGES,
                default=l0.get("exchanges", ALL_EXCHANGES),
            )
            tc1, tc2 = st.columns(2)
            with tc1:
                l0["exclude_etfs"] = st.toggle("Exclude ETFs", value=bool(l0.get("exclude_etfs", True)))
            with tc2:
                l0["include_adrs"] = st.toggle("Include ADRs", value=bool(l0.get("include_adrs", True)))

        # ---------------------------------------------------------------------
        # LAYER 1 CONTROLS (Grouped into 3 Logical Trader Sections)
        # ---------------------------------------------------------------------
        l1 = st.session_state["layer1_cfg"]
        with st.expander("🎯 Layer 1: 11 Trend & Momentum Rules", expanded=True):
            st.caption("**Group 1: Moving Average Trend Stack (C1–C5)**")
            l1["c1_enabled"] = st.checkbox("C1: Price > SMA150 & SMA200", value=bool(l1.get("c1_enabled", True)))
            l1["c2_enabled"] = st.checkbox("C2: SMA150 > SMA200", value=bool(l1.get("c2_enabled", True)))
            l1["c3_enabled"] = st.checkbox("C3: SMA200 Trending Up", value=bool(l1.get("c3_enabled", True)))
            if l1["c3_enabled"]:
                l1["c3_lookback_days"] = st.select_slider(
                    "C3 Lookback Trading Days (N)",
                    options=[5, 10, 15, 20, 30, 40, 60],
                    value=int(l1.get("c3_lookback_days", 20))
                    if int(l1.get("c3_lookback_days", 20)) in [5, 10, 15, 20, 30, 40, 60]
                    else 20,
                )
            l1["c4_enabled"] = st.checkbox("C4: SMA50 > SMA150 > SMA200", value=bool(l1.get("c4_enabled", True)))
            l1["c5_enabled"] = st.checkbox("C5: Price > SMA50", value=bool(l1.get("c5_enabled", True)))

            st.markdown("---")
            st.caption("**Group 2: 52-Week Price Zone & RS Rank (C6–C8)**")
            l1["c6_enabled"] = st.checkbox("C6: Price >= 52W Low + X%", value=bool(l1.get("c6_enabled", True)))
            if l1["c6_enabled"]:
                l1["c6_min_pct_above_52w_low"] = st.number_input(
                    "Min % Above 52W Low",
                    min_value=0.0,
                    max_value=300.0,
                    value=float(l1.get("c6_min_pct_above_52w_low", 30.0)),
                    step=5.0,
                )
            l1["c7_enabled"] = st.checkbox("C7: Price Near 52W High (Within Y%)", value=bool(l1.get("c7_enabled", True)))
            if l1["c7_enabled"]:
                l1["c7_max_pct_below_52w_high"] = st.number_input(
                    "Max % Below 52W High",
                    min_value=1.0,
                    max_value=80.0,
                    value=float(l1.get("c7_max_pct_below_52w_high", 25.0)),
                    step=5.0,
                )
            l1["c8_enabled"] = st.checkbox("C8: RS Percentile >= P", value=bool(l1.get("c8_enabled", True)))
            if l1["c8_enabled"]:
                l1["c8_min_rs_percentile"] = st.slider(
                    "Min RS Percentile (1-99)",
                    min_value=1,
                    max_value=99,
                    value=int(l1.get("c8_min_rs_percentile", 70)),
                )

            st.markdown("---")
            st.caption("**Group 3: Swing MA & S&P 500 Outperformance (C9–C11)**")
            l1["c9_enabled"] = st.checkbox("C9: SMA10 >= SMA20", value=bool(l1.get("c9_enabled", True)))

            sp_1m = float(sp500_bm.get("perf_1m_pct", 0.0))
            sp_6m = float(sp500_bm.get("perf_6m_pct", 0.0))

            l1["c10_enabled"] = st.checkbox("C10: 1M Perf > S&P 500 Target", value=bool(l1.get("c10_enabled", True)))
            if l1["c10_enabled"]:
                l1["c10_use_dynamic_sp500"] = st.toggle(
                    f"Auto 1M Target (S&P: {sp_1m:+.2f}%)",
                    value=bool(l1.get("c10_use_dynamic_sp500", True)),
                    help="2.0x S&P return when S&P >= 0%, or 0.5x when S&P < 0%.",
                )
                if not l1["c10_use_dynamic_sp500"]:
                    l1["c10_manual_min_pct"] = st.number_input(
                        "Manual Min 1M Perf (%)",
                        value=float(l1.get("c10_manual_min_pct", 7.0)),
                        step=1.0,
                    )

            l1["c11_enabled"] = st.checkbox("C11: 6M Perf > S&P 500 Target", value=bool(l1.get("c11_enabled", True)))
            if l1["c11_enabled"]:
                l1["c11_use_dynamic_sp500"] = st.toggle(
                    f"Auto 6M Target (S&P: {sp_6m:+.2f}%)",
                    value=bool(l1.get("c11_use_dynamic_sp500", True)),
                    help="2.0x S&P return when S&P >= 0%, or 0.5x when S&P < 0%.",
                )
                if not l1["c11_use_dynamic_sp500"]:
                    l1["c11_manual_min_pct"] = st.number_input(
                        "Manual Min 6M Perf (%)",
                        value=float(l1.get("c11_manual_min_pct", 24.0)),
                        step=2.0,
                    )

        with st.expander("💾 Save Custom Preset"):
            new_preset_name = st.text_input("Preset Name", placeholder="e.g. $2B MidCap + 11 Rules")
            if st.button("Save Preset", use_container_width=True) and new_preset_name.strip():
                save_custom_preset(new_preset_name.strip(), "Custom user preset", l0, l1)
                st.session_state["active_preset_name"] = new_preset_name.strip()
                st.toast(f"Saved preset: {new_preset_name.strip()}", icon="💾")
                st.rerun()

    # =========================================================================
    # EXECUTE INSTANT SCREENING (<1 SECOND)
    # =========================================================================
    t_start = time.perf_counter()
    df_l0 = apply_layer0_filter(df_universe, st.session_state["layer0_cfg"])
    df_scored, summary_meta = evaluate_layer1_conditions(
        df_l0, st.session_state["layer1_cfg"], sp500_bm
    )
    elapsed_ms = (time.perf_counter() - t_start) * 1000.0

    # =========================================================================
    # 1. COMPACT HEADER & FUNNEL RIBBON
    # =========================================================================
    db_status = "🟢 Supabase Cloud Connected" if is_supabase_configured() else "🟡 Session RAM Mode (Add SUPABASE_URL & SUPABASE_KEY in Streamlit Secrets)"
    hdr_left, hdr_right = st.columns([3.2, 1.8])
    with hdr_left:
        st.markdown("## 📈 US Stock Momentum Screener — Trading Cockpit")
        st.caption(
            f"**EOD Snapshot:** `{sp500_bm.get('as_of_date', 'Latest')}` · **Storage:** {db_status} · **Speed:** `{elapsed_ms:.0f} ms`"
        )
    with hdr_right:
        btn_c1, btn_c2 = st.columns(2)
        with btn_c1:
            if st.button("📝 Log Run Snapshot", use_container_width=True):
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
        with btn_c2:
            if st.button("🔄 Refresh EOD Data", use_container_width=True):
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

    # 5 Focused Funnel & Benchmark KPI Cards
    k1, k2, k3, k4, k5 = st.columns(5)
    l0_cnt = summary_meta["layer0_count"]
    qual_cnt = summary_meta["qualified_count"]
    near_cnt = summary_meta["near_miss_count"]
    active_cnt = summary_meta["active_condition_count"]

    k1.metric(
        "1️⃣ Layer 0 Liquid Pool",
        f"{l0_cnt:,} stocks",
        delta=f"of {len(df_universe):,} US baseline",
        delta_color="off",
    )
    k2.metric(
        f"2️⃣ Qualified Winners ({active_cnt}/{active_cnt})",
        f"{qual_cnt:,} stocks",
        delta=f"{(qual_cnt / max(1, l0_cnt) * 100):.1f}% pass rate",
    )
    k3.metric(
        f"🎯 Near-Misses ({max(0, active_cnt - 1)}/{active_cnt})",
        f"{near_cnt:,} stocks",
        delta="Missed by 1 rule",
        delta_color="off",
    )
    k4.metric(
        "S&P 500 1M ➔ C10 Target",
        f">{summary_meta['y_1m_threshold_pct']:+.2f}%",
        delta=f"S&P 1M: {summary_meta['sp500_1m_pct']:+.2f}% ({'2x' if summary_meta['sp500_1m_pct']>=0 else '0.5x'})",
        delta_color="off",
    )
    k5.metric(
        "S&P 500 6M ➔ C11 Target",
        f">{summary_meta['y_6m_threshold_pct']:+.2f}%",
        delta=f"S&P 6M: {summary_meta['sp500_6m_pct']:+.2f}% ({'2x' if summary_meta['sp500_6m_pct']>=0 else '0.5x'})",
        delta_color="off",
    )

    # Chief UI Designer Feature: Condition Bottleneck Strip
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
            "<div><small><b>🔬 Layer 1 Condition Pass Rates (Bottleneck Detector across Layer 0 Pool):</b></small>"
            f'<div class="bottleneck-bar">{"".join(chips_html)}</div></div>',
            unsafe_allow_html=True,
        )

    # =========================================================================
    # WORKSPACE TABS: Primary Trading Cockpit vs. Historical Run Logs
    # =========================================================================
    tab_cockpit, tab_history = st.tabs(
        [
            f"🚀 Primary Screening Cockpit ({qual_cnt} Qualified · {near_cnt} Near-Misses)",
            "📜 Historical Screening Run Logs",
        ]
    )

    with tab_cockpit:
        if df_scored.empty:
            st.warning("No stocks passed your current Layer 0 Pre-Filter settings. Try lowering Min Market Cap or Volume in the sidebar.")
        else:
            # Top Sector Leadership Bar (computed on 100% Qualified stocks)
            df_qual_only = df_scored[df_scored["qualified_all"]]
            if not df_qual_only.empty and "sector" in df_qual_only.columns:
                sec_counts = df_qual_only["sector"].fillna("Other").value_counts().head(6)
                sec_badges = " · ".join([f"**{sec}** (`{cnt}`)" for sec, cnt in sec_counts.items()])
                st.markdown(f"🔥 **Leading Breakout Sectors Today ({qual_cnt} Winners):** {sec_badges}")

            # One-Click Quick Filter Toolbar
            tb1, tb2, tb3, tb4 = st.columns([2.6, 1.5, 1.3, 0.8])
            with tb1:
                view_mode = st.radio(
                    "Watchlist View Mode",
                    options=[
                        f"🏆 Qualified ({active_cnt}/{active_cnt})",
                        f"🎯 Near-Misses ({max(0, active_cnt - 1)}/{active_cnt})",
                        f"👀 Broad ({max(0, active_cnt - 2)}+ Passed)",
                        f"🌐 Full Layer 0 ({l0_cnt})",
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
                    placeholder="🔍 Search Ticker (e.g. NVDA, MRNA)...",
                    label_visibility="collapsed",
                )

            # Filter dataframe according to selected pill mode
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
            # 2. 100% FULL-WIDTH HIGH-DENSITY WATCHLIST TABLE (Click-to-Inspect)
            # =================================================================
            display_cols = [
                "ticker",
                "company_name",
                "sector",
                "market_cap_b",
                "close",
                "rs_percentile",
                "perf_1m",
                "perf_6m",
                "pct_of_52w_high",
                "dollar_vol_m",
                "pass_summary",
                "diagnostic_badge",
                "tv_url",
            ]

            st.caption("💡 **Tip:** Click the checkbox on the far left of any row below to immediately load its **1-Year Daily Chart & 11-Condition Scorecard** in the Stock Cockpit Drawer below.")

            selection_event = st.dataframe(
                df_view[display_cols],
                use_container_width=True,
                height=440,
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row",
                column_config={
                    "ticker": st.column_config.TextColumn("Ticker", width="small"),
                    "company_name": st.column_config.TextColumn("Company", width="medium"),
                    "sector": st.column_config.TextColumn("Sector", width="medium"),
                    "market_cap_b": st.column_config.NumberColumn("Mkt Cap", format="$%.2fB"),
                    "close": st.column_config.NumberColumn("Price", format="$%.2f"),
                    "rs_percentile": st.column_config.ProgressColumn(
                        "RS Rank (1-99)",
                        format="%d",
                        min_value=1,
                        max_value=99,
                        help="Pool-wide Relative Strength Percentile (40% 3M + 20% 6M + 20% 9M + 20% 12M)",
                    ),
                    "perf_1m": st.column_config.NumberColumn("1M Perf", format="%+.2f%%"),
                    "perf_6m": st.column_config.NumberColumn("6M Perf", format="%+.2f%%"),
                    "pct_of_52w_high": st.column_config.ProgressColumn(
                        "% of 52W High",
                        format="%.1f%%",
                        min_value=0,
                        max_value=100,
                        help="100% = At 52-Week High. Condition #7 default requires >= 75% (within 25% of high).",
                    ),
                    "dollar_vol_m": st.column_config.NumberColumn("Price×Vol", format="$%.0fM"),
                    "pass_summary": st.column_config.TextColumn("Score", width="small"),
                    "diagnostic_badge": st.column_config.TextColumn(
                        "Status / Missed Rules",
                        width="medium",
                        help="Plain-English summary showing whether all active rules passed or which exact rule(s) missed.",
                    ),
                    "tv_url": st.column_config.LinkColumn("Chart", display_text="TradingView ↗"),
                },
            )

            # =================================================================
            # 3. DOCKED STOCK COCKPIT DRAWER (Below Full-Width Table)
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

                # Side-by-side: Interactive 1Y Price + 5 MA Chart (Left 55%) & 11-Rule Scorecard (Right 45%)
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
            st.info("No screening runs logged yet. Click **'📝 Log Run Snapshot'** in the top-right header to record daily snapshots.")
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
