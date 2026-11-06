"""
Layer 5 Top Filter Pills — Renders Risk Management Gate, Stop-Loss Sliders,
Account Sizing Inputs, and Portfolio Allocation Controls.
"""

from __future__ import annotations

from typing import Dict, Any
import streamlit as st


def render_layer5_pills(l5: Dict[str, Any], l5_meta: Dict[str, Any] | None = None) -> None:
    """Renders the Layer 5 Risk Management & Position Sizing Top Pill Bar."""
    if l5_meta is None:
        l5_meta = {}

    gate_on = bool(l5.get("risk_gate_enabled", True))
    account_equity = float(l5.get("account_equity", 100000.0))
    risk_pct = float(l5.get("max_risk_pct_per_trade", 1.0))
    max_stop = float(l5.get("max_stop_loss_pct", 7.0))
    rr_ratio = float(l5.get("min_reward_risk_ratio", 2.5))
    max_alloc = float(l5.get("max_portfolio_allocation_pct", 25.0))

    max_dollar_risk = account_equity * (risk_pct / 100.0)
    max_capital_alloc = account_equity * (max_alloc / 100.0)
    avg_risk = l5_meta.get("avg_risk_pct", max_stop * 0.7)

    l5_cols = st.columns([1.6, 1.6, 1.4, 1.4])

    # 1. Pill: Stop-Loss & Reward/Risk Gate
    with l5_cols[0]:
        stop_lbl = f"🛡️ L5 Stop: ≤{max_stop:g}% (Target {rr_ratio:g}R)" if gate_on else "⚪ L5 Risk: OFF"
        with st.popover(stop_lbl, use_container_width=True):
            st.markdown("**Capital Protection & Stop-Loss Clamp**")
            st.caption("Minervini discipline: cut losses quickly and clamp maximum downside risk.")
            l5["risk_gate_enabled"] = st.toggle("Enable Risk Gate", value=gate_on)
            l5["max_stop_loss_pct"] = st.slider(
                "Max Allowable Stop-Loss (%)",
                min_value=3.0,
                max_value=10.0,
                value=max_stop,
                step=0.5,
                help="Eliminates setups where the logical stop exceeds this percentage.",
            )
            l5["min_reward_risk_ratio"] = st.slider(
                "Target Reward-to-Risk (R-Multiple)",
                min_value=1.5,
                max_value=4.5,
                value=rr_ratio,
                step=0.25,
                help="Standard swing trading target is 2.5:1 or 3.0:1 reward-to-risk.",
            )

    # 2. Pill: Account Equity & 1% Risk Rule
    with l5_cols[1]:
        acct_lbl = f"💰 Equity: ${account_equity:,.0f} ({risk_pct:g}% Risk)"
        with st.popover(acct_lbl, use_container_width=True):
            st.markdown("**Portfolio Equity & Risk Sizing**")
            st.caption("Institutional 1% Risk Rule: risk no more than 1% of total equity on any trade.")
            l5["account_equity"] = st.number_input(
                "Account Equity ($)",
                min_value=1000.0,
                max_value=50000000.0,
                value=account_equity,
                step=5000.0,
            )
            l5["max_risk_pct_per_trade"] = st.slider(
                "Max Account Risk Per Trade (%)",
                min_value=0.25,
                max_value=2.5,
                value=risk_pct,
                step=0.25,
                help="Standard professional guideline is 0.5% to 1.25% per trade.",
            )
            st.info(f"💵 Maximum Dollar Risk per Trade: **${max_dollar_risk:,.2f}**")

    # 3. Pill: Max Portfolio Allocation Cap
    with l5_cols[2]:
        alloc_lbl = f"💼 Position Cap: ≤{max_alloc:g}%"
        with st.popover(alloc_lbl, use_container_width=True):
            st.markdown("**Concentration Limit per Trade**")
            st.caption("Prevents over-allocation: limits the maximum position capital.")
            l5["max_portfolio_allocation_pct"] = st.slider(
                "Max Allocation Cap (%)",
                min_value=10.0,
                max_value=50.0,
                value=max_alloc,
                step=2.5,
                help="25% = maximum of 4 equal-sized positions in your account.",
            )
            st.info(f"🏦 Maximum Position Size: **${max_capital_alloc:,.2f}**")

    # 4. Pill: Live Sizing & Risk Profile Summary
    with l5_cols[3]:
        summary_lbl = f"📐 Risk 1R: ~{avg_risk:.1f}% Avg"
        with st.popover(summary_lbl, use_container_width=True):
            st.markdown("**Position Sizing Calculator Parameters**")
            st.markdown(
                f"- **Account Equity**: `${account_equity:,.2f}`\n"
                f"- **1R Risk Budget**: `${max_dollar_risk:,.2f}` (`{risk_pct}%`)\n"
                f"- **Max Capital/Trade**: `${max_capital_alloc:,.2f}` (`{max_alloc}%`)\n"
                f"- **Max Stop-Loss**: `≤ {max_stop}%`\n"
                f"- **Target R/R**: `{rr_ratio}:1`\n"
            )
            st.caption("Position sizes and stop-losses are calculated in real time in the table below.")
