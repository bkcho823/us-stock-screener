"""
Layer 2 Top Filter Pills — Renders the Industry Group Gate, Lone Wolf Exemption,
Composite Weight Configuration, and Top Industry Leaderboard Popovers.
"""

from __future__ import annotations

from typing import Dict, Any, List
import streamlit as st


def render_layer2_pills(l2: Dict[str, Any], l2_meta: Dict[str, Any] | None = None) -> None:
    """Renders the Layer 2 Industry Momentum & Leadership Top Pill Bar."""
    if l2_meta is None:
        l2_meta = {}

    leaderboard: List[Dict[str, Any]] = l2_meta.get("leaderboard", [])
    top_group_pct = float(l2.get("top_group_pct", 40.0))
    gate_on = bool(l2.get("group_gate_enabled", True))
    lone_wolf_on = bool(l2.get("lone_wolf_enabled", True))

    l2_cols = st.columns([1.5, 1.3, 1.4, 1.8])

    # 1. Pill: Top Industry Group Gate (Top 40%)
    with l2_cols[0]:
        gate_lbl = f"✅ L2: Top {top_group_pct:g}% Group" if gate_on else "⚪ L2 Group Gate: OFF"
        with st.popover(gate_lbl, use_container_width=True):
            st.markdown("**Industry Group Momentum Gate**")
            st.caption("Filters out stocks in lagging/declining industry groups based on 1M/3M/6M rotation momentum.")
            l2["group_gate_enabled"] = st.toggle("Enable Group Gate", value=gate_on)
            l2["top_group_pct"] = st.slider(
                "Keep Top X% of Industries",
                min_value=10.0,
                max_value=90.0,
                value=top_group_pct,
                step=5.0,
                help="E.g., Top 40% means industry percentile >= 60.",
            )

    # 2. Pill: Lone Wolf Leader Override (RS >= 90)
    with l2_cols[1]:
        lw_lbl = f"🦅 RS ≥ {l2.get('lone_wolf_min_rs', 90)} Override" if lone_wolf_on else "⚪ Lone Wolf: OFF"
        with st.popover(lw_lbl, use_container_width=True):
            st.markdown("**Lone Wolf Super-Leader Exemption**")
            st.caption("Allows true market leaders (RS ≥ 90) through even if their industry hasn't woken up yet.")
            l2["lone_wolf_enabled"] = st.toggle("Enable Lone Wolf Exemption", value=lone_wolf_on)
            l2["lone_wolf_min_rs"] = st.slider(
                "Minimum Individual RS",
                min_value=80,
                max_value=99,
                value=int(l2.get("lone_wolf_min_rs", 90)),
                step=1,
            )

    # 3. Pill: Composite Score Weights
    with l2_cols[2]:
        w_stock = int(float(l2.get("weight_stock_rs", 0.50)) * 100)
        w_group = int(float(l2.get("weight_group_rs", 0.35)) * 100)
        w_lead = int(float(l2.get("weight_lead_rank", 0.15)) * 100)
        with st.popover(f"⚖️ L2 Weights ({w_stock}/{w_group}/{w_lead})", use_container_width=True):
            st.markdown("**Layer 2 Composite Score Weights**")
            st.caption("Customize the relative importance of individual momentum, industry tailwind, and in-group rank.")
            
            b1, b2, b3 = st.columns(3)
            with b1:
                if st.button("Default (50/35/15)", use_container_width=True):
                    l2["weight_stock_rs"] = 0.50
                    l2["weight_group_rs"] = 0.35
                    l2["weight_lead_rank"] = 0.15
                    st.rerun()
            with b2:
                if st.button("Stock Focus (70/20/10)", use_container_width=True):
                    l2["weight_stock_rs"] = 0.70
                    l2["weight_group_rs"] = 0.20
                    l2["weight_lead_rank"] = 0.10
                    st.rerun()
            with b3:
                if st.button("Theme Focus (30/50/20)", use_container_width=True):
                    l2["weight_stock_rs"] = 0.30
                    l2["weight_group_rs"] = 0.50
                    l2["weight_lead_rank"] = 0.20
                    st.rerun()

            ws = st.slider("Individual Stock RS (%)", 10, 80, w_stock, step=5)
            wg = st.slider("Industry Group RS (%)", 10, 60, w_group, step=5)
            wl = st.slider("In-Group Leadership Rank (%)", 5, 30, w_lead, step=5)
            
            total = ws + wg + wl
            if total > 0:
                l2["weight_stock_rs"] = round(ws / total, 2)
                l2["weight_group_rs"] = round(wg / total, 2)
                l2["weight_lead_rank"] = round(wl / total, 2)

    # 4. Pill: Top Industry Leaderboard Quick Inspection
    with l2_cols[3]:
        with st.popover(f"🏆 Leading Industry Groups ({len(leaderboard)})", use_container_width=True):
            st.markdown("**Market-Wide Industry Rotation Leaderboard**")
            st.caption("Top performing industry groups based on 1M / 3M / 6M rotation momentum across the Layer 0 pool:")
            if leaderboard:
                top_items = leaderboard[:12]
                st.dataframe(
                    top_items,
                    use_container_width=True,
                    height=280,
                    hide_index=True,
                    column_config={
                        "rank": st.column_config.NumberColumn("Rank", format="#%d", width="small"),
                        "industry": st.column_config.TextColumn("Industry", width="medium"),
                        "sector": st.column_config.TextColumn("Sector", width="small"),
                        "rs_pct": st.column_config.ProgressColumn("RS Rank", format="%d", min_value=1, max_value=99),
                        "breadth_pct": st.column_config.NumberColumn(">50MA %", format="%.0f%%"),
                        "stock_count": st.column_config.NumberColumn("Stocks", format="%d"),
                    },
                )
            else:
                st.info("Leaderboard will populate once daily market universe is computed.")
