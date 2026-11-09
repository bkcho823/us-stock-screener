"""
Layer 3 — Volatility Contraction Pattern (VCP) & EMA Structure Confirmation Engine.
Applies:
1. Mark Minervini's VCP Tightness (last contraction amplitude <= X%, volume contraction <= Y% of avg volume).
2. JLaw's short/medium-term structure: Close > 21EMA > 50EMA (and pullback cushion testing 21EMA/50EMA).
3. Produces VCP Tightness Score (0-100) and Plain-English structure status badges (e.g. 'VCP 3T (Tight: 4.2%)', 'EMA Pullback Support').
"""

from __future__ import annotations

from typing import Dict, Any, Tuple
import numpy as np
import pandas as pd


def _calc_vcp_tightness_score(contraction_pct: float, vol_dryup_pct: float, ema_aligned: bool) -> float:
    """
    Computes a 0-100 VCP Tightness Score:
    - Contraction amplitude (0-50 pts): <= 4% = 50 pts, <= 8% = 40 pts, <= 12% = 25 pts, >15% = 10 pts.
    - Volume dry-up (0-35 pts): <= 40% avg = 35 pts, <= 65% avg = 25 pts, <= 85% = 15 pts.
    - EMA Alignment (0-15 pts): 15 pts if Close > 21EMA > 50EMA.
    """
    score = 0.0

    # Contraction component (50%)
    if contraction_pct <= 4.0:
        score += 50.0
    elif contraction_pct <= 8.0:
        score += 40.0 - ((contraction_pct - 4.0) / 4.0) * 10.0
    elif contraction_pct <= 12.0:
        score += 30.0 - ((contraction_pct - 8.0) / 4.0) * 15.0
    else:
        score += max(5.0, 15.0 - (contraction_pct - 12.0))

    # Volume dry-up component (35%)
    if vol_dryup_pct <= 40.0:
        score += 35.0
    elif vol_dryup_pct <= 65.0:
        score += 25.0 + ((65.0 - vol_dryup_pct) / 25.0) * 10.0
    elif vol_dryup_pct <= 90.0:
        score += 15.0 + ((90.0 - vol_dryup_pct) / 25.0) * 10.0
    else:
        score += max(5.0, 15.0 - ((vol_dryup_pct - 90.0) / 50.0) * 10.0)

    # EMA Alignment component (15%)
    if ema_aligned:
        score += 15.0

    return round(float(np.clip(score, 0.0, 100.0)), 1)


def evaluate_layer3_vcp_and_structure(
    df_l2_scored: pd.DataFrame,
    layer3_cfg: Dict[str, Any],
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Evaluates Layer 3 VCP pattern contraction, volume dry-up, and 21/50 EMA alignment.
    """
    if df_l2_scored is None or df_l2_scored.empty:
        return pd.DataFrame(), {
            "l3_enabled": bool(layer3_cfg.get("l3_enabled", True)),
            "vcp_qualified_count": 0,
            "ema_aligned_count": 0,
            "tight_consolidation_count": 0,
        }

    df = df_l2_scored.copy()

    # Gracefully ensure Layer 3 indicator columns exist
    if "ema_21" not in df.columns:
        if "ema_20" in df.columns:
            df["ema_21"] = df["ema_20"].round(2)
        elif "sma_20" in df.columns:
            df["ema_21"] = df["sma_20"].round(2)
        else:
            df["ema_21"] = df["close"].round(2)

    if "ema_50" not in df.columns:
        if "sma_50" in df.columns:
            df["ema_50"] = df["sma_50"].round(2)
        else:
            df["ema_50"] = df["close"].round(2)

    if "last_contraction_pct" not in df.columns:
        if "volatility_d" in df.columns:
            df["last_contraction_pct"] = (df["volatility_d"].fillna(3.0) * 1.8).clip(2.0, 15.0).round(2)
        else:
            df["last_contraction_pct"] = pd.Series(5.5, index=df.index)

    if "vol_dryup_pct" not in df.columns:
        if "vol_60d" in df.columns and "vol_1d" in df.columns:
            vol_avg = df["vol_60d"].replace(0, np.nan).fillna(df["vol_1d"].replace(0, 1))
            v10 = df.get("vol_10d", df["vol_1d"]).fillna(df["vol_1d"])
            prior_9d_vol = ((10.0 * v10 - df["vol_1d"]) / 9.0).clip(lower=v10 * 0.25)
            df["vol_dryup_pct"] = ((prior_9d_vol / vol_avg) * 100.0).clip(10.0, 200.0).round(1)
        else:
            df["vol_dryup_pct"] = pd.Series(50.0, index=df.index)

    if "adr_20_pct" not in df.columns:
        if "volatility_d" in df.columns:
            df["adr_20_pct"] = df["volatility_d"].fillna(3.0).clip(0.5, 25.0).round(2)
        else:
            df["adr_20_pct"] = pd.Series(3.5, index=df.index)

    l3_enabled = bool(layer3_cfg.get("l3_enabled", True))
    vcp_gate_on = bool(layer3_cfg.get("vcp_gate_enabled", True))
    require_ema = bool(layer3_cfg.get("require_ema_alignment", True))
    max_contraction = float(layer3_cfg.get("max_contraction_pct", 8.0))
    max_vol_dryup = float(layer3_cfg.get("max_vol_dryup_pct", 65.0))
    min_tightness = float(layer3_cfg.get("min_tightness_score", 60.0))
    min_adr_pct = float(layer3_cfg.get("min_adr_pct", 2.5))

    # 1. JLaw EMA Alignment: Close > 21EMA > 50EMA
    df["ema_aligned"] = (df["close"] > df["ema_21"]) & (df["ema_21"] > df["ema_50"])

    # Pullback Support: testing 21EMA or 50EMA within -1.5% to +2.5% cushion
    df["dist_to_ema21_pct"] = (((df["close"] - df["ema_21"]) / df["ema_21"]) * 100.0).round(2)
    df["is_ema_pullback"] = (df["dist_to_ema21_pct"] >= -1.5) & (df["dist_to_ema21_pct"] <= 2.5)

    # 2. Minervini VCP Contraction, Volume Dry-up, & JLaw Minimum ADR% Filter
    df["is_tight_contraction"] = df["last_contraction_pct"] <= max_contraction
    df["is_vol_dryup"] = df["vol_dryup_pct"] <= max_vol_dryup
    df["is_adr_qualified"] = df["adr_20_pct"] >= min_adr_pct

    # 3. VCP Tightness Score (0-100)
    df["vcp_score"] = [
        _calc_vcp_tightness_score(float(c), float(v), bool(e))
        for c, v, e in zip(df["last_contraction_pct"], df["vol_dryup_pct"], df["ema_aligned"])
    ]

    # 4. Layer 3 Gate Qualification
    if not l3_enabled or not vcp_gate_on:
        df["l3_qualified"] = True
    else:
        # Stock passes if it has tight consolidation / VCP score >= threshold, ADR% >= min_adr_pct, AND (if required) EMA alignment
        cond = ((df["vcp_score"] >= min_tightness) | (df["is_tight_contraction"] & df["is_vol_dryup"])) & df["is_adr_qualified"]
        if require_ema:
            cond &= df["ema_aligned"]
        df["l3_qualified"] = cond

    # 5. Descriptive Pattern Badge
    def _make_vcp_badge(row: pd.Series) -> str:
        contraction = row["last_contraction_pct"]
        vol = row["vol_dryup_pct"]
        adr = row["adr_20_pct"]
        if not row["is_adr_qualified"]:
            return f"🐢 Low ADR ({adr:.1f}% < {min_adr_pct:g}%)"
        if row["is_tight_contraction"] and row["is_vol_dryup"]:
            return f"🎯 VCP Tight ({contraction:.1f}% · Dry {vol:.0f}% · ADR {adr:.1f}%)"
        if row["is_tight_contraction"]:
            return f"📐 Tight Range ({contraction:.1f}% · ADR {adr:.1f}%)"
        if row["is_ema_pullback"]:
            return f"📈 EMA21 Pullback ({row['dist_to_ema21_pct']:+.1f}% · ADR {adr:.1f}%)"
        if row["ema_aligned"]:
            return f"✓ EMA Stacked (21>50 · ADR {adr:.1f}%)"
        return f"〰 Wide Range ({contraction:.1f}%)"

    df["vcp_badge"] = df.apply(_make_vcp_badge, axis=1)

    # Re-sort watchlist:
    # 1. Qualified L1
    # 2. Qualified L2
    # 3. Qualified L3
    # 4. Composite Score
    # 5. VCP Score
    sort_cols = [c for c in ["qualified_all", "l2_qualified", "l3_qualified", "composite_score", "vcp_score", "rs_percentile"] if c in df.columns]
    df = df.sort_values(by=sort_cols, ascending=[False] * len(sort_cols)).reset_index(drop=True)

    summary_meta = {
        "l3_enabled": l3_enabled,
        "vcp_gate_enabled": vcp_gate_on,
        "require_ema_alignment": require_ema,
        "max_contraction_pct": max_contraction,
        "max_vol_dryup_pct": max_vol_dryup,
        "min_tightness_score": min_tightness,
        "min_adr_pct": min_adr_pct,
        "l3_qualified_count": int((df.get("qualified_all", True) & df.get("l2_qualified", True) & df["l3_qualified"]).sum()),
        "ema_aligned_count": int(df["ema_aligned"].sum()),
        "tight_consolidation_count": int(df["is_tight_contraction"].sum()),
        "adr_qualified_count": int(df["is_adr_qualified"].sum()),
    }

    return df, summary_meta
