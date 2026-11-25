"""
Multi-Tab Layer Result Grids (`src/ui/watchlist_grid.py`) —
Renders dedicated, self-contained result tables for each screening layer tab:
  - Tab 0: Layer 0 Candidate Universe Pre-Filter Results
  - Tab 1: Layer 1 Trend & Momentum (11 Rules) Results
  - Tab 2: Layer 2 Industry & CAN SLIM Fundamental Leadership Results
  - Tab 3: Layer 3 VCP & EMA Structure Setups + Grouped Live TradingView Chart Cockpit
  - Tab 4: Layer 4 Actionable Breakout Entry Triggers Results
  - Tab 5: Layer 5 Risk Management, Stop-Loss (1R) & Position Sizing Order Sheet
"""

from __future__ import annotations

from typing import Dict, Any, List

import pandas as pd
import streamlit as st

from src.config import build_tv_chart_url
from src.ui.tradingview_cockpit import render_tradingview_cockpit


def _style_table_with_active_row(
    df: pd.DataFrame,
    active_symbol: str,
    columns: List[str],
) -> pd.io.formats.style.Styler:
    """Creates a styled dataframe marking the active stock with '▶' and cyan row highlight."""
    df_table = df[columns].copy()
    active_row_idx = None

    if not df_table.empty and "ticker" in df_table.columns:
        formatted_tickers = []
        for i, t in enumerate(df_table["ticker"]):
            if str(t).strip() == str(active_symbol).strip():
                formatted_tickers.append(f"▶ {t}")
                active_row_idx = i
            else:
                formatted_tickers.append(f"   {t}")
        df_table["ticker"] = formatted_tickers

    def _highlight(row: pd.Series) -> list[str]:
        if active_row_idx is not None and row.name == active_row_idx:
            return [
                "background-color: rgba(56, 189, 248, 0.24); color: #ffffff; font-weight: 700;"
            ] * len(row)
        return [""] * len(row)

    return df_table.style.apply(_highlight, axis=1)


def _attach_tv_urls(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    active_layout_id = st.session_state.get("tv_layout_id", "")
    out["tv_url"] = out.apply(
        lambda r: build_tv_chart_url(str(r.get("exchange", "NASDAQ")), str(r["ticker"]), active_layout_id),
        axis=1,
    )
    return out


def _render_common_search_and_sector_bar(
    df_source: pd.DataFrame,
    key_prefix: str,
    csv_filename: str,
    extra_left_col_ratio: float = 2.4,
):
    """Renders Sector filter, Symbol search, and CSV export toolbar for a layer tab."""
    all_sectors = sorted(df_source["sector"].dropna().unique().tolist()) if "sector" in df_source.columns else []
    c1, c2, c3 = st.columns([extra_left_col_ratio, 1.4, 0.8])
    with c1:
        selected_sectors = st.multiselect(
            "Filter by Sector",
            options=all_sectors,
            placeholder="Filter by Sector (All Sectors)...",
            key=f"{key_prefix}_sector_filter",
            label_visibility="collapsed",
        )
    with c2:
        search_query = st.text_input(
            "Search Symbol or Company",
            placeholder="🔍 Search Symbol / Company...",
            key=f"{key_prefix}_search_box",
            label_visibility="collapsed",
        )

    df_sub = df_source.copy()
    if selected_sectors and "sector" in df_sub.columns:
        df_sub = df_sub[df_sub["sector"].isin(selected_sectors)]
    if search_query.strip():
        q = search_query.strip().lower()
        df_sub = df_sub[
            df_sub["ticker"].astype(str).str.lower().str.contains(q)
            | df_sub.get("company_name", pd.Series("", index=df_sub.index)).fillna("").astype(str).str.lower().str.contains(q)
        ]
    df_sub = _attach_tv_urls(df_sub.reset_index(drop=True))

    with c3:
        csv_bytes = df_sub.to_csv(index=False).encode("utf-8")
        st.download_button(
            label=f"⬇️ CSV ({len(df_sub)})",
            data=csv_bytes,
            file_name=csv_filename,
            mime="text/csv",
            use_container_width=True,
            key=f"{key_prefix}_csv_dl",
        )
    return df_sub


# =========================================================================
# TAB 0: Layer 0 — Universe Pre-Filter Results
# =========================================================================
def render_layer0_tab_results(df_scored: pd.DataFrame, summary_meta: Dict[str, Any], sp500_bm: Dict[str, Any]) -> None:
    """Renders Layer 0 Universe Pre-Filter results inside Tab 0."""
    if df_scored.empty:
        st.warning("No stocks passed your Layer 0 Pre-Filter pills above. Loosen Market Cap or Volume thresholds.")
        return

    st.markdown(
        f"#### 🌐 **Layer 0 Qualified Institutional Universe** &nbsp; "
        f"<span style='background:rgba(56,189,248,0.18); color:#38bdf8; padding:3px 10px; border-radius:12px; font-weight:700; font-size:0.88rem;'>"
        f"{len(df_scored)} Liquid US Equities</span>",
        unsafe_allow_html=True,
    )
    df_sub = _render_common_search_and_sector_bar(
        df_scored,
        key_prefix="tab_l0",
        csv_filename=f"layer0_universe_{sp500_bm.get('as_of_date', 'eod')}.csv",
    )

    cols = [
        c for c in [
            "ticker", "company_name", "exchange", "sector", "industry",
            "close", "market_cap_b", "dollar_vol_m", "vol_1d", "vol_10d", "vol_30d", "vol_60d", "vol_90d", "tv_url"
        ] if c in df_sub.columns
    ]
    st.dataframe(
        df_sub[cols],
        use_container_width=True,
        height=460,
        hide_index=True,
        column_config={
            "ticker": st.column_config.TextColumn(f"Symbol ({len(df_sub)})", width="small"),
            "company_name": st.column_config.TextColumn("Company Name", width="medium"),
            "exchange": st.column_config.TextColumn("Exch", width="small"),
            "sector": st.column_config.TextColumn("Sector", width="medium"),
            "industry": st.column_config.TextColumn("Industry", width="medium"),
            "close": st.column_config.NumberColumn("Price", format="$%.2f"),
            "market_cap_b": st.column_config.NumberColumn("Mkt Cap", format="$%.2fB"),
            "dollar_vol_m": st.column_config.NumberColumn("Dollar Vol", format="$%.1fM"),
            "vol_1d": st.column_config.NumberColumn("Vol 1D", format="%d"),
            "vol_10d": st.column_config.NumberColumn("Avg Vol 10D", format="%d"),
            "vol_30d": st.column_config.NumberColumn("Avg Vol 30D", format="%d"),
            "vol_60d": st.column_config.NumberColumn("Avg Vol 60D", format="%d"),
            "vol_90d": st.column_config.NumberColumn("Avg Vol 90D", format="%d"),
            "tv_url": st.column_config.LinkColumn("BKCHO Chart", display_text="Open in TV ↗"),
        },
    )


# =========================================================================
# TAB 1: Layer 1 — Trend & Momentum Template (11 Rules) Results
# =========================================================================
def render_layer1_tab_results(df_scored: pd.DataFrame, summary_meta: Dict[str, Any], sp500_bm: Dict[str, Any]) -> None:
    """Renders Layer 1 Trend & Momentum 11-Condition results inside Tab 1."""
    if df_scored.empty:
        st.warning("No stocks passed Layer 0.")
        return

    qual_cnt = summary_meta.get("qualified_count", 0)
    near_cnt = summary_meta.get("near_miss_count", 0)
    l0_cnt = summary_meta.get("layer0_count", len(df_scored))
    active_cnt = summary_meta.get("active_condition_count", 11)

    tb1, tb2 = st.columns([2.8, 1.5])
    with tb1:
        view_mode = st.radio(
            "Layer 1 View Mode",
            options=[
                f"🏆 All L1 Qualified ({active_cnt}/{active_cnt}) [{qual_cnt}]",
                f"🎯 Near-Miss ({max(0, active_cnt - 1)}/{active_cnt}) [{near_cnt}]",
                f"🌐 Full L0 Pool [{l0_cnt}]",
            ],
            horizontal=True,
            key="tab_l1_view_mode",
            label_visibility="collapsed",
        )
    with tb2:
        sort_mode = st.selectbox(
            "Layer 1 Sort Order",
            options=[
                "⚡ Pure RS Rating (Stock RS)",
                "🏔️ Near 52W High (% of High)",
                "🚀 1M Momentum (Perf 1M)",
                "🏛️ Market Cap (Mega to Small)",
            ],
            key="tab_l1_sort_mode",
            label_visibility="collapsed",
        )

    if view_mode.startswith("🏆"):
        df_base = df_scored[df_scored["qualified_all"]].copy()
    elif view_mode.startswith("🎯"):
        df_base = df_scored[df_scored["passed_count"] == max(0, active_cnt - 1)].copy()
    else:
        df_base = df_scored.copy()

    if not df_base.empty:
        if sort_mode.startswith("⚡"):
            sc = [c for c in ["rs_percentile", "pct_of_52w_high", "perf_1m"] if c in df_base.columns]
        elif sort_mode.startswith("🏔️"):
            sc = [c for c in ["pct_of_52w_high", "rs_percentile", "perf_1m"] if c in df_base.columns]
        elif sort_mode.startswith("🚀"):
            sc = [c for c in ["perf_1m", "rs_percentile", "pct_of_52w_high"] if c in df_base.columns]
        else:
            sc = [c for c in ["market_cap_b", "rs_percentile"] if c in df_base.columns]
        df_base = df_base.sort_values(by=sc, ascending=[False] * len(sc))

    df_sub = _render_common_search_and_sector_bar(
        df_base,
        key_prefix="tab_l1",
        csv_filename=f"layer1_trend_{sp500_bm.get('as_of_date', 'eod')}.csv",
    )

    cols = [
        c for c in [
            "ticker", "company_name", "diagnostic_badge", "pass_summary", "rs_percentile",
            "close", "sma_50", "sma_150", "sma_200", "perf_1m", "perf_6m",
            "pct_of_52w_high", "pct_above_52w_low", "market_cap_b", "tv_url"
        ] if c in df_sub.columns
    ]
    st.dataframe(
        df_sub[cols],
        use_container_width=True,
        height=440,
        hide_index=True,
        column_config={
            "ticker": st.column_config.TextColumn(f"Symbol ({len(df_sub)})", width="small"),
            "company_name": st.column_config.TextColumn("Company", width="medium"),
            "diagnostic_badge": st.column_config.TextColumn("L1 Trend Status", width="medium"),
            "pass_summary": st.column_config.TextColumn("Rules", width="small"),
            "rs_percentile": st.column_config.ProgressColumn("Stock RS", format="%d", min_value=1, max_value=99),
            "close": st.column_config.NumberColumn("Price", format="$%.2f"),
            "sma_50": st.column_config.NumberColumn("SMA 50", format="$%.2f"),
            "sma_150": st.column_config.NumberColumn("SMA 150", format="$%.2f"),
            "sma_200": st.column_config.NumberColumn("SMA 200", format="$%.2f"),
            "perf_1m": st.column_config.NumberColumn("Perf 1M", format="%+.2f%%"),
            "perf_6m": st.column_config.NumberColumn("Perf 6M", format="%+.2f%%"),
            "pct_of_52w_high": st.column_config.ProgressColumn("% 52W High", format="%.1f%%", min_value=0, max_value=100),
            "pct_above_52w_low": st.column_config.NumberColumn("Above 52W Low", format="+%.1f%%"),
            "market_cap_b": st.column_config.NumberColumn("Mkt Cap", format="$%.2fB"),
            "tv_url": st.column_config.LinkColumn("BKCHO Chart", display_text="Open in TV ↗"),
        },
    )


# =========================================================================
# TAB 2: Layer 2 — Industry & CAN SLIM Fundamental Leadership Results
# =========================================================================
def render_layer2_tab_results(df_scored: pd.DataFrame, summary_meta: Dict[str, Any], sp500_bm: Dict[str, Any]) -> None:
    """Renders Layer 2 Industry Rotation & CAN SLIM Fundamental Leadership results inside Tab 2."""
    if df_scored.empty:
        st.warning("No stocks available.")
        return

    l2_meta = summary_meta.get("l2_meta", {})
    l2_qual_cnt = l2_meta.get("l2_qualified_count", 0)
    lw_cnt = l2_meta.get("lone_wolf_count", 0)
    l1_qual_cnt = summary_meta.get("qualified_count", 0)

    tb1, tb2 = st.columns([2.8, 1.5])
    with tb1:
        view_mode = st.radio(
            "Layer 2 View Mode",
            options=[
                f"🎯 L2 Qualified Leaders [{l2_qual_cnt}]",
                f"🦅 Lone Wolf Super-Leaders [{lw_cnt}]",
                f"🏆 All L1 Qualified [{l1_qual_cnt}]",
            ],
            horizontal=True,
            key="tab_l2_view_mode",
            label_visibility="collapsed",
        )
    with tb2:
        sort_mode = st.selectbox(
            "Layer 2 Sort Order",
            options=[
                "🥇 Overall Strongest (L2 Composite Score)",
                "⚡ Pure Stock RS Rating",
                "🏆 Industry Group RS Rank",
            ],
            key="tab_l2_sort_mode",
            label_visibility="collapsed",
        )

    if view_mode.startswith("🎯"):
        df_base = df_scored[df_scored["qualified_all"] & df_scored.get("l2_qualified", True)].copy()
    elif view_mode.startswith("🦅"):
        df_base = df_scored[df_scored["qualified_all"] & df_scored.get("is_lone_wolf", False)].copy()
    else:
        df_base = df_scored[df_scored["qualified_all"]].copy()

    if not df_base.empty:
        if sort_mode.startswith("🥇"):
            sc = [c for c in ["composite_score", "rs_percentile", "group_rs_percentile"] if c in df_base.columns]
        elif sort_mode.startswith("⚡"):
            sc = [c for c in ["rs_percentile", "composite_score", "group_rs_percentile"] if c in df_base.columns]
        else:
            sc = [c for c in ["group_rs_percentile", "composite_score", "rs_percentile"] if c in df_base.columns]
        df_base = df_base.sort_values(by=sc, ascending=[False] * len(sc))

    df_sub = _render_common_search_and_sector_bar(
        df_base,
        key_prefix="tab_l2",
        csv_filename=f"layer2_industry_leaders_{sp500_bm.get('as_of_date', 'eod')}.csv",
    )

    cols = [
        c for c in [
            "ticker", "company_name", "composite_score", "l2_badge", "fund_badge",
            "rs_percentile", "group_rs_percentile", "industry_rank_str",
            "close", "perf_1m", "perf_6m", "pct_of_52w_high", "market_cap_b", "tv_url"
        ] if c in df_sub.columns
    ]
    st.dataframe(
        df_sub[cols],
        use_container_width=True,
        height=440,
        hide_index=True,
        column_config={
            "ticker": st.column_config.TextColumn(f"Symbol ({len(df_sub)})", width="small"),
            "company_name": st.column_config.TextColumn("Company", width="medium"),
            "composite_score": st.column_config.NumberColumn("L2 Score", format="%.1f", width="small"),
            "l2_badge": st.column_config.TextColumn("Industry Status", width="medium"),
            "fund_badge": st.column_config.TextColumn("CAN SLIM Fundamentals", width="medium"),
            "rs_percentile": st.column_config.ProgressColumn("Stock RS", format="%d", min_value=1, max_value=99),
            "group_rs_percentile": st.column_config.NumberColumn("Ind RS", format="%d", width="small"),
            "industry_rank_str": st.column_config.TextColumn("Industry & Rank", width="medium"),
            "close": st.column_config.NumberColumn("Price", format="$%.2f"),
            "perf_1m": st.column_config.NumberColumn("Perf 1M", format="%+.2f%%"),
            "perf_6m": st.column_config.NumberColumn("Perf 6M", format="%+.2f%%"),
            "pct_of_52w_high": st.column_config.ProgressColumn("% 52W High", format="%.1f%%", min_value=0, max_value=100),
            "market_cap_b": st.column_config.NumberColumn("Mkt Cap", format="$%.2fB"),
            "tv_url": st.column_config.LinkColumn("BKCHO Chart", display_text="Open in TV ↗"),
        },
    )


# =========================================================================
# TAB 3: Layer 3 — VCP & EMA Structure Setups + Grouped TradingView Chart Cockpit
# =========================================================================
def render_layer3_tab_results_with_chart(
    df_scored: pd.DataFrame,
    summary_meta: Dict[str, Any],
    sp500_bm: Dict[str, Any],
) -> None:
    """
    Renders Layer 3 VCP & EMA Setups Table AND groups the Live Embedded TradingView Chart Cockpit
    directly below the table inside the Layer 3 Tab.
    """
    if df_scored.empty:
        st.warning("No stocks available.")
        return

    df_l3 = df_scored[
        df_scored.get("qualified_all", True)
        & df_scored.get("l2_qualified", True)
        & df_scored.get("l3_qualified", True)
    ].copy()

    l4_meta = summary_meta.get("l4_meta", {})
    trig_cnt = int((df_l3.get("action_status", "") == "TRIGGERED").sum()) if not df_l3.empty else l4_meta.get("triggered_count", 0)
    bz_cnt = int((df_l3.get("action_status", "") == "BUY_ZONE").sum()) if not df_l3.empty else l4_meta.get("buy_zone_count", 0)
    deck_cnt = int((df_l3.get("action_status", "") == "ON_DECK").sum()) if not df_l3.empty else l4_meta.get("on_deck_count", 0)

    st.markdown(
        f"#### 🎯 **Layer 3 VCP Tightness & EMA Structure Setups** &nbsp; "
        f"<span style='background:rgba(56,189,248,0.18); color:#38bdf8; padding:3px 10px; border-radius:12px; font-weight:700; font-size:0.88rem;'>"
        f"{len(df_l3)} VCP Setups ({trig_cnt} 🚀 Triggered · {bz_cnt} ⚡ Buy Zone · {deck_cnt} ⏳ On Deck)</span>",
        unsafe_allow_html=True,
    )

    if not df_l3.empty:
        status_rank_map = {"TRIGGERED": 0, "BUY_ZONE": 1, "ON_DECK": 2, "EXTENDED": 3, "BUILDING": 4}
        df_l3["_status_rank"] = df_l3.get("action_status", pd.Series("BUILDING", index=df_l3.index)).map(status_rank_map).fillna(5)
        sort_by_cols = [c for c in ["_status_rank", "composite_score", "vcp_score", "rs_percentile"] if c in df_l3.columns]
        df_l3 = df_l3.sort_values(
            by=sort_by_cols,
            ascending=[True, False, False, False][:len(sort_by_cols)],
        ).reset_index(drop=True)

    df_sub = _render_common_search_and_sector_bar(
        df_l3,
        key_prefix="tab_l3",
        csv_filename=f"layer3_vcp_setups_{sp500_bm.get('as_of_date', 'eod')}.csv",
    )

    if df_sub.empty:
        st.info(
            "ℹ️ No stocks currently fulfill strict Layer 3 VCP & EMA criteria with your active thresholds. "
            "Use the Layer 3 filter pills above to relax contraction, volume dry-up, or ADR% thresholds."
        )
        return

    # Synchronize row selection with the Layer 3 TradingView Chart Cockpit below
    t3_state = st.session_state.get("l3_df_widget")
    if t3_state and isinstance(t3_state, dict):
        cur_sel = t3_state.get("selection", {}).get("rows", [])
        if cur_sel and cur_sel != st.session_state.get("last_l3_sel", []):
            st.session_state["last_l3_sel"] = cur_sel
            if 0 <= cur_sel[0] < len(df_sub):
                st.session_state["selected_ticker"] = str(df_sub.iloc[cur_sel[0]]["ticker"])
                st.session_state["active_row_idx"] = int(cur_sel[0])

    active_idx = int(st.session_state.get("active_row_idx", 0))
    active_idx = max(0, min(active_idx, len(df_sub) - 1))
    st.session_state["active_row_idx"] = active_idx
    selected_ticker = str(df_sub.iloc[active_idx]["ticker"])
    st.session_state["selected_ticker"] = selected_ticker

    t3_cols = [
        c for c in [
            "ticker",
            "vcp_score",
            "vcp_badge",
            "last_contraction_pct",
            "vol_dryup_pct",
            "adr_20_pct",
            "dist_to_ema21_pct",
            "action_status_badge",
            "pivot_price",
            "dist_to_pivot_pct",
            "close",
            "ema_21",
            "ema_50",
            "composite_score",
            "rs_percentile",
            "group_rs_percentile",
            "industry_rank_str",
            "tv_url",
        ] if c in df_sub.columns
    ]

    styler_t3 = _style_table_with_active_row(df_sub, selected_ticker, t3_cols)

    st.dataframe(
        styler_t3,
        key="l3_df_widget",
        use_container_width=True,
        height=230,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "ticker": st.column_config.TextColumn(f"Symbol ({len(df_sub)})", width="small"),
            "vcp_score": st.column_config.ProgressColumn("VCP Score", format="%d", min_value=0, max_value=100),
            "vcp_badge": st.column_config.TextColumn("VCP / EMA Structure", width="medium"),
            "last_contraction_pct": st.column_config.NumberColumn("10D Tight %", format="%.1f%%"),
            "vol_dryup_pct": st.column_config.NumberColumn("5D Vol Dry %", format="%.0f%%"),
            "adr_20_pct": st.column_config.NumberColumn("ADR(20) %", format="%.1f%%"),
            "dist_to_ema21_pct": st.column_config.NumberColumn("21EMA Dist", format="%+.1f%%"),
            "action_status_badge": st.column_config.TextColumn("Breakout Status", width="medium"),
            "pivot_price": st.column_config.NumberColumn("Pivot ($)", format="$%.2f"),
            "dist_to_pivot_pct": st.column_config.NumberColumn("Pivot Dist", format="%+.1f%%"),
            "close": st.column_config.NumberColumn("Price", format="$%.2f"),
            "ema_21": st.column_config.NumberColumn("21 EMA", format="$%.2f"),
            "ema_50": st.column_config.NumberColumn("50 EMA", format="$%.2f"),
            "composite_score": st.column_config.NumberColumn("L2 Score", format="%.1f", width="small"),
            "rs_percentile": st.column_config.ProgressColumn("Stock RS", format="%d", min_value=1, max_value=99),
            "group_rs_percentile": st.column_config.NumberColumn("Ind RS", format="%d", width="small"),
            "industry_rank_str": st.column_config.TextColumn("Industry & Rank", width="medium"),
            "tv_url": st.column_config.LinkColumn("BKCHO Chart", display_text="Open in TV ↗"),
        },
    )

    st.markdown("---")
    # Render the Live Embedded TradingView Advanced Chart Cockpit right inside Layer 3!
    render_tradingview_cockpit(df_sub)


# =========================================================================
# TAB 4: Layer 4 — Breakout Entry Triggers & Pivot Detection Results
# =========================================================================
def render_layer4_tab_results(df_scored: pd.DataFrame, summary_meta: Dict[str, Any], sp500_bm: Dict[str, Any]) -> None:
    """Renders Layer 4 Actionable Breakout Entry Signals & Pivot Proximity results inside Tab 4."""
    if df_scored.empty:
        st.warning("No stocks available.")
        return

    df_l4 = df_scored[
        df_scored.get("qualified_all", True)
        & df_scored.get("l2_qualified", True)
        & df_scored.get("l3_qualified", True)
        & df_scored.get("l4_qualified", True)
    ].copy()

    if not df_l4.empty:
        status_rank_map = {"TRIGGERED": 0, "BUY_ZONE": 1, "ON_DECK": 2, "EXTENDED": 3, "BUILDING": 4}
        df_l4["_status_rank"] = df_l4.get("action_status", pd.Series("BUILDING", index=df_l4.index)).map(status_rank_map).fillna(5)
        sc = [c for c in ["_status_rank", "composite_score", "vcp_score", "rs_percentile"] if c in df_l4.columns]
        df_l4 = df_l4.sort_values(by=sc, ascending=[True, False, False, False][:len(sc)]).reset_index(drop=True)

    trig_cnt = int((df_l4.get("action_status", "") == "TRIGGERED").sum()) if not df_l4.empty else 0
    bz_cnt = int((df_l4.get("action_status", "") == "BUY_ZONE").sum()) if not df_l4.empty else 0
    deck_cnt = int((df_l4.get("action_status", "") == "ON_DECK").sum()) if not df_l4.empty else 0

    st.markdown(
        f"#### ⚡ **Layer 4 Actionable Breakout Entry Triggers** &nbsp; "
        f"<span style='background:rgba(56,189,248,0.18); color:#38bdf8; padding:3px 10px; border-radius:12px; font-weight:700; font-size:0.88rem;'>"
        f"{len(df_l4)} Actionable Candidates ({trig_cnt} 🚀 Triggered · {bz_cnt} ⚡ Buy Zone · {deck_cnt} ⏳ On Deck)</span>",
        unsafe_allow_html=True,
    )

    df_sub = _render_common_search_and_sector_bar(
        df_l4,
        key_prefix="tab_l4",
        csv_filename=f"layer4_entry_signals_{sp500_bm.get('as_of_date', 'eod')}.csv",
    )

    if df_sub.empty:
        st.info("ℹ️ No stocks match your Layer 4 Action Status filter. Try switching 'Action Status' to ALL or loosening Buy Zone / On-Deck sliders above.")
        return

    cols = [
        c for c in [
            "ticker", "company_name", "action_status_badge", "pivot_price", "pivot_type",
            "dist_to_pivot_pct", "vol_expansion_pct", "close", "vcp_score", "vcp_badge",
            "last_contraction_pct", "vol_dryup_pct", "adr_20_pct", "composite_score", "rs_percentile", "tv_url"
        ] if c in df_sub.columns
    ]
    st.dataframe(
        df_sub[cols],
        use_container_width=True,
        height=440,
        hide_index=True,
        column_config={
            "ticker": st.column_config.TextColumn(f"Symbol ({len(df_sub)})", width="small"),
            "company_name": st.column_config.TextColumn("Company", width="medium"),
            "action_status_badge": st.column_config.TextColumn("Entry Trigger Status", width="medium"),
            "pivot_price": st.column_config.NumberColumn("Pivot ($)", format="$%.2f"),
            "pivot_type": st.column_config.TextColumn("Pivot Basis", width="small"),
            "dist_to_pivot_pct": st.column_config.NumberColumn("Dist to Pivot", format="%+.2f%%"),
            "vol_expansion_pct": st.column_config.NumberColumn("Vol Surge %", format="%.0f%%"),
            "close": st.column_config.NumberColumn("Close ($)", format="$%.2f"),
            "vcp_score": st.column_config.ProgressColumn("VCP Score", format="%d", min_value=0, max_value=100),
            "vcp_badge": st.column_config.TextColumn("VCP Structure", width="medium"),
            "last_contraction_pct": st.column_config.NumberColumn("10D Tight %", format="%.1f%%"),
            "vol_dryup_pct": st.column_config.NumberColumn("5D Dry %", format="%.0f%%"),
            "adr_20_pct": st.column_config.NumberColumn("ADR %", format="%.1f%%"),
            "composite_score": st.column_config.NumberColumn("L2 Score", format="%.1f", width="small"),
            "rs_percentile": st.column_config.ProgressColumn("Stock RS", format="%d", min_value=1, max_value=99),
            "tv_url": st.column_config.LinkColumn("BKCHO Chart", display_text="Open in TV ↗"),
        },
    )


# =========================================================================
# TAB 5: Layer 5 — Risk Management, Stop-Loss (1R) & Position Sizing Results
# =========================================================================
def render_layer5_tab_results(df_scored: pd.DataFrame, summary_meta: Dict[str, Any], sp500_bm: Dict[str, Any]) -> None:
    """Renders Layer 5 Risk Management, Stop-Loss (1R), JLaw Hybrid Exit & Position Sizing Order Sheet inside Tab 5."""
    if df_scored.empty:
        st.warning("No stocks available.")
        return

    df_l5 = df_scored[
        df_scored.get("qualified_all", True)
        & df_scored.get("l2_qualified", True)
        & df_scored.get("l3_qualified", True)
        & df_scored.get("l4_qualified", True)
        & df_scored.get("l5_qualified", True)
    ].copy()

    if not df_l5.empty:
        status_rank_map = {"TRIGGERED": 0, "BUY_ZONE": 1, "ON_DECK": 2, "EXTENDED": 3, "BUILDING": 4}
        df_l5["_status_rank"] = df_l5.get("action_status", pd.Series("BUILDING", index=df_l5.index)).map(status_rank_map).fillna(5)
        sc = [c for c in ["_status_rank", "composite_score", "vcp_score", "rs_percentile"] if c in df_l5.columns]
        df_l5 = df_l5.sort_values(by=sc, ascending=[True, False, False, False][:len(sc)]).reset_index(drop=True)

    l5_meta = summary_meta.get("l5_meta", {})
    eq = float(l5_meta.get("account_equity", 100000.0))
    max_r_dlr = float(l5_meta.get("max_dollar_risk", 1000.0))
    avg_r = float(l5_meta.get("avg_risk_pct", 0.0))

    st.markdown(
        f"#### 🛡️ **Layer 5 Risk Management & Position Sizing Order Sheet** &nbsp; "
        f"<span style='background:rgba(56,189,248,0.18); color:#38bdf8; padding:3px 10px; border-radius:12px; font-weight:700; font-size:0.88rem;'>"
        f"{len(df_l5)} Risk-Approved Orders · Equity ${eq:,.0f} · 1R Budget ${max_r_dlr:,.0f} · Avg Stop -{avg_r:.1f}%</span>",
        unsafe_allow_html=True,
    )

    df_sub = _render_common_search_and_sector_bar(
        df_l5,
        key_prefix="tab_l5",
        csv_filename=f"layer5_order_sheet_{sp500_bm.get('as_of_date', 'eod')}.csv",
    )

    if df_sub.empty:
        st.info("ℹ️ No setups passed Layer 5 Risk & Position Sizing filters. Increase Max Allowable Stop-Loss (%) or check Layer 3/4 filters.")
        return

    cols = [
        c for c in [
            "ticker", "company_name", "action_status_badge", "exit_plan_badge", "earnings_badge",
            "close", "pivot_price", "stop_loss_price", "risk_per_share", "risk_pct",
            "target_price", "target_gain_pct", "recommended_shares", "partial_shares",
            "runner_trail_ema21", "position_value", "portfolio_alloc_pct",
            "vcp_score", "composite_score", "tv_url"
        ] if c in df_sub.columns
    ]
    st.dataframe(
        df_sub[cols],
        use_container_width=True,
        height=440,
        hide_index=True,
        column_config={
            "ticker": st.column_config.TextColumn(f"Symbol ({len(df_sub)})", width="small"),
            "company_name": st.column_config.TextColumn("Company", width="medium"),
            "action_status_badge": st.column_config.TextColumn("Entry Status", width="medium"),
            "exit_plan_badge": st.column_config.TextColumn("JLaw Exit Plan", width="large"),
            "earnings_badge": st.column_config.TextColumn("ER Guard", width="small"),
            "close": st.column_config.NumberColumn("Price ($)", format="$%.2f"),
            "pivot_price": st.column_config.NumberColumn("Pivot ($)", format="$%.2f"),
            "stop_loss_price": st.column_config.NumberColumn("Stop ($)", format="$%.2f"),
            "risk_per_share": st.column_config.NumberColumn("1R ($/sh)", format="$%.2f"),
            "risk_pct": st.column_config.NumberColumn("1R Risk %", format="-%.2f%%"),
            "target_price": st.column_config.NumberColumn("Target ($)", format="$%.2f"),
            "target_gain_pct": st.column_config.NumberColumn("Target +%", format="+%.1f%%"),
            "recommended_shares": st.column_config.NumberColumn("Buy Shares", format="%d"),
            "partial_shares": st.column_config.NumberColumn("50% Scale Shares", format="%d"),
            "runner_trail_ema21": st.column_config.NumberColumn("21EMA Trail ($)", format="$%.2f"),
            "position_value": st.column_config.NumberColumn("Position ($)", format="$%.0f"),
            "portfolio_alloc_pct": st.column_config.NumberColumn("Alloc %", format="%.1f%%"),
            "vcp_score": st.column_config.ProgressColumn("VCP Score", format="%d", min_value=0, max_value=100),
            "composite_score": st.column_config.NumberColumn("L2 Score", format="%.1f", width="small"),
            "tv_url": st.column_config.LinkColumn("BKCHO Chart", display_text="Open in TV ↗"),
        },
    )


def render_watchlist_grid(
    df_scored: pd.DataFrame,
    summary_meta: Dict[str, Any],
    sp500_bm: Dict[str, Any],
) -> pd.DataFrame:
    """Backward-compatible wrapper returning Layer 3 VCP setups dataframe."""
    render_layer3_tab_results_with_chart(df_scored, summary_meta, sp500_bm)
    return df_scored
