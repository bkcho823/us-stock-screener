"""
Top Header Bar — Renders Application Title, Cloud DB Status Badge, Preset Auto-Apply Selector,
Save Preset Popover, BKCHO Chart Layout ID Popover, and Manual Refresh Data Button.
"""

from __future__ import annotations

from typing import Dict, Any

import streamlit as st

from src.config import extract_tv_layout_id
from src.infrastructure import (
    is_supabase_configured,
    load_all_presets,
    save_custom_preset,
    save_tv_layout_id,
)
from src.providers.eod_sync_service import refresh_daily_market_data
from src.ui.state_manager import apply_preset_to_state


def render_top_header(sp500_bm: Dict[str, Any]) -> None:
    """Renders Top Bar Row 1: Title, Preset Selector, Save Preset, BKCHO Chart Setup, and Refresh."""
    presets = load_all_presets()
    preset_names = list(presets.keys())
    l0 = st.session_state["layer0_cfg"]
    l1 = st.session_state["layer1_cfg"]

    top_c1, top_c2, top_c3, top_c4, top_c5, top_c6 = st.columns([2.4, 1.55, 1.85, 0.95, 1.15, 0.95])

    with top_c1:
        db_badge = "🟢 Supabase DB" if is_supabase_configured() else "🟡 Session RAM"
        st.markdown(
            f"### 📈 Stock Screener · <small>`{sp500_bm.get('as_of_date', 'EOD')}` ({db_badge})</small>",
            unsafe_allow_html=True,
        )

    with top_c2:
        # P2: JLaw Market Regime Traffic Light & Progressive Exposure Guide
        regime_code = str(sp500_bm.get("market_regime", "GREEN_POWER_TREND"))
        bm_sym = str(sp500_bm.get("symbol", "^GSPC"))
        bm_close = float(sp500_bm.get("last_close", 0.0))
        bm_ema21 = float(sp500_bm.get("ema_21", bm_close))
        bm_sma50 = float(sp500_bm.get("sma_50", bm_close))
        bm_dist21 = float(sp500_bm.get("dist_to_ema21_pct", 0.0))
        rec_exp = str(sp500_bm.get("recommended_exposure_str", "1.0%–2.0% Risk · Full Offense"))

        if regime_code == "GREEN_POWER_TREND":
            reg_pill_lbl = f"🟢 Regime: POWER TREND ({bm_dist21:+.1f}%)"
        elif regime_code == "YELLOW_PULLBACK":
            reg_pill_lbl = f"🟡 Regime: PULLBACK ({bm_dist21:+.1f}%)"
        else:
            reg_pill_lbl = f"🔴 Regime: DEFENSIVE ({bm_dist21:+.1f}%)"

        with st.popover(reg_pill_lbl, use_container_width=True):
            st.markdown(f"**🚦 JLaw Market Regime Traffic Light ({bm_sym})**")
            st.write(f"• **Status:** {sp500_bm.get('regime_badge', reg_pill_lbl)}")
            st.write(f"• **{bm_sym} Close:** `{bm_close:,.2f}` vs **21 EMA:** `{bm_ema21:,.2f}` (`{bm_dist21:+.2f}%`)")
            st.write(f"• **50 SMA:** `{bm_sma50:,.2f}` · **1M / 6M Perf:** `{sp500_bm.get('perf_1m_pct', 0):+.2f}%` / `{sp500_bm.get('perf_6m_pct', 0):+.2f}%`")
            st.info(f"🎯 **Progressive Exposure Guidance:** {rec_exp}")
            st.caption(
                "JLaw USIC Rule: Press full size & pyramid only when S&P 500 / QQQ is above a rising 21 EMA and recent breakouts hold gains."
            )

    with top_c3:
        def _on_preset_change() -> None:
            chosen = st.session_state["preset_selector_widget"]
            apply_preset_to_state(chosen, presets)

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

    with top_c4:
        with st.popover("💾 Save Preset", use_container_width=True):
            st.markdown("**Save Current Filter Pill Setup**")
            new_preset_name = st.text_input("Preset Name", placeholder="e.g. Above 200MA + 1+6M Per")
            if st.button("Save Preset Now", use_container_width=True, type="primary") and new_preset_name.strip():
                save_custom_preset(new_preset_name.strip(), "Custom user preset", l0, l1)
                st.session_state["active_preset_name"] = new_preset_name.strip()
                st.toast(f"Saved preset: {new_preset_name.strip()}", icon="💾")
                st.rerun()

    with top_c5:
        cur_layout = extract_tv_layout_id(st.session_state.get("tv_layout_id", ""))
        layout_btn_lbl = f"⚙️ BKCHO Chart ({cur_layout})" if cur_layout else "⚙️ Set BKCHO Chart URL"
        with st.popover(layout_btn_lbl, use_container_width=True):
            st.markdown("**Link Your Personal 'BKCHO Chart' Layout**")
            st.caption(
                "Paste the URL from your TradingView browser address bar when viewing **BKCHO Chart** "
                "(e.g. `https://www.tradingview.com/chart/AbCdEf12/`). Saved permanently to Supabase!"
            )
            raw_layout_in = st.text_input(
                "BKCHO Chart URL or Layout ID",
                value=st.session_state.get("tv_layout_id", ""),
                placeholder="https://www.tradingview.com/chart/XXXXXXXX/",
            )
            if st.button("Save BKCHO Chart Layout", use_container_width=True, type="primary"):
                extracted = extract_tv_layout_id(raw_layout_in)
                st.session_state["tv_layout_id"] = extracted
                save_tv_layout_id(extracted)
                st.toast(f"Saved BKCHO Chart Layout ID: {extracted or 'Default'}", icon="✅")
                st.rerun()

    with top_c6:
        if st.button("🔄 Refresh Data", use_container_width=True):
            prog = st.progress(0, text="Refreshing live market data...")
            df_universe, new_bm = refresh_daily_market_data(
                enrich_yf=True,
                max_symbols_for_yf=800,
                progress_callback=lambda p, msg: prog.progress(int(p * 100), text=msg),
            )
            st.session_state["cached_df_universe"] = df_universe
            st.session_state["cached_sp500_bm"] = new_bm
            prog.empty()
            st.rerun()
