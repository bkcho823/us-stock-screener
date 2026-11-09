"""
Layer 1 Top Filter Pills — Renders all 11 Layer 1 Trend & Momentum pills (C1 through C11)
across 2 wide non-truncated rows (6 + 5 pills).
"""

from __future__ import annotations

from typing import Dict, Any

import streamlit as st

from src.config import compute_dynamic_sp500_threshold


def render_layer1_pills(l1: Dict[str, Any], sp500_bm: Dict[str, Any]) -> None:
    """Renders all 11 Layer 1 Trend & Momentum condition pills (`C1`–`C11`)."""
    sp_1m = float((sp500_bm or {}).get("perf_1m_pct", 0.0))
    sp_6m = float((sp500_bm or {}).get("perf_6m_pct", 0.0))

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

    # Row 1: 6 Wide Layer 1 Trend Pills (C1, C2, C3, C4, C5, C9)
    l1_r1 = st.columns(6)
    with l1_r1[0]:
        ipo_on = bool(l1.get("ipo_mode_enabled", True))
        ipo_tag = " (+IPO)" if ipo_on else ""
        p_c1 = f"✅ C1: P > 150/200{ipo_tag}" if l1["c1_enabled"] else "⚪ C1: P > 150/200"
        with st.popover(p_c1, use_container_width=True):
            l1["c1_enabled"] = st.toggle("Enable C1: Price > SMA 150 & SMA 200", value=bool(l1.get("c1_enabled", True)))
            st.markdown("---")
            l1["ipo_mode_enabled"] = st.toggle(
                "🚀 Enable IPO Lifecycle Mode (<200D Bars)",
                value=ipo_on,
                help="Allows recent IPOs & spin-offs (<200 trading bars, e.g. RDDT, GEV) to pass C1–C4 using JLaw's IPO Stage 2 stack (Close > EMA21 > SMA50).",
            )
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

    # Row 2: 5 Wide Layer 1 Momentum & 52W Pills (C6, C7, C8, C10, C11)
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
