"""
Layer 5: Risk Management & Position Sizing Calculator.
Calculates:
  - Logical Support & Max Risk Stop-Loss Price (Stop $)
  - Downside Risk Per Share (1R) and Risk Percentage (Risk %)
  - Profit Target Price based on Reward/Risk ratio (Target $, Target Gain %)
  - Position Sizing based on 1% Account Risk and Portfolio Cap allocation (Shares, Position $, Alloc %)
"""

from __future__ import annotations

from typing import Dict, Any, Tuple
import numpy as np
import pandas as pd


def evaluate_layer5_position_sizing(
    df: pd.DataFrame,
    layer5_cfg: Dict[str, Any] | None = None,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Computes stop-loss prices, 1R downside risk, profit targets, and recommended position sizes.
    """
    if layer5_cfg is None:
        layer5_cfg = {}

    if df.empty:
        return df, {
            "l5_enabled": True,
            "risk_gate_enabled": True,
            "account_equity": 100000.0,
            "max_risk_pct_per_trade": 1.0,
            "max_stop_loss_pct": 7.0,
            "min_reward_risk_ratio": 2.5,
            "max_portfolio_allocation_pct": 25.0,
            "l5_qualified_count": 0,
            "avg_risk_pct": 0.0,
        }

    df = df.copy()

    l5_enabled = bool(layer5_cfg.get("l5_enabled", True))
    gate_on = bool(layer5_cfg.get("risk_gate_enabled", True))
    account_equity = float(layer5_cfg.get("account_equity", 100000.0))
    risk_pct_per_trade = float(layer5_cfg.get("max_risk_pct_per_trade", 1.0))
    max_stop_pct = float(layer5_cfg.get("max_stop_loss_pct", 7.0))
    rr_ratio = float(layer5_cfg.get("min_reward_risk_ratio", 2.5))
    max_alloc_pct = float(layer5_cfg.get("max_portfolio_allocation_pct", 25.0))

    # Total dollar risk allowed on this trade
    max_dollar_risk = account_equity * (risk_pct_per_trade / 100.0)
    # Maximum total capital allocation allowed for a single position
    max_capital_allocation = account_equity * (max_alloc_pct / 100.0)

    stop_prices = []
    risk_amounts = []
    risk_pcts = []
    target_prices = []
    target_gain_pcts = []
    shares_list = []
    pos_values = []
    alloc_pcts = []
    risk_badges = []

    for _, row in df.iterrows():
        close = float(row.get("close", 10.0))
        contraction = float(row.get("last_contraction_pct", 5.0))
        ema20 = float(row.get("ema_20", close * 0.96))

        # 1. Structural Stop: below contraction low
        struct_stop = close * (1.0 - (contraction * 0.85 / 100.0))

        # 2. EMA Stop: 1% below 21-day EMA (if below close)
        ema_stop = ema20 * 0.99 if 0 < ema20 < close else struct_stop

        # Nearest logical support
        logical_stop = max(struct_stop, ema_stop)

        # 3. Maximum Risk Clamp (never exceed max_stop_pct)
        max_risk_stop = close * (1.0 - (max_stop_pct / 100.0))

        # Stop price is the tighter of logical support and max risk clamp,
        # but at least 2.0% below entry to prevent tick noise whipsaws
        stop_val = max(max_risk_stop, min(close * 0.98, logical_stop))
        stop_val = round(stop_val, 2)
        stop_prices.append(stop_val)

        # Risk per share (1R)
        risk_per_share = max(0.05, round(close - stop_val, 2))
        risk_amounts.append(risk_per_share)

        risk_pct = round((risk_per_share / close) * 100.0, 2)
        risk_pcts.append(risk_pct)

        # Target Price based on Reward/Risk ratio
        target_val = round(close + (rr_ratio * risk_per_share), 2)
        target_prices.append(target_val)

        target_gain = round(((target_val - close) / close) * 100.0, 1)
        target_gain_pcts.append(target_gain)

        # Position Sizing:
        # A) Risk-based shares = max_dollar_risk / risk_per_share
        shares_risk = int(max_dollar_risk / risk_per_share) if risk_per_share > 0 else 1
        # B) Capital-based shares = max_capital_allocation / close
        shares_cap = int(max_capital_allocation / close) if close > 0 else 1

        rec_shares = max(1, min(shares_risk, shares_cap))
        shares_list.append(rec_shares)

        pos_val = round(rec_shares * close, 2)
        pos_values.append(pos_val)

        pos_alloc = round((pos_val / account_equity) * 100.0, 1) if account_equity > 0 else 0.0
        alloc_pcts.append(pos_alloc)

        # Risk Badge
        risk_badge = f"🛑 Stop ${stop_val:.2f} (-{risk_pct:.1f}%) · 🎯 ${target_val:.2f} (+{target_gain:.1f}%)"
        risk_badges.append(risk_badge)

    df["stop_loss_price"] = stop_prices
    df["risk_per_share"] = risk_amounts
    df["risk_pct"] = risk_pcts
    df["target_price"] = target_prices
    df["target_gain_pct"] = target_gain_pcts
    df["recommended_shares"] = shares_list
    df["position_value"] = pos_values
    df["portfolio_alloc_pct"] = alloc_pcts
    df["risk_badge"] = risk_badges

    # Gate Qualification: Stock qualifies if downside risk is within acceptable boundaries (<= max_stop_pct)
    if not l5_enabled or not gate_on:
        df["l5_qualified"] = True
    else:
        df["l5_qualified"] = df["risk_pct"] <= max_stop_pct

    l5_qual_cnt = int((
        df.get("qualified_all", True)
        & df.get("l2_qualified", True)
        & df.get("l3_qualified", True)
        & df.get("l4_qualified", True)
        & df["l5_qualified"]
    ).sum())

    avg_risk = round(float(df["risk_pct"].mean()), 2) if not df.empty else 0.0

    l5_meta = {
        "l5_enabled": l5_enabled,
        "risk_gate_enabled": gate_on,
        "account_equity": account_equity,
        "max_risk_pct_per_trade": risk_pct_per_trade,
        "max_dollar_risk": max_dollar_risk,
        "max_stop_loss_pct": max_stop_pct,
        "min_reward_risk_ratio": rr_ratio,
        "max_portfolio_allocation_pct": max_alloc_pct,
        "max_capital_allocation": max_capital_allocation,
        "l5_qualified_count": l5_qual_cnt,
        "avg_risk_pct": avg_risk,
    }

    return df, l5_meta
