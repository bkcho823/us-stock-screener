"""
TradingView Chart Cockpit — Renders the Bottom Live Embedded TradingView Advanced Chart Widget
(`s3.tradingview.com/tv.js`), Prev/Next Navigation Bar, Global `PageUp`/`PageDown`/`Space`
Keyboard Shortcut Listener, and Direct 'Open in BKCHO Chart ↗' Link Button.
"""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from src.config import build_tv_chart_url, extract_tv_layout_id


def _render_tradingview_advanced_chart(exchange: str, ticker: str, height: int = 500) -> None:
    """
    Renders the official live interactive TradingView Advanced Chart Widget (`s3.tradingview.com/tv.js`)
    with Daily interval, Drawing Toolbar enabled, Volume, and SMAs 10/20/50/150/200 pre-loaded.
    """
    tv_symbol = f"{exchange}:{ticker}"
    widget_config = {
        "autosize": True,
        "symbol": tv_symbol,
        "interval": "D",
        "timezone": "Etc/UTC",
        "theme": "dark",
        "style": "1",
        "locale": "en",
        "enable_publishing": False,
        "allow_symbol_change": True,
        "hide_side_toolbar": False,
        "withdateranges": True,
        "details": False,
        "hotlist": False,
        "calendar": False,
        "studies": [
            {"id": "MASimple@tv-basicstudies", "inputs": {"length": 10}},
            {"id": "MASimple@tv-basicstudies", "inputs": {"length": 20}},
            {"id": "MASimple@tv-basicstudies", "inputs": {"length": 50}},
            {"id": "MASimple@tv-basicstudies", "inputs": {"length": 150}},
            {"id": "MASimple@tv-basicstudies", "inputs": {"length": 200}},
        ],
        "container_id": "tv_advanced_chart_container",
    }

    html_code = f"""
    <div class="tradingview-widget-container" style="height:{height}px;width:100%;">
      <div id="tv_advanced_chart_container" style="height:{height - 10}px;width:100%;"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
      new TradingView.widget({json.dumps(widget_config)});
      </script>
    </div>
    """
    components.html(html_code, height=height)


def _inject_keyboard_row_navigation() -> None:
    """
    Binds global keyboard shortcuts on the parent Streamlit document:
    - PageUp   -> Clicks the '◀ Prev' button (moves highlight & chart up 1 row)
    - PageDown -> Clicks the 'Next ▶' button (moves highlight & chart down 1 row)
    - Spacebar -> Clicks the 'Next ▶' button (unless typing inside an input/textarea)
    """
    js_code = """
    <script>
    (function() {
        const parentDoc = window.parent.document;
        if (parentDoc.__usStockKeyNavBound) return;
        parentDoc.__usStockKeyNavBound = true;

        parentDoc.addEventListener('keydown', function(e) {
            const tag = (e.target && e.target.tagName) ? e.target.tagName.toUpperCase() : '';
            const isEditable = (
                tag === 'INPUT' ||
                tag === 'TEXTAREA' ||
                tag === 'SELECT' ||
                (e.target && e.target.isContentEditable)
            );
            if (isEditable) return;

            if (e.key === 'PageDown' || e.code === 'Space' || e.key === ' ') {
                const buttons = Array.from(parentDoc.querySelectorAll('button'));
                const nextBtn = buttons.find(b => b.innerText && b.innerText.includes('Next ▶'));
                if (nextBtn && !nextBtn.disabled) {
                    e.preventDefault();
                    e.stopPropagation();
                    nextBtn.click();
                }
            } else if (e.key === 'PageUp') {
                const buttons = Array.from(parentDoc.querySelectorAll('button'));
                const prevBtn = buttons.find(b => b.innerText && b.innerText.includes('◀ Prev'));
                if (prevBtn && !prevBtn.disabled) {
                    e.preventDefault();
                    e.stopPropagation();
                    prevBtn.click();
                }
            }
        }, true);
    })();
    </script>
    """
    components.html(js_code, height=0, width=0)


def render_tradingview_cockpit(df_view: pd.DataFrame) -> None:
    """Renders the active stock navigation header, keyboard shortcuts, and embedded TradingView widget."""
    if df_view is None or df_view.empty:
        return

    active_idx = int(st.session_state.get("active_row_idx", 0))
    active_idx = max(0, min(active_idx, len(df_view) - 1))
    active_layout_id = st.session_state.get("tv_layout_id", "")

    inspected_row = df_view.iloc[active_idx]
    sel_ticker = str(inspected_row["ticker"])
    sel_name = str(inspected_row.get("company_name", ""))
    sel_exch = str(inspected_row.get("exchange", "NASDAQ"))
    tv_link = build_tv_chart_url(sel_exch, sel_ticker, active_layout_id)

    pass_sum = inspected_row.get("pass_summary", "")
    diag_b = inspected_row.get("diagnostic_badge", "")
    vcp_b = inspected_row.get("vcp_badge", "")
    act_b = inspected_row.get("action_status_badge", "")
    risk_b = inspected_row.get("risk_badge", "")
    badges = [f"`{b}`" for b in [act_b, risk_b, pass_sum, diag_b, vcp_b] if b]
    badge_str = f"({' · '.join(badges)})" if badges else ""

    dr_hdr1, nav_prev_col, nav_next_col, dr_hdr2 = st.columns([2.9, 0.65, 0.85, 1.25])
    with dr_hdr1:
        st.markdown(
            f"#### 📈 **[{active_idx + 1}/{len(df_view)}] {sel_exch}:{sel_ticker}** — {sel_name} {badge_str}"
        )
    with nav_prev_col:
        if st.button(
            "◀ Prev (PgUp)",
            disabled=(active_idx <= 0),
            use_container_width=True,
            help="Shortcut: Press PageUp key",
        ):
            st.session_state["active_row_idx"] = max(0, active_idx - 1)
            st.rerun()
    with nav_next_col:
        if st.button(
            "Next ▶ (PgDn/Space)",
            disabled=(active_idx >= len(df_view) - 1),
            use_container_width=True,
            help="Shortcut: Press PageDown or Spacebar",
        ):
            st.session_state["active_row_idx"] = min(len(df_view) - 1, active_idx + 1)
            st.rerun()
    with dr_hdr2:
        btn_label = (
            f"📈 Open {sel_ticker} in BKCHO Chart ↗"
            if extract_tv_layout_id(active_layout_id)
            else f"📈 Open {sel_ticker} in TradingView ↗"
        )
        st.link_button(
            btn_label,
            url=tv_link,
            use_container_width=True,
        )

    _inject_keyboard_row_navigation()
    _render_tradingview_advanced_chart(sel_exch, sel_ticker, height=500)
