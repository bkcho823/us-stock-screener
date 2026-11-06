"""
Layer 3 Top Filter Pills — Renders VCP Tightness Gate, Max Contraction Slider,
Volume Dry-up Slider, JLaw 21/50 EMA Alignment Toggle, and Structure Status Popover.
"""

from __future__ import annotations

from typing import Dict, Any
import streamlit as st


def render_layer3_pills(l3: Dict[str, Any], l3_meta: Dict[str, Any] | None = None) -> None:
    """Renders the Layer 3 VCP Tightness & EMA Structure Top Pill Bar."""
    if l3_meta is None:
        l3_meta = {}

    vcp_gate_on = bool(l3.get("vcp_gate_enabled", True))
    require_ema = bool(l3.get("require_ema_alignment", True))
    max_contraction = float(l3.get("max_contraction_pct", 8.0))
    max_vol = float(l3.get("max_vol_dryup_pct", 65.0))
    min_tightness = float(l3.get("min_tightness_score", 60.0))

    l3_cols = st.columns([1.6, 1.4, 1.5, 1.5])

    # 1. Pill: VCP Pattern Gate & Contraction Tightness Slider
    with l3_cols[0]:
        vcp_lbl = f"🎯 L3: VCP Tight (≤{max_contraction:g}%)" if vcp_gate_on else "⚪ L3 VCP Gate: OFF"
        with st.popover(vcp_lbl, use_container_width=True):
            st.markdown("**Minervini VCP Contraction Gate**")
            st.caption("Filters for stocks whose most recent pullback contraction is compact and tight.")
            l3["vcp_gate_enabled"] = st.toggle("Enable VCP Gate", value=vcp_gate_on)
            l3["max_contraction_pct"] = st.slider(
                "Max Contraction Range (%)",
                min_value=3.0,
                max_value=15.0,
                value=max_contraction,
                step=0.5,
                help="Minervini ideal last contraction is 3% - 8%.",
            )
            l3["min_tightness_score"] = st.slider(
                "Min VCP Score (0-100)",
                min_value=30.0,
                max_value=90.0,
                value=min_tightness,
                step=5.0,
            )

    # 2. Pill: Volume Dry-Up (Supply Exhaustion)
    with l3_cols[1]:
        vol_lbl = f"📉 Vol Dry-Up (≤{max_vol:g}%)" if vcp_gate_on else "⚪ Vol Dry-Up: OFF"
        with st.popover(vol_lbl, use_container_width=True):
            st.markdown("**Volume Contraction / Supply Dry-Up**")
            st.caption("Ensures institutional selling has stopped before breakout by requiring volume to contract below average.")
            l3["max_vol_dryup_pct"] = st.slider(
                "Max Volume vs 50D/60D Avg (%)",
                min_value=20.0,
                max_value=100.0,
                value=max_vol,
                step=5.0,
                help="Ideal VCP dry-up is 30% - 65% of normal average volume.",
            )

    # 3. Pill: JLaw 21 EMA > 50 EMA Trend Structure
    with l3_cols[2]:
        ema_lbl = "📈 EMA 21 > 50: ON" if require_ema else "⚪ EMA 21 > 50: OFF"
        with st.popover(ema_lbl, use_container_width=True):
            st.markdown("**JLaw EMA Trend Alignment**")
            st.caption("Verifies that short-term moving average is stacked above medium-term (Close > 21EMA > 50EMA).")
            l3["require_ema_alignment"] = st.toggle("Require Close > 21EMA > 50EMA", value=require_ema)

    # 4. Pill: Layer 3 Status & Summary
    with l3_cols[3]:
        vcp_qual = l3_meta.get("l3_qualified_count", 0)
        ema_cnt = l3_meta.get("ema_aligned_count", 0)
        tight_cnt = l3_meta.get("tight_consolidation_count", 0)
        with st.popover(f"📐 VCP Candidates: {vcp_qual}", use_container_width=True):
            st.markdown("**Layer 3 Structure Diagnostics**")
            st.write(f"• **VCP & EMA Fully Qualified:** `{vcp_qual}` stocks")
            st.write(f"• **Close > 21EMA > 50EMA:** `{ema_cnt}` stocks")
            st.write(f"• **Tight Consolidation (≤{max_contraction}%):** `{tight_cnt}` stocks")
            st.caption("These stocks are in the tightest technical position to stage explosive 3-10 day breakouts.")
