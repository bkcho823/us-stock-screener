"""
Compact Bottleneck Detector & Funnel Summary Strip — Displays Layer 0 Pool count,
Qualified count, Near-Miss count, and color-coded C1–C11 pass rates.
"""

from __future__ import annotations

from typing import Dict, Any

import streamlit as st


def render_bottleneck_strip(summary_meta: Dict[str, Any]) -> None:
    """Renders the horizontal color-coded condition bottleneck chip strip."""
    if not summary_meta.get("condition_bottlenecks"):
        return

    l0_cnt = summary_meta["layer0_count"]
    qual_cnt = summary_meta["qualified_count"]
    near_cnt = summary_meta["near_miss_count"]
    active_cnt = summary_meta["active_condition_count"]

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
