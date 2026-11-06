"""
Layer 4 Top Filter Pills — Renders Entry Trigger Gate, Volume Surge Threshold,
Buy Zone Range Sliders, and Actionable Breakout Status Filter.
"""

from __future__ import annotations

from typing import Dict, Any
import streamlit as st


def render_layer4_pills(l4: Dict[str, Any], l4_meta: Dict[str, Any] | None = None) -> None:
    """Renders the Layer 4 Actionable Entry Trigger & Pivot Top Pill Bar."""
    if l4_meta is None:
        l4_meta = {}

    gate_on = bool(l4.get("entry_gate_enabled", True))
    min_vol = float(l4.get("min_vol_expansion_pct", 120.0))
    max_buy_zone = float(l4.get("max_buy_zone_pct", 3.5))
    on_deck = float(l4.get("on_deck_pct", 3.0))
    status_filter = str(l4.get("action_status_filter", "ALL")).upper()

    trig_cnt = l4_meta.get("triggered_count", 0)
    bz_cnt = l4_meta.get("buy_zone_count", 0)
    deck_cnt = l4_meta.get("on_deck_count", 0)

    l4_cols = st.columns([1.6, 1.4, 1.5, 1.5])

    # 1. Pill: Entry Trigger Gate & Status Filter
    with l4_cols[0]:
        filter_label = "All Actionable"
        if status_filter == "TRIGGERED_ONLY":
            filter_label = "🚀 Triggered"
        elif status_filter == "BUY_ZONE_ONLY":
            filter_label = "⚡ Buy Zone"
        elif status_filter == "ON_DECK_ONLY":
            filter_label = "⏳ On Deck"

        lbl = f"🎯 L4 Entry: {filter_label}" if gate_on else "⚪ L4 Gate: OFF"
        with st.popover(lbl, use_container_width=True):
            st.markdown("**Actionable Entry Trigger Gate**")
            st.caption("Filters for stocks breaking out today or poised in the low-risk buy zone.")
            l4["entry_gate_enabled"] = st.toggle("Enable Entry Gate", value=gate_on)

            status_opts = [
                "ALL (🚀 Triggered + ⚡ Buy Zone + ⏳ On Deck)",
                "🚀 Triggered Today Only",
                "⚡ In Buy Zone Only",
                "⏳ On Deck Only",
            ]
            cur_idx = 0
            if status_filter == "TRIGGERED_ONLY":
                cur_idx = 1
            elif status_filter == "BUY_ZONE_ONLY":
                cur_idx = 2
            elif status_filter == "ON_DECK_ONLY":
                cur_idx = 3

            chosen = st.radio(
                "Filter by Action Status",
                options=status_opts,
                index=cur_idx,
            )
            if chosen.startswith("🚀"):
                l4["action_status_filter"] = "TRIGGERED_ONLY"
            elif chosen.startswith("⚡"):
                l4["action_status_filter"] = "BUY_ZONE_ONLY"
            elif chosen.startswith("⏳"):
                l4["action_status_filter"] = "ON_DECK_ONLY"
            else:
                l4["action_status_filter"] = "ALL"

    # 2. Pill: Breakout Volume Expansion Threshold
    with l4_cols[1]:
        vol_lbl = f"📊 Vol Surge (≥{min_vol:g}%)" if gate_on else "⚪ Vol Surge: OFF"
        with st.popover(vol_lbl, use_container_width=True):
            st.markdown("**Institutional Volume Expansion**")
            st.caption("Minimum volume surge vs 50-day average required for a confirmed 🚀 Triggered breakout.")
            l4["min_vol_expansion_pct"] = st.slider(
                "Min Breakout Volume Surge (%)",
                min_value=100.0,
                max_value=200.0,
                value=min_vol,
                step=5.0,
                help="120% = 20% higher than average volume. 150% = 1.5x average volume.",
            )

    # 3. Pill: Buy Zone & On Deck Distance Sliders
    with l4_cols[2]:
        dist_lbl = f"📏 Buy Zone (≤{max_buy_zone:g}%)" if gate_on else "⚪ Buy Zone: OFF"
        with st.popover(dist_lbl, use_container_width=True):
            st.markdown("**Low-Risk Buy Zone & Setup Proximity**")
            st.caption("Minervini discipline: avoid chasing stocks extended > 3-5% above resistance pivot.")
            l4["max_buy_zone_pct"] = st.slider(
                "Max Buy Zone Distance (+%)",
                min_value=1.5,
                max_value=6.0,
                value=max_buy_zone,
                step=0.5,
                help="Maximum % price can extend above pivot before marked as 🛑 EXTENDED.",
            )
            l4["on_deck_pct"] = st.slider(
                "On-Deck Cushion (-%)",
                min_value=1.0,
                max_value=5.0,
                value=on_deck,
                step=0.5,
                help="Stocks within this % below pivot are tagged as ⏳ ON DECK.",
            )

    # 4. Pill: Breakout Action Status Summary
    with l4_cols[3]:
        summary_lbl = f"⚡ Action (🚀{trig_cnt} · ⚡{bz_cnt} · ⏳{deck_cnt})"
        with st.popover(summary_lbl, use_container_width=True):
            st.markdown("**Live Breakout Status Breakdown**")
            st.markdown(
                f"- 🚀 **`TRIGGERED TODAY`**: **{trig_cnt}** stocks (Broke pivot on heavy volume)\n"
                f"- ⚡ **`IN BUY ZONE`**: **{bz_cnt}** stocks (Within +{max_buy_zone}% of pivot)\n"
                f"- ⏳ **`ON DECK`**: **{deck_cnt}** stocks (Coiled within -{on_deck}% of pivot)\n"
            )
            st.caption("Click any row in the setups table below to inspect its chart pattern.")
