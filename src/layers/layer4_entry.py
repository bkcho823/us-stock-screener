"""
Layer 4: Actionable Entry Triggers & Pivot Detection Engine.
Calculates resistance pivot points, distance to pivot (%), institutional volume expansion (%),
and assigns the 4 actionable execution status classifications:
  - 🚀 TRIGGERED TODAY: Broke pivot today on institutional volume surge (>= 120%)
  - ⚡ IN BUY ZONE: Within 0% to +3.5% of pivot (low-risk entry window)
  - ⏳ ON DECK: Within -3.0% to 0% below pivot (coiling for imminent breakout)
  - 🛑 EXTENDED: > +3.5% past pivot (do not chase)
  - 〰 BUILDING: < -3.0% below pivot (still basing / consolidating)
"""

from __future__ import annotations

from typing import Dict, Any, Tuple
import numpy as np
import pandas as pd


def evaluate_layer4_entry_signals(
    df: pd.DataFrame,
    layer4_cfg: Dict[str, Any] | None = None,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Evaluates actionable entry signals and assigns execution status badges.
    """
    if layer4_cfg is None:
        layer4_cfg = {}

    if df.empty:
        return df, {
            "l4_enabled": True,
            "entry_gate_enabled": True,
            "l4_qualified_count": 0,
            "triggered_count": 0,
            "buy_zone_count": 0,
            "on_deck_count": 0,
        }

    df = df.copy()

    l4_enabled = bool(layer4_cfg.get("l4_enabled", True))
    gate_on = bool(layer4_cfg.get("entry_gate_enabled", True))
    min_vol_expansion = float(layer4_cfg.get("min_vol_expansion_pct", 120.0))
    max_buy_zone = float(layer4_cfg.get("max_buy_zone_pct", 3.5))
    on_deck_pct = float(layer4_cfg.get("on_deck_pct", 3.0))
    status_filter = str(layer4_cfg.get("action_status_filter", "ALL")).upper()

    # 1. Volume Expansion Ratio vs 50D/60D Average Volume
    if "vol_60d" in df.columns:
        vol_avg = df["vol_60d"].replace(0, np.nan).fillna(df.get("vol_10d", df.get("vol_1d", 1)))
    elif "vol_10d" in df.columns:
        vol_avg = df["vol_10d"].replace(0, np.nan).fillna(df.get("vol_1d", 1))
    else:
        vol_avg = df.get("vol_1d", pd.Series(1, index=df.index))

    vol_1d = df.get("vol_1d", pd.Series(1, index=df.index))
    df["vol_expansion_pct"] = ((vol_1d / vol_avg.replace(0, np.nan)) * 100.0).fillna(100.0).clip(10.0, 500.0).round(1)

    # 2. Pivot Resistance Price Calculation (P0 Fix: Pre-Breakout 10D Coil Swing High & Prior 52W High)
    pivot_prices = []
    for _, row in df.iterrows():
        close = float(row.get("close", 10.0))
        high_52w = float(row.get("high_52w", close))
        prior_52w = float(row.get("prior_high_52w", high_52w))
        ref_52w = prior_52w if prior_52w > 0 else high_52w
        coil_high = float(row.get("coil_pivot_high", 0.0))
        contraction = float(row.get("last_contraction_pct", 6.0))

        if ref_52w > 0 and close >= ref_52w:
            # Breaking out at/above prior 52W high: pivot resistance is the prior 52W high level
            pivot = round(ref_52w, 2)
        elif ref_52w > 0 and ((ref_52w - close) / close) <= 0.08:
            # Within 8% of 52W high: primary overhead resistance is the prior 52W high
            pivot = round(ref_52w, 2)
        elif coil_high > 0:
            # Mid-base VCP (>8% below 52W high): resistance is the 10D pre-breakout consolidation swing high
            pivot = round(coil_high, 2)
        else:
            # Un-enriched fallback: if breaking out above SMA10 with a mid-base coil, anchor to SMA10; else 52W high
            sma_10_val = float(row.get("sma_10", 0.0) or 0.0)
            offset = max(0.8, min(contraction * 0.35, 4.5))
            if sma_10_val > 0 and sma_10_val < close:
                pivot = round(sma_10_val * (1.0 + (offset / 100.0)), 2)
            elif ref_52w > 0:
                pivot = round(ref_52w, 2)
            else:
                pivot = round(close * (1.0 + (offset / 100.0)), 2)
        pivot_prices.append(pivot)

    df["pivot_price"] = pivot_prices

    # 3. Distance to Pivot (%): (Close - Pivot) / Pivot * 100
    df["dist_to_pivot_pct"] = (((df["close"] - df["pivot_price"]) / df["pivot_price"]) * 100.0).round(2)

    # 4. Action Status Classification
    action_statuses = []
    action_badges = []

    for _, row in df.iterrows():
        dist = float(row["dist_to_pivot_pct"])
        vol_exp = float(row["vol_expansion_pct"])

        # State 1: Triggered Today (Breaking out now with heavy institutional volume surge)
        if 0.0 <= dist <= max_buy_zone and vol_exp >= min_vol_expansion:
            status = "TRIGGERED"
            badge = f"🚀 TRIGGERED ({dist:+.1f}% · Vol {vol_exp:.0f}%)"
        # State 2: In Buy Zone (Above pivot within low-risk tolerance)
        elif 0.0 <= dist <= max_buy_zone:
            status = "BUY_ZONE"
            badge = f"⚡ BUY ZONE ({dist:+.1f}% · Vol {vol_exp:.0f}%)"
        # State 3: On Deck (Coiled tightly right beneath the pivot)
        elif -on_deck_pct <= dist < 0.0:
            status = "ON_DECK"
            badge = f"⏳ ON DECK ({dist:+.1f}% to Pivot)"
        # State 4: Extended (> max buy zone)
        elif dist > max_buy_zone:
            status = "EXTENDED"
            badge = f"🛑 EXTENDED ({dist:+.1f}% past Pivot)"
        # State 5: Building Base (< -on_deck_pct)
        else:
            status = "BUILDING"
            badge = f"〰 BUILDING ({dist:+.1f}% to Pivot)"

        action_statuses.append(status)
        action_badges.append(badge)

    df["action_status"] = action_statuses
    df["action_status_badge"] = action_badges

    # 5. Qualification Gate
    if not l4_enabled or not gate_on:
        df["l4_qualified"] = True
    else:
        if status_filter == "TRIGGERED_ONLY":
            df["l4_qualified"] = df["action_status"] == "TRIGGERED"
        elif status_filter == "BUY_ZONE_ONLY":
            df["l4_qualified"] = df["action_status"].isin(["TRIGGERED", "BUY_ZONE"])
        elif status_filter == "ON_DECK_ONLY":
            df["l4_qualified"] = df["action_status"] == "ON_DECK"
        else:  # ALL actionable setups (Triggered, Buy Zone, or On Deck)
            df["l4_qualified"] = df["action_status"].isin(["TRIGGERED", "BUY_ZONE", "ON_DECK"])

    # Summary Metadata
    triggered_cnt = int((df["action_status"] == "TRIGGERED").sum())
    buy_zone_cnt = int((df["action_status"] == "BUY_ZONE").sum())
    on_deck_cnt = int((df["action_status"] == "ON_DECK").sum())
    l4_qual_cnt = int((
        df.get("qualified_all", True)
        & df.get("l2_qualified", True)
        & df.get("l3_qualified", True)
        & df["l4_qualified"]
    ).sum())

    l4_meta = {
        "l4_enabled": l4_enabled,
        "entry_gate_enabled": gate_on,
        "min_vol_expansion_pct": min_vol_expansion,
        "max_buy_zone_pct": max_buy_zone,
        "on_deck_pct": on_deck_pct,
        "action_status_filter": status_filter,
        "l4_qualified_count": l4_qual_cnt,
        "triggered_count": triggered_cnt,
        "buy_zone_count": buy_zone_cnt,
        "on_deck_count": on_deck_cnt,
    }

    return df, l4_meta
