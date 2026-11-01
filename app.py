"""
Step 5 (TradingView Top-Pill Architecture + Live Embedded TradingView Advanced Chart + Supabase Cloud DB)
US Short/Mid-Term Breakout Stock Scoring & Ranking System — Layer 0 + Layer 1
Features:
- Zero Left Sidebar! 100% of filtering criteria placed at the TOP of the page as interactive TradingView-style filter pills (`st.popover`)
- Row 1: Preset Dropdown + Action Buttons (Save Preset, BKCHO Chart Layout ID Setting, Refresh Data)
- Row 2 (Layer 0 Pills): US Market/Exchanges | Price >= $10 | Mkt Cap >= $3B | Vol 1D > 500K | Avg Vol 10D/30D/60D/90D > 500K | Price × Vol > $50M
- Row 3 (Layer 1 Pills): C1..C8 Minervini Trend Template Pills | C9 SMA10 >= SMA20 | C10 1M Perf > Y% | C11 6M Perf > Y%
- Compact Watchlist Table (235px height)
- Live Embedded TradingView Advanced Real-Time Chart Widget (`s3.tradingview.com/tv.js`) at the bottom + "Open in BKCHO Chart ↗" button
"""

from __future__ import annotations

import json
import re
import time
from typing import Dict, Any

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from src.config import (
    ALL_EXCHANGES,
    BUILTIN_PRESETS,
    DEFAULT_TV_LAYOUT_ID,
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
)
from src.storage import (
    load_all_presets,
    save_custom_preset,
)
from src.supabase_client import (
    is_supabase_configured,
    sb_get_kv,
    sb_upsert_kv,
)

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
    /* Make top Streamlit header bar transparent and give top row safe clearance */
    header[data-testid="stHeader"] {
        background: transparent !important;
        height: 2.5rem !important;
    }
    .block-container {
        padding-top: 3.2rem !important;
        padding-bottom: 1.5rem !important;
        max-width: 98% !important;
    }
    /* Style st.popover buttons to look like TradingView Filter Pills (prevent text truncation) */
    div[data-testid="stPopover"] > div > button {
        border-radius: 8px !important;
        padding: 0.2rem 0.5rem !important;
        min-height: 2.15rem !important;
        font-size: 0.78rem !important;
        font-weight: 600 !important;
        white-space: nowrap !important;
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
        margin: 4px 0 8px 0;
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


def _extract_tv_layout_id(raw_input: str) -> str:
    """
    Extracts the TradingView Layout ID from either a full URL like:
    `https://www.tradingview.com/chart/AbCdEf12/?symbol=NASDAQ:BEAM`
    or a bare layout ID like `AbCdEf12`.
    """
    s = (raw_input or "").strip()
    if not s:
        return ""
    m = re.search(r"tradingview\.com/chart/([A-Za-z0-9_\-]+)", s)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_\-]{4,20}", s):
        return s
    return ""


def _build_tv_chart_url(exchange: str, ticker: str, layout_id: str) -> str:
    clean_id = _extract_tv_layout_id(layout_id)
    sym_param = f"{exchange}%3A{ticker}"
    if clean_id:
        return f"https://www.tradingview.com/chart/{clean_id}/?symbol={sym_param}"
    return f"https://www.tradingview.com/chart/?symbol={sym_param}"


def _render_tradingview_advanced_chart(exchange: str, ticker: str, height: int = 500) -> None:
    """
    Renders the official live interactive TradingView Advanced Chart Widget (`s3.tradingview.com/tv.js`)
    with Daily interval, Drawing Toolbar enabled, Volume, and Moving Averages pre-loaded.
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
            {
                "id": "MASimple@tv-basicstudies",
                "inputs": {"length": 10},
            },
            {
                "id": "MASimple@tv-basicstudies",
                "inputs": {"length": 20},
            },
            {
                "id": "MASimple@tv-basicstudies",
                "inputs": {"length": 50},
            },
            {
                "id": "MASimple@tv-basicstudies",
                "inputs": {"length": 150},
            },
            {
                "id": "MASimple@tv-basicstudies",
                "inputs": {"length": 200},
            },
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
    - PageUp       -> Clicks the '◀ Prev' button (moves highlight & chart up 1 row)
    - PageDown     -> Clicks the 'Next ▶' button (moves highlight & chart down 1 row)
    - Spacebar     -> Clicks the 'Next ▶' button (unless typing inside an input/textarea)
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


def _init_session_state() -> None:
    if "layer0_cfg" not in st.session_state:
        st.session_state["layer0_cfg"] = get_default_layer0_config()
    if "layer1_cfg" not in st.session_state:
        st.session_state["layer1_cfg"] = get_default_layer1_config()
    if "active_preset_name" not in st.session_state:
        st.session_state["active_preset_name"] = list(BUILTIN_PRESETS.keys())[0]
    if "active_row_idx" not in st.session_state:
        st.session_state["active_row_idx"] = 0
    if "last_table_sel" not in st.session_state:
        st.session_state["last_table_sel"] = []
    if "tv_layout_id" not in st.session_state:
        saved_layout = DEFAULT_TV_LAYOUT_ID
        if not saved_layout and is_supabase_configured():
            try:
                val = sb_get_kv("tv_layout_id")
                if isinstance(val, str):
                    saved_layout = val
                elif isinstance(val, dict) and "layout_id" in val:
                    saved_layout = str(val["layout_id"])
            except Exception:
                pass
        st.session_state["tv_layout_id"] = saved_layout


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
    top_c1, top_c2, top_c3, top_c4, top_c5 = st.columns([2.9, 2.3, 1.1, 1.35, 1.1])
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
        cur_layout = _extract_tv_layout_id(st.session_state.get("tv_layout_id", ""))
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
                extracted = _extract_tv_layout_id(raw_layout_in)
                st.session_state["tv_layout_id"] = extracted
                if is_supabase_configured():
                    try:
                        sb_upsert_kv("tv_layout_id", {"layout_id": extracted})
                    except Exception:
                        pass
                st.toast(f"Saved BKCHO Chart Layout ID: {extracted or 'Default'}", icon="✅")
                st.rerun()
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
    # TOP FILTER PILLS — 100% OF LAYER 0 (11 PILLS) & LAYER 1 (11 PILLS) VISIBLE
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

    # --- ROW 1 (6 Wide Layer 0 Pills: Exchanges, ETFs, ADRs, Price, Mkt Cap, Dollar Vol) ---
    l0_r1 = st.columns(6)
    with l0_r1[0]:
        ex_list = l0.get("exchanges", ALL_EXCHANGES)
        ex_lbl = "🇺🇸 US (NYSE/NASD/AMEX)" if len(ex_list) == 3 else f"🇺🇸 Exchanges ({len(ex_list)})"
        with st.popover(ex_lbl, use_container_width=True):
            l0["exchanges"] = st.multiselect(
                "US Exchanges",
                options=ALL_EXCHANGES,
                default=ex_list,
            )
    with l0_r1[1]:
        etf_lbl = "✅ Exclude ETFs: ON" if l0.get("exclude_etfs", True) else "⚪ Exclude ETFs: OFF"
        with st.popover(etf_lbl, use_container_width=True):
            l0["exclude_etfs"] = st.toggle("Exclude ETFs / Funds", value=bool(l0.get("exclude_etfs", True)))
    with l0_r1[2]:
        adr_lbl = "✅ Include ADRs: ON" if l0.get("include_adrs", True) else "⚪ Include ADRs: OFF"
        with st.popover(adr_lbl, use_container_width=True):
            l0["include_adrs"] = st.toggle("Include Foreign ADRs", value=bool(l0.get("include_adrs", True)))
    with l0_r1[3]:
        with st.popover(f"Price ≥ ${l0['min_price']:.0f} USD", use_container_width=True):
            l0["min_price"] = st.number_input(
                "Minimum Share Price (USD)",
                min_value=1.0,
                max_value=1000.0,
                value=float(l0.get("min_price", 10.0)),
                step=1.0,
            )
    with l0_r1[4]:
        mc_label = (
            f"Mkt cap ≥ ${l0['min_market_cap_b']:g}B"
            if float(l0.get("max_market_cap_b", 0.0)) <= 0
            else f"Mkt cap ${l0['min_market_cap_b']:g}B–${l0['max_market_cap_b']:g}B"
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
    with l0_r1[5]:
        with st.popover(f"Price × Vol > ${l0['min_dollar_vol_m']:g}M", use_container_width=True):
            l0["min_dollar_vol_m"] = st.number_input(
                "Min Daily Dollar Volume ($ Millions)",
                min_value=0.0,
                max_value=1000.0,
                value=float(l0.get("min_dollar_vol_m", 50.0)),
                step=5.0,
            )

    # --- ROW 2 (5 Wide Layer 0 Volume Pills: 1D, 10D, 30D, 60D, 90D) ---
    l0_r2 = st.columns(5)
    with l0_r2[0]:
        with st.popover(f"Vol (1D) > {_fmt_vol(l0['min_vol_1d'])}", use_container_width=True):
            l0["min_vol_1d"] = st.number_input(
                "Current Day Volume (1D Shares)",
                min_value=0,
                max_value=50_000_000,
                value=int(l0.get("min_vol_1d", 500_000)),
                step=50_000,
            )
            if st.button("Apply to all 10D/30D/60D/90D", use_container_width=True):
                v = int(l0["min_vol_1d"])
                l0["min_vol_10d"] = l0["min_vol_30d"] = l0["min_vol_60d"] = l0["min_vol_90d"] = v
                st.rerun()
    with l0_r2[1]:
        with st.popover(f"Avg Vol 10D > {_fmt_vol(l0['min_vol_10d'])}", use_container_width=True):
            l0["min_vol_10d"] = st.number_input(
                "10-Day Average Volume (Shares)",
                min_value=0,
                max_value=50_000_000,
                value=int(l0.get("min_vol_10d", 500_000)),
                step=50_000,
            )
    with l0_r2[2]:
        with st.popover(f"Avg Vol 30D > {_fmt_vol(l0['min_vol_30d'])}", use_container_width=True):
            l0["min_vol_30d"] = st.number_input(
                "30-Day Average Volume (Shares)",
                min_value=0,
                max_value=50_000_000,
                value=int(l0.get("min_vol_30d", 500_000)),
                step=50_000,
            )
    with l0_r2[3]:
        with st.popover(f"Avg Vol 60D > {_fmt_vol(l0['min_vol_60d'])}", use_container_width=True):
            l0["min_vol_60d"] = st.number_input(
                "60-Day Average Volume (Shares)",
                min_value=0,
                max_value=50_000_000,
                value=int(l0.get("min_vol_60d", 500_000)),
                step=50_000,
            )
    with l0_r2[4]:
        with st.popover(f"Avg Vol 90D > {_fmt_vol(l0['min_vol_90d'])}", use_container_width=True):
            l0["min_vol_90d"] = st.number_input(
                "90-Day Average Volume (Shares)",
                min_value=0,
                max_value=50_000_000,
                value=int(l0.get("min_vol_90d", 500_000)),
                step=50_000,
            )

    # --- ROW 3 (6 Wide Layer 1 Trend Pills: C1, C2, C3, C4, C5, C9) ---
    l1_r1 = st.columns(6)
    with l1_r1[0]:
        p_c1 = "✅ C1: P > SMA150/200" if l1["c1_enabled"] else "⚪ C1: P > SMA150/200"
        with st.popover(p_c1, use_container_width=True):
            l1["c1_enabled"] = st.toggle("Enable C1: Price > SMA 150 & SMA 200", value=bool(l1.get("c1_enabled", True)))
    with l1_r1[1]:
        p_c2 = "✅ C2: SMA150 > 200" if l1["c2_enabled"] else "⚪ C2: SMA150 > 200"
        with st.popover(p_c2, use_container_width=True):
            l1["c2_enabled"] = st.toggle("Enable C2: SMA 150 > SMA 200", value=bool(l1.get("c2_enabled", True)))
    with l1_r1[2]:
        p_c3 = f"✅ C3: SMA200 ↑ ({l1['c3_lookback_days']}D)" if l1["c3_enabled"] else "⚪ C3: SMA200 ↑ (OFF)"
        with st.popover(p_c3, use_container_width=True):
            l1["c3_enabled"] = st.toggle("Enable C3: SMA 200 Trending Upward", value=bool(l1.get("c3_enabled", True)))
            l1["c3_lookback_days"] = st.select_slider(
                "Lookback Trading Days (N)",
                options=[5, 10, 15, 20, 30, 40, 60],
                value=int(l1.get("c3_lookback_days", 20))
                if int(l1.get("c3_lookback_days", 20)) in [5, 10, 15, 20, 30, 40, 60]
                else 20,
            )
    with l1_r1[3]:
        p_c4 = "✅ C4: 50 > 150 > 200" if l1["c4_enabled"] else "⚪ C4: 50 > 150 > 200"
        with st.popover(p_c4, use_container_width=True):
            l1["c4_enabled"] = st.toggle("Enable C4: SMA 50 > SMA 150 > SMA 200", value=bool(l1.get("c4_enabled", True)))
    with l1_r1[4]:
        p_c5 = "✅ C5: Price > SMA50" if l1["c5_enabled"] else "⚪ C5: Price > SMA50"
        with st.popover(p_c5, use_container_width=True):
            l1["c5_enabled"] = st.toggle("Enable C5: Price > SMA 50", value=bool(l1.get("c5_enabled", True)))
    with l1_r1[5]:
        p_c9 = "✅ C9: SMA10 ≥ SMA20" if l1["c9_enabled"] else "⚪ C9: SMA10 ≥ SMA20"
        with st.popover(p_c9, use_container_width=True):
            l1["c9_enabled"] = st.toggle("Enable C9: Short-Term Alignment (SMA 10 ≥ SMA 20)", value=bool(l1.get("c9_enabled", True)))

    # --- ROW 4 (5 Wide Layer 1 Momentum & 52W Pills: C6, C7, C8, C10, C11) ---
    l1_r2 = st.columns(5)
    with l1_r2[0]:
        p_c6 = f"✅ C6: 52W Low +{l1['c6_min_pct_above_52w_low']:g}%" if l1["c6_enabled"] else "⚪ C6: 52W Low (OFF)"
        with st.popover(p_c6, use_container_width=True):
            l1["c6_enabled"] = st.toggle("Enable C6: Price Cleared 52-Week Low", value=bool(l1.get("c6_enabled", True)))
            l1["c6_min_pct_above_52w_low"] = st.number_input(
                "Min % Above 52-Week Low",
                min_value=0.0,
                max_value=300.0,
                value=float(l1.get("c6_min_pct_above_52w_low", 30.0)),
                step=5.0,
            )
    with l1_r2[1]:
        p_c7 = f"✅ C7: 52W High -{l1['c7_max_pct_below_52w_high']:g}%" if l1["c7_enabled"] else "⚪ C7: 52W High (OFF)"
        with st.popover(p_c7, use_container_width=True):
            l1["c7_enabled"] = st.toggle("Enable C7: Price Near 52-Week High", value=bool(l1.get("c7_enabled", True)))
            l1["c7_max_pct_below_52w_high"] = st.number_input(
                "Max % Below 52-Week High",
                min_value=1.0,
                max_value=80.0,
                value=float(l1.get("c7_max_pct_below_52w_high", 25.0)),
                step=5.0,
            )
    with l1_r2[2]:
        p_c8 = f"✅ C8: RS Rating ≥ {l1['c8_min_rs_percentile']}" if l1["c8_enabled"] else "⚪ C8: RS Rating (OFF)"
        with st.popover(p_c8, use_container_width=True):
            l1["c8_enabled"] = st.toggle("Enable C8: Relative Strength Percentile", value=bool(l1.get("c8_enabled", True)))
            l1["c8_min_rs_percentile"] = st.slider(
                "Minimum RS Percentile (1-99)",
                min_value=1,
                max_value=99,
                value=int(l1.get("c8_min_rs_percentile", 70)),
            )
    with l1_r2[3]:
        p_c10 = f"✅ C10: Perf 1M > {y_1m_preview:+.1f}%" if l1["c10_enabled"] else "⚪ C10: Perf 1M (OFF)"
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
    with l1_r2[4]:
        p_c11 = f"✅ C11: Perf 6M > {y_6m_preview:+.1f}%" if l1["c11_enabled"] else "⚪ C11: Perf 6M (OFF)"
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

    # =========================================================================
    # EXECUTE INSTANT SCREENING (<1 SECOND)
    # =========================================================================
    df_l0 = apply_layer0_filter(df_universe, st.session_state["layer0_cfg"])
    df_scored, summary_meta = evaluate_layer1_conditions(
        df_l0, st.session_state["layer1_cfg"], sp500_bm
    )

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
    # MAIN WATCHLIST & LIVE EMBEDDED TRADINGVIEW CHART
    # =========================================================================
    if df_scored.empty:
        st.warning("No stocks passed your current Layer 0 Pre-Filter pills above. Click any top filter pill (e.g. Mkt cap or Vol) to loosen the threshold.")
    else:
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
            lambda r: _build_tv_chart_url(str(r["exchange"]), str(r["ticker"]), active_layout_id),
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

        selection_event = st.dataframe(
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

        # =====================================================================
        # BOTTOM SECTION: LIVE EMBEDDED TRADINGVIEW ADVANCED CHART WIDGET
        # =====================================================================
        if not df_view.empty:
            inspected_row = df_view.iloc[active_idx]
            sel_ticker = str(inspected_row["ticker"])
            sel_name = str(inspected_row.get("company_name", ""))
            sel_exch = str(inspected_row.get("exchange", "NASDAQ"))
            tv_link = _build_tv_chart_url(sel_exch, sel_ticker, active_layout_id)

            dr_hdr1, nav_prev_col, nav_next_col, dr_hdr2 = st.columns([2.9, 0.65, 0.85, 1.25])
            with dr_hdr1:
                st.markdown(
                    f"#### 📈 **[{active_idx + 1}/{len(df_view)}] {sel_exch}:{sel_ticker}** — {sel_name} "
                    f"(`{inspected_row['pass_summary']}` · `{inspected_row['diagnostic_badge']}`)"
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
                    if _extract_tv_layout_id(active_layout_id)
                    else f"📈 Open {sel_ticker} in TradingView ↗"
                )
                st.link_button(
                    btn_label,
                    url=tv_link,
                    use_container_width=True,
                )

            _inject_keyboard_row_navigation()
            _render_tradingview_advanced_chart(sel_exch, sel_ticker, height=500)


if __name__ == "__main__":
    main()
