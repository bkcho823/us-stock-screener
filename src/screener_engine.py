"""
Step 3: Layer 0 & Layer 1 Screening & Math Engine
- Applies all 12 adjustable Layer 0 Pre-Filter controls (Market Cap, Price, 1D/10D/30D/60D/90D Volume, Dollar Volume, Exchanges, ETF/ADR toggles)
- Dynamically computes the 1-99 Relative Strength (RS) Percentile across the qualifying Layer 0 candidate pool
- Evaluates all 11 Layer 1 Trend & Momentum conditions (with independent ON/OFF toggles and adjustable thresholds)
- Returns full condition-by-condition pass/fail breakdown and summary metrics in <1 second.
"""

from __future__ import annotations

from typing import Dict, Any, Tuple, List
import numpy as np
import pandas as pd

from src.config import compute_dynamic_sp500_threshold, CONDITION_METADATA


def _pick_nearest_lag_column(lookback_days: int) -> str:
    """Maps any user-chosen lookback days N to the nearest pre-computed SMA200 lag column."""
    available = [5, 10, 15, 20, 30, 40, 60]
    nearest = min(available, key=lambda x: abs(x - int(lookback_days)))
    return f"sma_200_lag_{nearest}"


def apply_layer0_filter(df: pd.DataFrame, layer0_cfg: Dict[str, Any]) -> pd.DataFrame:
    """
    Applies the 12 adjustable Layer 0 Candidate Universe Pre-Filter criteria.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    mask = pd.Series(True, index=df.index)

    # 1. Min Market Cap ($ Billions)
    min_mc = float(layer0_cfg.get("min_market_cap_b", 3.0))
    if min_mc > 0:
        mask &= df["market_cap_b"].fillna(0.0) >= min_mc

    # 2. Max Market Cap ($ Billions, 0 = no limit)
    max_mc = float(layer0_cfg.get("max_market_cap_b", 0.0))
    if max_mc > 0:
        mask &= df["market_cap_b"].fillna(0.0) <= max_mc

    # 3. Min Share Price ($)
    min_price = float(layer0_cfg.get("min_price", 10.0))
    if min_price > 0:
        mask &= df["close"].fillna(0.0) >= min_price

    # 4-8. Multi-Horizon Share Volume Checks (1D, 10D, 30D, 60D, 90D)
    for col, cfg_key in [
        ("vol_1d", "min_vol_1d"),
        ("vol_10d", "min_vol_10d"),
        ("vol_30d", "min_vol_30d"),
        ("vol_60d", "min_vol_60d"),
        ("vol_90d", "min_vol_90d"),
    ]:
        min_vol = float(layer0_cfg.get(cfg_key, 500_000))
        if min_vol > 0 and col in df.columns:
            mask &= df[col].fillna(0.0) >= min_vol

    # 9. Min Dollar Volume (Price x Vol in $ Millions)
    min_dvol = float(layer0_cfg.get("min_dollar_vol_m", 50.0))
    if min_dvol > 0:
        mask &= df["dollar_vol_m"].fillna(0.0) >= min_dvol

    # 10. Exchanges (NYSE, NASDAQ, AMEX)
    exchanges = layer0_cfg.get("exchanges", ["NYSE", "NASDAQ", "AMEX"])
    if exchanges:
        mask &= df["exchange"].isin(exchanges)

    # 11. Exclude ETFs / Funds
    if bool(layer0_cfg.get("exclude_etfs", True)) and "is_etf_or_fund" in df.columns:
        mask &= ~df["is_etf_or_fund"].fillna(False)

    # 12. Include / Exclude Foreign ADRs
    if not bool(layer0_cfg.get("include_adrs", True)) and "is_adr" in df.columns:
        mask &= ~df["is_adr"].fillna(False)

    return df[mask].copy().reset_index(drop=True)


def evaluate_layer1_conditions(
    df_l0: pd.DataFrame,
    layer1_cfg: Dict[str, Any],
    sp500_benchmark: Dict[str, Any],
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Computes dynamic pool-wide RS Percentile (1-99) across the Layer 0 candidate pool
    and evaluates all 11 Layer 1 Trend & Momentum conditions.
    """
    if df_l0 is None or df_l0.empty:
        return pd.DataFrame(), {
            "active_condition_count": 0,
            "active_condition_ids": [],
            "y_1m_threshold_pct": 0.0,
            "y_6m_threshold_pct": 0.0,
            "lag_col_used": "sma_200_lag_20",
        }

    df = df_l0.copy()

    # Compute 1-99 Relative Strength Percentile against the current Layer 0 candidate pool
    if len(df) > 1:
        pct_rank = df["rs_raw_score"].rank(pct=True, ascending=True, na_option="bottom")
        df["rs_percentile"] = np.clip(np.ceil(pct_rank * 99.0), 1, 99).astype(int)
    else:
        df["rs_percentile"] = 99

    # Individual condition evaluation
    # C1: Close > SMA150 and Close > SMA200
    df["c1_pass"] = (df["close"] > df["sma_150"]) & (df["close"] > df["sma_200"])

    # C2: SMA150 > SMA200
    df["c2_pass"] = df["sma_150"] > df["sma_200"]

    # C3: SMA200 trending upward over N lookback trading days
    lookback_n = int(layer1_cfg.get("c3_lookback_days", 20))
    lag_col = _pick_nearest_lag_column(lookback_n)
    if lag_col not in df.columns:
        lag_col = "sma_200_lag_20"
    df["sma_200_lookback_val"] = df[lag_col]
    df["c3_pass"] = df["sma_200"] > df["sma_200_lookback_val"]

    # C4: SMA50 > SMA150 > SMA200
    df["c4_pass"] = (df["sma_50"] > df["sma_150"]) & (df["sma_150"] > df["sma_200"])

    # C5: Close > SMA50
    df["c5_pass"] = df["close"] > df["sma_50"]

    # C6: Close >= 52W Low * (1 + X%)
    min_above_low_pct = float(layer1_cfg.get("c6_min_pct_above_52w_low", 30.0))
    df["pct_above_52w_low"] = (((df["close"] / df["low_52w"]) - 1.0) * 100.0).round(2)
    df["c6_pass"] = df["pct_above_52w_low"] >= min_above_low_pct

    # C7: Close >= 52W High * (1 - Y%)  (i.e. within Y% below 52W high)
    max_below_high_pct = float(layer1_cfg.get("c7_max_pct_below_52w_high", 25.0))
    df["pct_below_52w_high"] = (((df["high_52w"] - df["close"]) / df["high_52w"]) * 100.0).round(2)
    df["c7_pass"] = df["pct_below_52w_high"] <= max_below_high_pct

    # C8: RS Percentile >= Min Qualifying Percentile (default 70)
    min_rs = int(layer1_cfg.get("c8_min_rs_percentile", 70))
    df["c8_pass"] = df["rs_percentile"] >= min_rs

    # C9: Short-term MA alignment: SMA10 >= SMA20
    df["c9_pass"] = df["sma_10"] >= df["sma_20"]

    # C10: 1M Perf > Dynamic S&P 500 1M threshold (2x when S&P >= 0, 0.5x when S&P < 0)
    sp500_1m = float((sp500_benchmark or {}).get("perf_1m_pct", 0.0))
    y_1m_thresh = compute_dynamic_sp500_threshold(
        sp500_return_pct=sp500_1m,
        use_dynamic=bool(layer1_cfg.get("c10_use_dynamic_sp500", True)),
        pos_mult=float(layer1_cfg.get("c10_pos_multiplier", 2.0)),
        neg_mult=float(layer1_cfg.get("c10_neg_multiplier", 0.5)),
        manual_pct=float(layer1_cfg.get("c10_manual_min_pct", 7.0)),
    )
    df["c10_pass"] = df["perf_1m"].fillna(-999.0) > y_1m_thresh

    # C11: 6M Perf > Dynamic S&P 500 6M threshold (2x when S&P >= 0, 0.5x when S&P < 0)
    sp500_6m = float((sp500_benchmark or {}).get("perf_6m_pct", 0.0))
    y_6m_thresh = compute_dynamic_sp500_threshold(
        sp500_return_pct=sp500_6m,
        use_dynamic=bool(layer1_cfg.get("c11_use_dynamic_sp500", True)),
        pos_mult=float(layer1_cfg.get("c11_pos_multiplier", 2.0)),
        neg_mult=float(layer1_cfg.get("c11_neg_multiplier", 0.5)),
        manual_pct=float(layer1_cfg.get("c11_manual_min_pct", 24.0)),
    )
    df["c11_pass"] = df["perf_6m"].fillna(-999.0) > y_6m_thresh

    # Count how many of the ENABLED conditions each stock passes
    active_ids: List[str] = []
    for meta in CONDITION_METADATA:
        cid = meta["id"]
        if bool(layer1_cfg.get(f"{cid}_enabled", True)):
            active_ids.append(cid)

    if active_ids:
        pass_cols = [f"{cid}_pass" for cid in active_ids]
        df["passed_count"] = df[pass_cols].astype(int).sum(axis=1)
        df["total_active"] = len(active_ids)
        df["qualified_all"] = df["passed_count"] == len(active_ids)
    else:
        df["passed_count"] = 0
        df["total_active"] = 0
        df["qualified_all"] = True

    df["pass_summary"] = df["passed_count"].astype(str) + " / " + df["total_active"].astype(str)

    # Sort by Passed Count (desc), then RS Percentile (desc), then Market Cap (desc)
    df = df.sort_values(
        by=["passed_count", "rs_percentile", "market_cap_b"],
        ascending=[False, False, False],
    ).reset_index(drop=True)

    summary_meta = {
        "active_condition_count": len(active_ids),
        "active_condition_ids": active_ids,
        "y_1m_threshold_pct": y_1m_thresh,
        "y_6m_threshold_pct": y_6m_thresh,
        "sp500_1m_pct": sp500_1m,
        "sp500_6m_pct": sp500_6m,
        "lag_col_used": lag_col,
        "layer0_count": len(df),
        "qualified_count": int(df["qualified_all"].sum()),
    }
    return df, summary_meta


def build_stock_condition_breakdown(
    row: pd.Series,
    layer1_cfg: Dict[str, Any],
    summary_meta: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Produces a human-readable, transparent 11-condition pass/fail table for any single stock.
    """
    lookback_n = int(layer1_cfg.get("c3_lookback_days", 20))
    min_above_low = float(layer1_cfg.get("c6_min_pct_above_52w_low", 30.0))
    max_below_high = float(layer1_cfg.get("c7_max_pct_below_52w_high", 25.0))
    min_rs = int(layer1_cfg.get("c8_min_rs_percentile", 70))
    y_1m = float(summary_meta.get("y_1m_threshold_pct", 0.0))
    y_6m = float(summary_meta.get("y_6m_threshold_pct", 0.0))

    details = [
        {
            "Condition": "C1: Price > SMA150 & SMA200",
            "Enabled": bool(layer1_cfg.get("c1_enabled", True)),
            "Passed": bool(row.get("c1_pass", False)),
            "Stock Value": f"Close ${row.get('close', 0):.2f} | SMA150 ${row.get('sma_150', 0):.2f} | SMA200 ${row.get('sma_200', 0):.2f}",
            "Required Threshold": "Close > SMA150 and SMA200",
        },
        {
            "Condition": "C2: SMA150 > SMA200",
            "Enabled": bool(layer1_cfg.get("c2_enabled", True)),
            "Passed": bool(row.get("c2_pass", False)),
            "Stock Value": f"SMA150 ${row.get('sma_150', 0):.2f} vs SMA200 ${row.get('sma_200', 0):.2f}",
            "Required Threshold": "SMA150 > SMA200",
        },
        {
            "Condition": f"C3: SMA200 Rising ({lookback_n}D Lookback)",
            "Enabled": bool(layer1_cfg.get("c3_enabled", True)),
            "Passed": bool(row.get("c3_pass", False)),
            "Stock Value": f"SMA200 Now ${row.get('sma_200', 0):.2f} vs {lookback_n}D Ago ${row.get('sma_200_lookback_val', 0):.2f}",
            "Required Threshold": f"SMA200 (Now) > SMA200 ({lookback_n}D Ago)",
        },
        {
            "Condition": "C4: SMA50 > SMA150 > SMA200",
            "Enabled": bool(layer1_cfg.get("c4_enabled", True)),
            "Passed": bool(row.get("c4_pass", False)),
            "Stock Value": f"SMA50 ${row.get('sma_50', 0):.2f} > SMA150 ${row.get('sma_150', 0):.2f} > SMA200 ${row.get('sma_200', 0):.2f}",
            "Required Threshold": "Perfect 50 > 150 > 200 Stacking",
        },
        {
            "Condition": "C5: Price > SMA50",
            "Enabled": bool(layer1_cfg.get("c5_enabled", True)),
            "Passed": bool(row.get("c5_pass", False)),
            "Stock Value": f"Close ${row.get('close', 0):.2f} vs SMA50 ${row.get('sma_50', 0):.2f}",
            "Required Threshold": "Close > SMA50",
        },
        {
            "Condition": "C6: Price Cleared 52W Low",
            "Enabled": bool(layer1_cfg.get("c6_enabled", True)),
            "Passed": bool(row.get("c6_pass", False)),
            "Stock Value": f"+{row.get('pct_above_52w_low', 0):.1f}% above 52W Low (${row.get('low_52w', 0):.2f})",
            "Required Threshold": f">= +{min_above_low:.1f}% above 52W Low",
        },
        {
            "Condition": "C7: Price Near 52W High",
            "Enabled": bool(layer1_cfg.get("c7_enabled", True)),
            "Passed": bool(row.get("c7_pass", False)),
            "Stock Value": f"{row.get('pct_below_52w_high', 0):.1f}% below 52W High (${row.get('high_52w', 0):.2f})",
            "Required Threshold": f"Within {max_below_high:.1f}% of 52W High",
        },
        {
            "Condition": "C8: Relative Strength (RS) Percentile",
            "Enabled": bool(layer1_cfg.get("c8_enabled", True)),
            "Passed": bool(row.get("c8_pass", False)),
            "Stock Value": f"RS {int(row.get('rs_percentile', 0))} (3M:{row.get('perf_3m', 0):+.1f}%, 6M:{row.get('perf_6m', 0):+.1f}%, 12M:{row.get('perf_12m', 0):+.1f}%)",
            "Required Threshold": f"RS Percentile >= {min_rs}",
        },
        {
            "Condition": "C9: Short-Term Alignment (SMA10 >= SMA20)",
            "Enabled": bool(layer1_cfg.get("c9_enabled", True)),
            "Passed": bool(row.get("c9_pass", False)),
            "Stock Value": f"SMA10 ${row.get('sma_10', 0):.2f} vs SMA20 ${row.get('sma_20', 0):.2f}",
            "Required Threshold": "SMA10 >= SMA20",
        },
        {
            "Condition": "C10: 1M Perf vs S&P 500 Benchmark",
            "Enabled": bool(layer1_cfg.get("c10_enabled", True)),
            "Passed": bool(row.get("c10_pass", False)),
            "Stock Value": f"{row.get('perf_1m', 0):+.2f}% (S&P 500 1M: {summary_meta.get('sp500_1m_pct', 0):+.2f}%)",
            "Required Threshold": f"> {y_1m:+.2f}%",
        },
        {
            "Condition": "C11: 6M Perf vs S&P 500 Benchmark",
            "Enabled": bool(layer1_cfg.get("c11_enabled", True)),
            "Passed": bool(row.get("c11_pass", False)),
            "Stock Value": f"{row.get('perf_6m', 0):+.2f}% (S&P 500 6M: {summary_meta.get('sp500_6m_pct', 0):+.2f}%)",
            "Required Threshold": f"> {y_6m:+.2f}%",
        },
    ]
    return details
