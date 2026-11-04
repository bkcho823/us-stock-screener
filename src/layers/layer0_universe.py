"""
Layer 0 — Candidate Universe Pre-Filter.
Applies the 12 adjustable baseline liquidity, capitalization, price, and exchange criteria:
- Min / Max Market Cap ($B)
- Min Share Price ($)
- Multi-Horizon Share Volume (1D, 10D, 30D, 60D, 90D)
- Min Daily Dollar Volume (Price x Vol in $M)
- US Major Exchanges (NYSE, NASDAQ, AMEX)
- Exclude ETFs/Funds & Include/Exclude Foreign ADRs
"""

from __future__ import annotations

from typing import Dict, Any

import pandas as pd


def apply_layer0_filter(df: pd.DataFrame, layer0_cfg: Dict[str, Any]) -> pd.DataFrame:
    """
    Applies the 12 adjustable Layer 0 Candidate Universe Pre-Filter criteria.
    Pure Python/Pandas logic with zero UI dependencies.
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
