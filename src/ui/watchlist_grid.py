"""
Watchlist Grid Component — Renders View Mode Radio Pills (Qualified / Near-Miss / Broad / Full Layer 0),
Sector Multiselect, Symbol Search, CSV Export, and the 235px Interactive DataFrame with Active Row Highlight.
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
    active_layout_id = st.session_state.get("tv_layout_id", "")
    df_view["tv_url"] = df_view.apply(
        lambda r: build_tv_chart_url(str(r["exchange"]), str(r["ticker"]), active_layout_id),
        axis=1,
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
    if not df_table.empty:
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
            "tv_url": st.column_config.LinkColumn("BKCHO Chart", display_text="Open in TV ↗"),
        },
    )

    return df_view
