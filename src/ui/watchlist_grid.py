"""
Watchlist Grid Component — Renders two distinct, dedicated tables:
  1. Main Watchlist Table (Trend & Industry Strength: L2 Leaders / All Qualified / Near-Miss / Full Pool)
  2. Dedicated Layer 3 VCP Setups Table (Stocks fulfilling Minervini Volatility Contraction & JLaw EMA structure)
Provides bi-directional row selection, cyan active-row highlight, and returns the active DataFrame to the TradingView cockpit.
"""

from __future__ import annotations

from typing import Dict, Any, List

import pandas as pd
import streamlit as st

from src.config import build_tv_chart_url


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


def render_watchlist_grid(
    df_scored: pd.DataFrame,
    summary_meta: Dict[str, Any],
    sp500_bm: Dict[str, Any],
) -> pd.DataFrame:
    """
    Renders:
      1. Main Watchlist Toolbar & Table (L1 Trend & L2 Industry Leadership, height=225px)
      2. Dedicated Layer 3 VCP & EMA Setups Table (height=200px) placed immediately after Table 1.
    Returns the active DataFrame (`df_cockpit`) for the synchronized TradingView chart cockpit.
    """
    if df_scored.empty:
        st.warning(
            "No stocks passed your current Layer 0 Pre-Filter pills above. "
            "Click any top filter pill (e.g. Mkt cap or Vol) to loosen the threshold."
        )
        return pd.DataFrame()

    l0_cnt = summary_meta.get("layer0_count", len(df_scored))
    qual_cnt = summary_meta.get("qualified_count", 0)
    near_cnt = summary_meta.get("near_miss_count", 0)
    active_cnt = summary_meta.get("active_condition_count", 11)

    l2_meta = summary_meta.get("l2_meta", {})
    l2_qual_cnt = l2_meta.get("l2_qualified_count", qual_cnt)

    l3_meta = summary_meta.get("l3_meta", {})
    l3_qual_cnt = l3_meta.get("l3_qualified_count", 0)

    # -------------------------------------------------------------------------
    # 1. Main Watchlist Toolbar
    # -------------------------------------------------------------------------
    tb1, tb2, tb3, tb4, tb5 = st.columns([2.6, 1.4, 1.2, 1.1, 0.7])
    with tb1:
        view_mode = st.radio(
            "Watchlist View Mode",
            options=[
                f"🎯 L2 Leaders [{l2_qual_cnt}]",
                f"🏆 All L1 Qualified [{qual_cnt}]",
                f"🎯 Near-Miss [{near_cnt}]",
                f"🌐 Full Pool [{l0_cnt}]",
            ],
            horizontal=True,
            label_visibility="collapsed",
        )
    with tb2:
        sort_mode = st.selectbox(
            "Sort Order",
            options=[
                "🥇 Overall Strongest (L2 Score)",
                "⚡ Pure RS Rating (Stock RS)",
                "🏔️ Near 52W High (% of High)",
                "🚀 1M Momentum (Perf 1M)",
                "🏛️ Market Cap (Mega to Small)",
            ],
            index=0,
            label_visibility="collapsed",
            help="Determines which stock ranks at the top of the list and loads in the chart first.",
        )
    with tb3:
        all_sectors = sorted(df_scored["sector"].dropna().unique().tolist())
        selected_sectors = st.multiselect(
            "Filter by Sector",
            options=all_sectors,
            placeholder="All Sectors...",
            label_visibility="collapsed",
        )
    with tb4:
        search_query = st.text_input(
            "Search Ticker / Company",
            placeholder="🔍 Symbol / Company...",
            label_visibility="collapsed",
        )

    # Filter Main Watchlist Table (df_view)
    if view_mode.startswith("🎯 L2 Leaders"):
        df_view = df_scored[df_scored["qualified_all"] & df_scored.get("l2_qualified", True)].copy()
    elif view_mode.startswith("🏆 All L1 Qualified"):
        df_view = df_scored[df_scored["qualified_all"]].copy()
    elif view_mode.startswith("🎯 Near-Miss"):
        df_view = df_scored[df_scored["passed_count"] == max(0, active_cnt - 1)].copy()
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

    # Explicit multi-tier sorting for Table 1
    if not df_view.empty:
        if sort_mode.startswith("🥇 Overall Strongest"):
            sort_cols = [c for c in ["composite_score", "rs_percentile", "pct_of_52w_high", "perf_1m"] if c in df_view.columns]
            df_view = df_view.sort_values(by=sort_cols, ascending=[False] * len(sort_cols))
        elif sort_mode.startswith("⚡ Pure RS Rating"):
            sort_cols = [c for c in ["rs_percentile", "composite_score", "pct_of_52w_high", "perf_1m"] if c in df_view.columns]
            df_view = df_view.sort_values(by=sort_cols, ascending=[False] * len(sort_cols))
        elif sort_mode.startswith("🏔️ Near 52W High"):
            sort_cols = [c for c in ["pct_of_52w_high", "composite_score", "rs_percentile", "perf_1m"] if c in df_view.columns]
            df_view = df_view.sort_values(by=sort_cols, ascending=[False] * len(sort_cols))
        elif sort_mode.startswith("🚀 1M Momentum"):
            sort_cols = [c for c in ["perf_1m", "composite_score", "rs_percentile", "pct_of_52w_high"] if c in df_view.columns]
            df_view = df_view.sort_values(by=sort_cols, ascending=[False] * len(sort_cols))
        elif sort_mode.startswith("🏛️ Market Cap"):
            sort_cols = [c for c in ["market_cap_b", "composite_score", "rs_percentile"] if c in df_view.columns]
            df_view = df_view.sort_values(by=sort_cols, ascending=[False] * len(sort_cols))

    df_view = df_view.reset_index(drop=True)
    active_layout_id = st.session_state.get("tv_layout_id", "")
    df_view["tv_url"] = df_view.apply(
        lambda r: build_tv_chart_url(str(r["exchange"]), str(r["ticker"]), active_layout_id),
        axis=1,
    )

    with tb5:
        csv_bytes = df_view.to_csv(index=False).encode("utf-8")
        st.download_button(
            label=f"⬇️ CSV ({len(df_view)})",
            data=csv_bytes,
            file_name=f"watchlist_{sp500_bm.get('as_of_date', 'eod')}.csv",
            mime="text/csv",
            use_container_width=True,
        )

    # -------------------------------------------------------------------------
    # 2. Extract Dedicated Layer 3 VCP Setups (Stocks fulfilling L3 criteria)
    # -------------------------------------------------------------------------
    df_l3 = df_scored[
        df_scored.get("qualified_all", True)
        & df_scored.get("l2_qualified", True)
        & df_scored.get("l3_qualified", True)
    ].copy()

    if selected_sectors and not df_l3.empty:
        df_l3 = df_l3[df_l3["sector"].isin(selected_sectors)]
    if search_query.strip() and not df_l3.empty:
        q = search_query.strip().lower()
        df_l3 = df_l3[
            df_l3["ticker"].str.lower().str.contains(q)
            | df_l3["company_name"].fillna("").str.lower().str.contains(q)
        ]

    # Sort Layer 3 setups: Highest VCP Tightness Score first, then lowest contraction range
    if not df_l3.empty:
        l3_sort_cols = [c for c in ["vcp_score", "composite_score", "rs_percentile"] if c in df_l3.columns]
        df_l3 = df_l3.sort_values(
            by=l3_sort_cols + (["last_contraction_pct"] if "last_contraction_pct" in df_l3.columns else []),
            ascending=[False] * len(l3_sort_cols) + [True],
        ).reset_index(drop=True)
        df_l3["tv_url"] = df_l3.apply(
            lambda r: build_tv_chart_url(str(r["exchange"]), str(r["ticker"]), active_layout_id),
            axis=1,
        )

    # -------------------------------------------------------------------------
    # 3. Handle Row Selection Across Both Tables
    # -------------------------------------------------------------------------
    t1_state = st.session_state.get("watchlist_df_widget")
    if t1_state and isinstance(t1_state, dict):
        cur_sel = t1_state.get("selection", {}).get("rows", [])
        if cur_sel and cur_sel != st.session_state.get("last_table_sel", []):
            st.session_state["last_table_sel"] = cur_sel
            if 0 <= cur_sel[0] < len(df_view):
                st.session_state["selected_ticker"] = df_view.iloc[cur_sel[0]]["ticker"]
                st.session_state["active_table_source"] = "table1"
                st.session_state["last_l3_sel"] = []

    t2_state = st.session_state.get("l3_df_widget")
    if t2_state and isinstance(t2_state, dict):
        cur_l3_sel = t2_state.get("selection", {}).get("rows", [])
        if cur_l3_sel and cur_l3_sel != st.session_state.get("last_l3_sel", []):
            st.session_state["last_l3_sel"] = cur_l3_sel
            if 0 <= cur_l3_sel[0] < len(df_l3):
                st.session_state["selected_ticker"] = df_l3.iloc[cur_l3_sel[0]]["ticker"]
                st.session_state["active_table_source"] = "table2"
                st.session_state["last_table_sel"] = []

    # Default selected ticker if not yet set
    selected_ticker = st.session_state.get("selected_ticker", "")
    active_source = st.session_state.get("active_table_source", "table2" if not df_l3.empty else "table1")

    if not selected_ticker:
        if not df_l3.empty:
            selected_ticker = str(df_l3.iloc[0]["ticker"])
            active_source = "table2"
        elif not df_view.empty:
            selected_ticker = str(df_view.iloc[0]["ticker"])
            active_source = "table1"
        st.session_state["selected_ticker"] = selected_ticker
        st.session_state["active_table_source"] = active_source

    # -------------------------------------------------------------------------
    # 4. Render Table 1: Main Watchlist (Trend & Industry Strength)
    # -------------------------------------------------------------------------
    t1_cols = [
        "ticker",
        "composite_score",
        "l2_badge",
        "rs_percentile",
        "group_rs_percentile",
        "industry_rank_str",
        "close",
        "vol_1d",
        "market_cap_b",
        "perf_1m",
        "perf_6m",
        "pct_of_52w_high",
        "diagnostic_badge",
        "tv_url",
    ]
    t1_cols = [c for c in t1_cols if c in df_view.columns]

    styler_t1 = _style_table_with_active_row(
        df_view,
        selected_ticker if active_source == "table1" else "",
        t1_cols,
    )

    st.dataframe(
        styler_t1,
        key="watchlist_df_widget",
        use_container_width=True,
        height=225,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "ticker": st.column_config.TextColumn(f"Symbol ({len(df_view)})", width="small"),
            "composite_score": st.column_config.NumberColumn("L2 Score", format="%.1f", width="small"),
            "l2_badge": st.column_config.TextColumn("L2 Industry Status", width="medium"),
            "rs_percentile": st.column_config.ProgressColumn("Stock RS", format="%d", min_value=1, max_value=99),
            "group_rs_percentile": st.column_config.NumberColumn("Ind RS", format="%d", width="small"),
            "industry_rank_str": st.column_config.TextColumn("Industry & Rank", width="medium"),
            "close": st.column_config.NumberColumn("Price", format="$%.2f"),
            "vol_1d": st.column_config.NumberColumn("Vol", format="%d"),
            "market_cap_b": st.column_config.NumberColumn("Mkt cap", format="$%.2fB"),
            "perf_1m": st.column_config.NumberColumn("Perf 1M", format="%+.2f%%"),
            "perf_6m": st.column_config.NumberColumn("Perf 6M", format="%+.2f%%"),
            "pct_of_52w_high": st.column_config.ProgressColumn("% 52W High", format="%.1f%%", min_value=0, max_value=100),
            "diagnostic_badge": st.column_config.TextColumn("L1 Trend Rules", width="medium"),
            "tv_url": st.column_config.LinkColumn("BKCHO Chart", display_text="Open in TV ↗"),
        },
    )

    # -------------------------------------------------------------------------
    # 5. Render Table 2: Dedicated Layer 3 Minervini VCP & JLaw EMA Setups Table
    # -------------------------------------------------------------------------
    st.markdown("---")
    l3_hdr1, l3_hdr2 = st.columns([3.8, 1.2])
    with l3_hdr1:
        st.markdown(
            f"#### ⚡ **Layer 3: Minervini VCP & JLaw EMA Setups** &nbsp; "
            f"<span style='background:rgba(56,189,248,0.18); color:#38bdf8; padding:3px 10px; border-radius:12px; font-weight:700; font-size:0.88rem;'>"
            f"{len(df_l3)} Setups Fulfilled</span>",
            unsafe_allow_html=True,
        )
        st.caption(
            "Stocks meeting strict Volatility Contraction (≤8%), supply exhaustion volume dry-up (≤65%), and 21/50 EMA structural alignment."
        )
    with l3_hdr2:
        if not df_l3.empty:
            csv_l3_bytes = df_l3.to_csv(index=False).encode("utf-8")
            st.download_button(
                label=f"⬇️ CSV L3 Setups ({len(df_l3)})",
                data=csv_l3_bytes,
                file_name=f"l3_vcp_setups_{sp500_bm.get('as_of_date', 'eod')}.csv",
                mime="text/csv",
                use_container_width=True,
                key="dl_l3_setups_csv",
            )

    if df_l3.empty:
        st.info(
            "ℹ️ No stocks currently fulfill strict Layer 3 VCP criteria with your active thresholds. "
            "Use the Layer 3 filter pills in the top bar above to relax the Max Contraction (≤8%) or Volume Dry-Up (≤65%) thresholds."
        )
    else:
        t2_cols = [
            "ticker",
            "vcp_score",
            "vcp_badge",
            "last_contraction_pct",
            "vol_dryup_pct",
            "dist_to_ema21_pct",
            "close",
            "composite_score",
            "rs_percentile",
            "group_rs_percentile",
            "industry_rank_str",
            "perf_1m",
            "pct_of_52w_high",
            "tv_url",
        ]
        t2_cols = [c for c in t2_cols if c in df_l3.columns]

        styler_t2 = _style_table_with_active_row(
            df_l3,
            selected_ticker if active_source == "table2" else "",
            t2_cols,
        )

        st.dataframe(
            styler_t2,
            key="l3_df_widget",
            use_container_width=True,
            height=200,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            column_config={
                "ticker": st.column_config.TextColumn(f"Symbol ({len(df_l3)})", width="small"),
                "vcp_score": st.column_config.ProgressColumn("VCP Score", format="%d", min_value=0, max_value=100),
                "vcp_badge": st.column_config.TextColumn("VCP / EMA Structure", width="medium"),
                "last_contraction_pct": st.column_config.NumberColumn("Tight %", format="%.1f%%"),
                "vol_dryup_pct": st.column_config.NumberColumn("Dry %", format="%.0f%%"),
                "dist_to_ema21_pct": st.column_config.NumberColumn("21 EMA Dist", format="%+.1f%%"),
                "close": st.column_config.NumberColumn("Price", format="$%.2f"),
                "composite_score": st.column_config.NumberColumn("L2 Score", format="%.1f", width="small"),
                "rs_percentile": st.column_config.ProgressColumn("Stock RS", format="%d", min_value=1, max_value=99),
                "group_rs_percentile": st.column_config.NumberColumn("Ind RS", format="%d", width="small"),
                "industry_rank_str": st.column_config.TextColumn("Industry & Rank", width="medium"),
                "perf_1m": st.column_config.NumberColumn("Perf 1M", format="%+.2f%%"),
                "pct_of_52w_high": st.column_config.ProgressColumn("% 52W High", format="%.1f%%", min_value=0, max_value=100),
                "tv_url": st.column_config.LinkColumn("BKCHO Chart", display_text="Open in TV ↗"),
            },
        )

    # -------------------------------------------------------------------------
    # 6. Synchronize Cockpit Selection and Return Active DataFrame
    # -------------------------------------------------------------------------
    if active_source == "table2" and not df_l3.empty:
        df_cockpit = df_l3
    else:
        df_cockpit = df_view

    if not df_cockpit.empty:
        matching_rows = df_cockpit.index[df_cockpit["ticker"] == selected_ticker].tolist()
        if matching_rows:
            st.session_state["active_row_idx"] = matching_rows[0]
        else:
            cur_idx = int(st.session_state.get("active_row_idx", 0))
            clamped_idx = max(0, min(cur_idx, len(df_cockpit) - 1))
            st.session_state["active_row_idx"] = clamped_idx
            st.session_state["selected_ticker"] = str(df_cockpit.iloc[clamped_idx]["ticker"])

    return df_cockpit
