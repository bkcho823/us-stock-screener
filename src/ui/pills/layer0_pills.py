"""
Layer 0 Top Filter Pills — Renders all 11 Layer 0 Candidate Universe Pre-Filter pills
across 2 wide non-truncated rows (6 + 5 pills).
"""

from __future__ import annotations

from typing import Dict, Any

import streamlit as st

from src.config import ALL_EXCHANGES


def _fmt_vol(val: int | float) -> str:
    v = float(val)
    if v >= 1_000_000:
        return f"{v / 1_000_000:.1f}M".replace(".0M", "M")
    if v >= 1_000:
        return f"{v / 1_000:.0f}K"
    return str(int(v))


def render_layer0_pills(l0: Dict[str, Any]) -> None:
    """Renders all 11 Layer 0 Universe Pre-Filter pills (Exchanges, ETFs, ADRs, Price, Mkt Cap, Dollar Vol, 1D–90D Vol)."""
    # Row 1: 6 Wide Layer 0 Pills
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

    # Row 2: 5 Wide Layer 0 Volume Pills (1D, 10D, 30D, 60D, 90D)
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
