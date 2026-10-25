"""
Step 5: Interactive Streamlit Web Dashboard (app.py)
US Short/Mid-Term Breakout Stock Scoring & Ranking System — Layer 0 + Layer 1
"""

from __future__ import annotations

import time
from typing import Dict, Any

import pandas as pd
import streamlit as st

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
    delete_custom_preset,
    load_run_history,
    log_screening_run,
)

st.set_page_config(
    page_title="US Stock Momentum Screener (Layer 0 + Layer 1)",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _init_session_state() -> None:
    if "layer0_cfg" not in st.session_state:
        st.session_state["layer0_cfg"] = get_default_layer0_config()
    if "layer1_cfg" not in st.session_state:
        st.session_state["layer1_cfg"] = get_default_layer1_config()
    if "active_preset_name" not in st.session_state:
        st.session_state["active_preset_name"] = list(BUILTIN_PRESETS.keys())[0]


def _apply_preset_to_state(preset_name: str, presets: Dict[str, Dict[str, Any]]) -> None:
    if preset_name in presets:
        p = presets[preset_name]
        l0 = {**get_default_layer0_config(), **p.get("layer0", {})}
        l1 = {**get_default_layer1_config(), **p.get("layer1", {})}
        st.session_state["layer0_cfg"] = l0
        st.session_state["layer1_cfg"] = l1
        st.session_state["active_preset_name"] = preset_name


def main() -> None:
    _init_session_state()

    # Header
    st.title("📈 US Stock Momentum Screener — Layer 0 & Layer 1")
    st.caption(
        "**Layer 0 (Candidate Universe Pre-Filter)** + **Layer 1 (Minervini 8-Condition Trend Template + SMA10≥SMA20 + Dynamic S&P 500 1M/6M Outperformance)**"
    )

    # Load or initialize EOD market data
    df_universe, sp500_bm = load_cached_market_data()

    if df_universe is None or df_universe.empty or sp500_bm is None:
        st.info("No cached daily EOD market snapshot found yet. Fetching initial US Market Universe & S&P 500 Benchmark...")
        progress_bar = st.progress(0, text="Starting initial EOD data fetch...")
        df_universe, sp500_bm = refresh_daily_market_data(
            enrich_yf=True,
            max_symbols_for_yf=800,
            progress_callback=lambda p, msg: progress_bar.progress(int(p * 100), text=msg),
        )
        progress_bar.empty()
        st.rerun()

    # =========================================================================
    # SIDEBAR: Presets, Layer 0 Controls, Layer 1 Controls
    # =========================================================================
    presets = load_all_presets()
    preset_names = list(presets.keys())

    with st.sidebar:
        st.header("⚙️ Screener Controls")

        # 1. Preset Selector
        selected_preset = st.selectbox(
            "Filter Preset",
            options=preset_names,
            index=preset_names.index(st.session_state["active_preset_name"])
            if st.session_state["active_preset_name"] in preset_names
            else 0,
            help="Load a saved combination of Layer 0 and Layer 1 settings in one click.",
        )
        if st.button("📂 Load Selected Preset", use_container_width=True):
            _apply_preset_to_state(selected_preset, presets)
            st.rerun()

        st.divider()

        # 2. Layer 0 Controls (12 Adjustable Parameters)
        l0 = st.session_state["layer0_cfg"]
        with st.expander("🌐 Layer 0: Universe Pre-Filter (12 Controls)", expanded=True):
            col_mc1, col_mc2 = st.columns(2)
            with col_mc1:
                l0["min_market_cap_b"] = st.number_input(
                    "Min Mkt Cap ($B)",
                    min_value=0.1,
                    max_value=500.0,
                    value=float(l0.get("min_market_cap_b", 3.0)),
                    step=0.5,
                    help="Change easily e.g. from $2.0B to $3.0B.",
                )
            with col_mc2:
                l0["max_market_cap_b"] = st.number_input(
                    "Max Mkt Cap ($B, 0=None)",
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
                    "Min Price × Vol ($M)",
                    min_value=0.0,
                    max_value=1000.0,
                    value=float(l0.get("min_dollar_vol_m", 50.0)),
                    step=5.0,
                )

            st.markdown("**Multi-Horizon Share Volume Filters (Shares)**")
            v_col1, v_col2 = st.columns(2)
            with v_col1:
                l0["min_vol_1d"] = st.number_input(
                    "1D Vol >",
                    min_value=0,
                    max_value=50_000_000,
                    value=int(l0.get("min_vol_1d", 500_000)),
                    step=50_000,
                )
                l0["min_vol_30d"] = st.number_input(
                    "Avg Vol 30D >",
                    min_value=0,
                    max_value=50_000_000,
                    value=int(l0.get("min_vol_30d", 500_000)),
                    step=50_000,
                )
                l0["min_vol_90d"] = st.number_input(
                    "Avg Vol 90D >",
                    min_value=0,
                    max_value=50_000_000,
                    value=int(l0.get("min_vol_90d", 500_000)),
                    step=50_000,
                )
            with v_col2:
                l0["min_vol_10d"] = st.number_input(
                    "Avg Vol 10D >",
                    min_value=0,
                    max_value=50_000_000,
                    value=int(l0.get("min_vol_10d", 500_000)),
                    step=50_000,
                )
                l0["min_vol_60d"] = st.number_input(
                    "Avg Vol 60D >",
                    min_value=0,
                    max_value=50_000_000,
                    value=int(l0.get("min_vol_60d", 500_000)),
                    step=50_000,
                )

            l0["exchanges"] = st.multiselect(
                "US Exchanges",
                options=ALL_EXCHANGES,
                default=l0.get("exchanges", ALL_EXCHANGES),
            )
            t_col1, t_col2 = st.columns(2)
            with t_col1:
                l0["exclude_etfs"] = st.toggle("Exclude ETFs", value=bool(l0.get("exclude_etfs", True)))
            with t_col2:
                l0["include_adrs"] = st.toggle("Include ADRs", value=bool(l0.get("include_adrs", True)))

        # 3. Layer 1 Controls (11 Conditions + Thresholds)
        l1 = st.session_state["layer1_cfg"]
        with st.expander("🎯 Layer 1: 11 Trend & Momentum Rules", expanded=True):
            st.markdown("**Minervini Core Trend Template (C1–C8)**")
            l1["c1_enabled"] = st.checkbox("C1: Price > SMA150 & SMA200", value=bool(l1.get("c1_enabled", True)))
            l1["c2_enabled"] = st.checkbox("C2: SMA150 > SMA200", value=bool(l1.get("c2_enabled", True)))
            l1["c3_enabled"] = st.checkbox("C3: SMA200 Trending Up", value=bool(l1.get("c3_enabled", True)))
            if l1["c3_enabled"]:
                l1["c3_lookback_days"] = st.select_slider(
                    "C3 Lookback Trading Days (N)",
                    options=[5, 10, 15, 20, 30, 40, 60],
                    value=int(l1.get("c3_lookback_days", 20)) if int(l1.get("c3_lookback_days", 20)) in [5, 10, 15, 20, 30, 40, 60] else 20,
                )

            l1["c4_enabled"] = st.checkbox("C4: SMA50 > SMA150 > SMA200", value=bool(l1.get("c4_enabled", True)))
            l1["c5_enabled"] = st.checkbox("C5: Price > SMA50", value=bool(l1.get("c5_enabled", True)))

            l1["c6_enabled"] = st.checkbox("C6: Price >= 52W Low + X%", value=bool(l1.get("c6_enabled", True)))
            if l1["c6_enabled"]:
                l1["c6_min_pct_above_52w_low"] = st.number_input(
                    "C6 Min % Above 52W Low",
                    min_value=0.0,
                    max_value=300.0,
                    value=float(l1.get("c6_min_pct_above_52w_low", 30.0)),
                    step=5.0,
                )

            l1["c7_enabled"] = st.checkbox("C7: Price Near 52W High (Within Y%)", value=bool(l1.get("c7_enabled", True)))
            if l1["c7_enabled"]:
                l1["c7_max_pct_below_52w_high"] = st.number_input(
                    "C7 Max % Below 52W High",
                    min_value=1.0,
                    max_value=80.0,
                    value=float(l1.get("c7_max_pct_below_52w_high", 25.0)),
                    step=5.0,
                )

            l1["c8_enabled"] = st.checkbox("C8: RS Percentile >= P", value=bool(l1.get("c8_enabled", True)))
            if l1["c8_enabled"]:
                l1["c8_min_rs_percentile"] = st.slider(
                    "C8 Min RS Percentile (1-99)",
                    min_value=1,
                    max_value=99,
                    value=int(l1.get("c8_min_rs_percentile", 70)),
                )

            st.markdown("---")
            st.markdown("**TradingView Alignment & S&P 500 Rules (C9–C11)**")
            l1["c9_enabled"] = st.checkbox("C9: SMA10 >= SMA20", value=bool(l1.get("c9_enabled", True)))

            sp_1m = float(sp500_bm.get("perf_1m_pct", 0.0))
            sp_6m = float(sp500_bm.get("perf_6m_pct", 0.0))

            l1["c10_enabled"] = st.checkbox("C10: 1M Perf > S&P 500 Target", value=bool(l1.get("c10_enabled", True)))
            if l1["c10_enabled"]:
                l1["c10_use_dynamic_sp500"] = st.toggle(
                    f"Dynamic 1M vs S&P ({sp_1m:+.2f}%)",
                    value=bool(l1.get("c10_use_dynamic_sp500", True)),
                    help="When ON: 2.0x S&P 500 return if S&P >= 0%, or 0.5x if S&P < 0%.",
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
                    f"Dynamic 6M vs S&P ({sp_6m:+.2f}%)",
                    value=bool(l1.get("c11_use_dynamic_sp500", True)),
                    help="When ON: 2.0x S&P 500 return if S&P >= 0%, or 0.5x if S&P < 0%.",
                )
                if not l1["c11_use_dynamic_sp500"]:
                    l1["c11_manual_min_pct"] = st.number_input(
                        "Manual Min 6M Perf (%)",
                        value=float(l1.get("c11_manual_min_pct", 24.0)),
                        step=2.0,
                    )

        # 4. Save Custom Preset
        with st.expander("💾 Save Current Settings as Preset"):
            new_preset_name = st.text_input("New Preset Name", placeholder="e.g. Strict $5B + 11 Rules")
            new_preset_desc = st.text_input("Short Description", placeholder="Custom Layer 0 + Layer 1 setup")
            if st.button("Save Preset", use_container_width=True):
                if new_preset_name.strip():
                    save_custom_preset(new_preset_name.strip(), new_preset_desc.strip(), l0, l1)
                    st.session_state["active_preset_name"] = new_preset_name.strip()
                    st.success(f"Saved preset: {new_preset_name.strip()}")
                    st.rerun()
                else:
                    st.warning("Please enter a preset name.")

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
    # TOP SUMMARY METRICS & BENCHMARK BAR
    # =========================================================================
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Baseline Universe", f"{len(df_universe):,}", help="Cached liquid US stocks")
    m2.metric("Layer 0 Candidates", f"{summary_meta['layer0_count']:,}", help="Passed Market Cap, Price & Volume filters")
    m3.metric(
        f"Layer 1 Qualified ({summary_meta['active_condition_count']}/{summary_meta['active_condition_count']})",
        f"{summary_meta['qualified_count']:,}",
        help="Stocks passing 100% of enabled Layer 1 conditions",
    )
    m4.metric(
        "S&P 500 1M → Target Y",
        f"{summary_meta['y_1m_threshold_pct']:+.2f}%",
        delta=f"S&P 1M: {summary_meta['sp500_1m_pct']:+.2f}%",
        delta_color="normal",
    )
    m5.metric(
        "S&P 500 6M → Target Y",
        f"{summary_meta['y_6m_threshold_pct']:+.2f}%",
        delta=f"S&P 6M: {summary_meta['sp500_6m_pct']:+.2f}%",
        delta_color="normal",
    )
    m6.metric("Screen Speed", f"{elapsed_ms:.0f} ms", delta=f"As of {sp500_bm.get('as_of_date', 'Today')}")

    # Action Buttons Bar
    act_col1, act_col2, act_col3 = st.columns([2, 2, 4])
    with act_col1:
        if st.button("📝 Log / Save This Screening Run", use_container_width=True):
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
            st.toast("Screening run saved to Run History!", icon="✅")
    with act_col2:
        if st.button("🔄 Refresh Live EOD Market Data", use_container_width=True):
            prog = st.progress(0, text="Refreshing live market data...")
            df_universe, sp500_bm = refresh_daily_market_data(
                enrich_yf=True,
                max_symbols_for_yf=800,
                progress_callback=lambda p, msg: prog.progress(int(p * 100), text=msg),
            )
            prog.empty()
            st.rerun()

    # =========================================================================
    # MAIN TABS: Watchlist Table | Condition Drill-Down | Run History
    # =========================================================================
    tab_results, tab_drilldown, tab_history = st.tabs(
        [
            f"🏆 Screening Results ({summary_meta['qualified_count']} Qualified / {summary_meta['layer0_count']} Pool)",
            "🔍 Stock Condition Drill-Down (Pass/Fail Detail)",
            "📜 Screening Run History",
        ]
    )

    with tab_results:
        if df_scored.empty:
            st.warning("No stocks passed the current Layer 0 Pre-Filter settings. Try loosening Market Cap or Volume figures.")
        else:
            active_cnt = summary_meta["active_condition_count"]
            f_col1, f_col2, f_col3 = st.columns([2, 2, 2])
            with f_col1:
                min_passed_filter = st.slider(
                    "Minimum Conditions Passed to Display",
                    min_value=0,
                    max_value=max(1, active_cnt),
                    value=active_cnt,
                    help="Set to max to view only 100% qualified stocks, or lower by 1-2 to inspect near-miss candidates.",
                )
            with f_col2:
                search_query = st.text_input("Filter by Ticker or Company Name", placeholder="e.g. NVDA, PLTR...")

            df_view = df_scored[df_scored["passed_count"] >= min_passed_filter].copy()
            if search_query.strip():
                q = search_query.strip().lower()
                df_view = df_view[
                    df_view["ticker"].str.lower().str.contains(q)
                    | df_view["company_name"].fillna("").str.lower().str.contains(q)
                ]

            df_view["tv_url"] = (
                "https://www.tradingview.com/chart/?symbol="
                + df_view["exchange"].astype(str)
                + "%3A"
                + df_view["ticker"].astype(str)
            )

            display_cols = [
                "ticker",
                "company_name",
                "exchange",
                "sector",
                "market_cap_b",
                "close",
                "rs_percentile",
                "pass_summary",
                "perf_1m",
                "perf_6m",
                "dollar_vol_m",
                "vol_1d",
                "sma_50",
                "sma_150",
                "sma_200",
                "tv_url",
            ]

            st.dataframe(
                df_view[display_cols],
                use_container_width=True,
                height=520,
                hide_index=True,
                column_config={
                    "ticker": st.column_config.TextColumn("Ticker", width="small"),
                    "company_name": st.column_config.TextColumn("Company Name", width="medium"),
                    "exchange": st.column_config.TextColumn("Exch", width="small"),
                    "sector": st.column_config.TextColumn("Sector", width="medium"),
                    "market_cap_b": st.column_config.NumberColumn("Mkt Cap ($B)", format="$%.2fB"),
                    "close": st.column_config.NumberColumn("Price ($)", format="$%.2f"),
                    "rs_percentile": st.column_config.NumberColumn("RS Rating", format="%d"),
                    "pass_summary": st.column_config.TextColumn("Passed (X/N)", width="small"),
                    "perf_1m": st.column_config.NumberColumn("1M Perf %", format="%+.2f%%"),
                    "perf_6m": st.column_config.NumberColumn("6M Perf %", format="%+.2f%%"),
                    "dollar_vol_m": st.column_config.NumberColumn("Price×Vol ($M)", format="$%.1fM"),
                    "vol_1d": st.column_config.NumberColumn("1D Vol", format="%d"),
                    "sma_50": st.column_config.NumberColumn("SMA 50", format="$%.2f"),
                    "sma_150": st.column_config.NumberColumn("SMA 150", format="$%.2f"),
                    "sma_200": st.column_config.NumberColumn("SMA 200", format="$%.2f"),
                    "tv_url": st.column_config.LinkColumn("TradingView", display_text="Open Chart ↗"),
                },
            )

            csv_bytes = df_view[display_cols].to_csv(index=False).encode("utf-8")
            st.download_button(
                label=f"⬇️ Export Displayed Watchlist ({len(df_view)} Stocks) to CSV",
                data=csv_bytes,
                file_name=f"us_momentum_watchlist_{sp500_bm.get('as_of_date', 'eod')}.csv",
                mime="text/csv",
            )

    with tab_drilldown:
        if df_scored.empty:
            st.info("No candidate stocks in Layer 0 pool to inspect.")
        else:
            st.subheader("Inspect Exact Pass/Fail Values Per Stock")
            ticker_options = (
                df_scored["ticker"]
                + " — "
                + df_scored["company_name"].fillna("")
                + " ("
                + df_scored["pass_summary"]
                + " Passed | RS "
                + df_scored["rs_percentile"].astype(str)
                + ")"
            ).tolist()
            selected_option = st.selectbox("Select a Candidate Stock from Layer 0 Pool:", options=ticker_options)
            sel_idx = ticker_options.index(selected_option)
            stock_row = df_scored.iloc[sel_idx]

            c_info1, c_info2, c_info3, c_info4, c_info5 = st.columns(5)
            c_info1.metric("Ticker", f"{stock_row['ticker']} ({stock_row['exchange']})")
            c_info2.metric("Price", f"${stock_row['close']:.2f}")
            c_info3.metric("Market Cap", f"${stock_row['market_cap_b']:.2f}B")
            c_info4.metric("RS Percentile", f"{int(stock_row['rs_percentile'])} / 99")
            c_info5.metric("Conditions Passed", stock_row["pass_summary"])

            breakdown = build_stock_condition_breakdown(
                stock_row, st.session_state["layer1_cfg"], summary_meta
            )
            df_bd = pd.DataFrame(breakdown)
            df_bd["Status"] = df_bd.apply(
                lambda r: "⚪ OFF (Ignored)"
                if not r["Enabled"]
                else ("✅ PASS" if r["Passed"] else "❌ FAIL"),
                axis=1,
            )
            st.dataframe(
                df_bd[["Condition", "Status", "Stock Value", "Required Threshold"]],
                use_container_width=True,
                hide_index=True,
                height=430,
            )

    with tab_history:
        st.subheader("Past Screening Run Logs")
        history = load_run_history()
        if not history:
            st.info("No screening runs logged yet. Click **'Log / Save This Screening Run'** above to record snapshots for comparison.")
        else:
            df_hist = pd.DataFrame(history)
            df_hist["Top Qualifying Tickers"] = df_hist["top_tickers"].apply(
                lambda lst: ", ".join(lst[:12]) + ("..." if len(lst) > 12 else "") if isinstance(lst, list) else ""
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
