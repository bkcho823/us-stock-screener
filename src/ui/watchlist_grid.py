"""
Watchlist Grid Component — Renders View Mode Radio Pills (L2 Leader-Tier / All Qualified / Near-Miss / Full Pool),
Sector Multiselect, Symbol Search, CSV Export, and the 235px Interactive DataFrame with Active Row Highlight,
Composite Score, and Industry Leaderboard Rank.
"""

from __future__ import annotations

from typing import Dict, Any

import pandas as pd
import streamlit as st

from src.config import build_tv_chart_url


def render_watchlist_grid(
    df_scored: pd.DataFrame,
    summary_meta: Dict[str, Any],
    sp500_bm: Dict[str, Any],
) -> pd.DataFrame:
    """
    Renders the Watchlist Toolbar + Compact Highlighted Watchlist Table (`height=235`)
    and returns the filtered `df_view` DataFrame for the bottom TradingView cockpit.
    """
    if df_scored.empty:
        st.warning(
            "No stocks passed your current Layer 0 Pre-Filter pills above. "
            "Click any top filter pill (e.g. Mkt cap or Vol) to loosen the threshold."
        )
        return pd.DataFrame()

    l0_cnt = summary_meta["layer0_count"]
    qual_cnt = summary_meta["qualified_count"]
    near_cnt = summary_meta["near_miss_count"]
    active_cnt = summary_meta["active_condition_count"]

    l2_meta = summary_meta.get("l2_meta", {})
    l2_qual_cnt = l2_meta.get("l2_qualified_count", qual_cnt)

    l3_meta = summary_meta.get("l3_meta", {})
    l3_qual_cnt = l3_meta.get("l3_qualified_count", l2_qual_cnt)

    tb1, tb2, tb3, tb4, tb5 = st.columns([2.8, 1.3, 1.2, 1.1, 0.6])
    with tb1:
        view_mode = st.radio(
            "Watchlist View Mode",
            options=[
                f"⚡ L3 VCP Setups [{l3_qual_cnt}]",
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

    if view_mode.startswith("⚡ L3 VCP Setups"):
        df_view = df_scored[df_scored.get("qualified_all", True) & df_scored.get("l2_qualified", True) & df_scored.get("l3_qualified", True)].copy()
    elif view_mode.startswith("🎯 L2 Leaders"):
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

    # Explicit multi-tier sorting to guarantee the overall strongest stock is placed at Row #0
    if not df_view.empty:
        if sort_mode.startswith("🥇 Overall Strongest"):
            # Primary: L2 Composite Score -> Secondary: VCP Score -> Tertiary: Stock RS -> Quaternary: % 52W High
            sort_cols = [c for c in ["composite_score", "vcp_score", "rs_percentile", "pct_of_52w_high", "perf_1m"] if c in df_view.columns]
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

    # Columns configuration including Layer 2 Composite Score & Industry Rank
    display_cols = [
        "ticker",
        "composite_score",
        "vcp_score",
        "vcp_badge",
        "rs_percentile",
        "group_rs_percentile",
        "industry_rank_str",
        "close",
        "vol_1d",
        "last_contraction_pct",
        "vol_dryup_pct",
        "market_cap_b",
        "perf_1m",
        "perf_6m",
        "pct_of_52w_high",
        "l2_badge",
        "diagnostic_badge",
        "tv_url",
    ]
    # Filter only columns present in df_view
    display_cols = [c for c in display_cols if c in df_view.columns]

    # Clamp active_row_idx within current filtered watchlist bounds
    if df_view.empty:
        st.session_state["active_row_idx"] = 0
    else:
        st.session_state["active_row_idx"] = max(
            0, min(int(st.session_state.get("active_row_idx", 0)), len(df_view) - 1)
        )

    # Sync if user clicked a row checkbox in the table on the previous render
    table_state = st.session_state.get("watchlist_df_widget")
    if table_state and isinstance(table_state, dict):
        cur_sel = table_state.get("selection", {}).get("rows", [])
        if cur_sel != st.session_state.get("last_table_sel", []):
            st.session_state["last_table_sel"] = cur_sel
            if cur_sel and 0 <= cur_sel[0] < len(df_view):
                st.session_state["active_row_idx"] = cur_sel[0]

    active_idx = int(st.session_state.get("active_row_idx", 0))

    # Add visual active pointer on Symbol column & highlight active row in cyan/blue
    df_table = df_view[display_cols].copy()
    if not df_table.empty and "ticker" in df_table.columns:
        df_table["ticker"] = [
            f"▶ {t}" if i == active_idx else f"   {t}"
            for i, t in enumerate(df_table["ticker"])
        ]

    def _highlight_active_row(row: pd.Series) -> list[str]:
        if row.name == active_idx:
            return [
                "background-color: rgba(56, 189, 248, 0.24); color: #ffffff; font-weight: 700;"
            ] * len(row)
        return [""] * len(row)

    styled_table = df_table.style.apply(_highlight_active_row, axis=1)

    st.dataframe(
        styled_table,
        key="watchlist_df_widget",
        use_container_width=True,
        height=235,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "ticker": st.column_config.TextColumn(f"Symbol ({len(df_view)})", width="small"),
            "composite_score": st.column_config.NumberColumn("L2 Score", format="%.1f", width="small"),
            "vcp_score": st.column_config.ProgressColumn("VCP Score", format="%d", min_value=0, max_value=100),
            "vcp_badge": st.column_config.TextColumn("VCP / EMA Structure", width="medium"),
            "rs_percentile": st.column_config.ProgressColumn("Stock RS", format="%d", min_value=1, max_value=99),
            "group_rs_percentile": st.column_config.NumberColumn("Ind RS", format="%d", width="small"),
            "industry_rank_str": st.column_config.TextColumn("Industry & Rank", width="medium"),
            "close": st.column_config.NumberColumn("Price", format="$%.2f"),
            "vol_1d": st.column_config.NumberColumn("Vol", format="%d"),
            "last_contraction_pct": st.column_config.NumberColumn("Tight %", format="%.1f%%"),
            "vol_dryup_pct": st.column_config.NumberColumn("Dry %", format="%.0f%%"),
            "market_cap_b": st.column_config.NumberColumn("Mkt cap", format="$%.2fB"),
            "perf_1m": st.column_config.NumberColumn("Perf 1M", format="%+.2f%%"),
            "perf_6m": st.column_config.NumberColumn("Perf 6M", format="%+.2f%%"),
            "pct_of_52w_high": st.column_config.ProgressColumn("% 52W High", format="%.1f%%", min_value=0, max_value=100),
            "l2_badge": st.column_config.TextColumn("L2 Industry Status", width="medium"),
            "diagnostic_badge": st.column_config.TextColumn("L1 Trend Rules", width="medium"),
            "tv_url": st.column_config.LinkColumn("BKCHO Chart", display_text="Open in TV ↗"),
        },
    )

    return df_view
