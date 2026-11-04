"""
Core configuration constants, default filter thresholds, and condition metadata.
"""

from __future__ import annotations

import re
from typing import Dict, Any, List

ALL_EXCHANGES: List[str] = ["NYSE", "NASDAQ", "AMEX"]

# Optional TradingView saved chart layout ID or full URL for "BKCHO Chart"
DEFAULT_TV_LAYOUT_ID: str = ""

# Baseline floor used when fetching the daily universe cache so the user can lower
# Market Cap (e.g. from $3B down to $500M) or Volume in the UI and re-filter in <1s.
BASELINE_CACHE_MIN_MKT_CAP_B: float = 0.5  # $500M floor for cached universe
BASELINE_CACHE_MIN_PRICE: float = 5.0      # $5 floor for cached universe
BASELINE_CACHE_MIN_VOL: int = 100_000      # 100K volume floor for cached universe


def get_default_layer0_config() -> Dict[str, Any]:
    """
    Default Layer 0 Pre-Filter matching Bryan's TradingView setup:
    - Market Cap >= $3.0B, Price >= $10
    - 1D, 10D, 30D, 60D, 90D Volume > 500,000 shares
    - Dollar Volume (Price x Vol) > $50M
    - US Major Exchanges (NYSE, NASDAQ, AMEX), Exclude ETFs, Include ADRs
    """
    return {
        "min_market_cap_b": 3.0,
        "max_market_cap_b": 0.0,
        "min_price": 10.0,
        "min_vol_1d": 500_000,
        "min_vol_10d": 500_000,
        "min_vol_30d": 500_000,
        "min_vol_60d": 500_000,
        "min_vol_90d": 500_000,
        "min_dollar_vol_m": 50.0,
        "exchanges": ["NYSE", "NASDAQ", "AMEX"],
        "exclude_etfs": True,
        "include_adrs": True,
    }


def get_default_layer1_config() -> Dict[str, Any]:
    """
    Default Layer 1 Extended 11-Condition Trend & Momentum Template:
    - Conditions 1 to 8: Mark Minervini's Trend Template
    - Condition 9: SMA 10 >= SMA 20 (Short-term swing alignment)
    - Condition 10: 1M Performance > Y_1M% (Dynamic 2.0x / 0.5x S&P 500 1M return)
    - Condition 11: 6M Performance > Y_6M% (Dynamic 2.0x / 0.5x S&P 500 6M return)
    """
    return {
        "c1_enabled": True,
        "c2_enabled": True,
        "c3_enabled": True,
        "c4_enabled": True,
        "c5_enabled": True,
        "c6_enabled": True,
        "c7_enabled": True,
        "c8_enabled": True,
        "c9_enabled": True,
        "c10_enabled": True,
        "c11_enabled": True,
        "c3_lookback_days": 20,
        "c6_min_pct_above_52w_low": 30.0,
        "c7_max_pct_below_52w_high": 25.0,
        "c8_min_rs_percentile": 70,
        "c10_use_dynamic_sp500": True,
        "c10_pos_multiplier": 2.0,
        "c10_neg_multiplier": 0.5,
        "c10_manual_min_pct": 7.0,
        "c11_use_dynamic_sp500": True,
        "c11_pos_multiplier": 2.0,
        "c11_neg_multiplier": 0.5,
        "c11_manual_min_pct": 24.0,
    }


def compute_dynamic_sp500_threshold(
    sp500_return_pct: float,
    use_dynamic: bool,
    pos_mult: float,
    neg_mult: float,
    manual_pct: float,
) -> float:
    """
    Calculates the required return threshold Y%:
    - If use_dynamic is False, returns manual_pct.
    - If sp500_return_pct >= 0: Y = pos_mult * sp500_return_pct (e.g., 2.0 * 3% = 6%)
    - If sp500_return_pct < 0:  Y = neg_mult * sp500_return_pct (e.g., 0.5 * -4% = -2%)
    """
    if not use_dynamic:
        return round(float(manual_pct), 2)
    if sp500_return_pct >= 0:
        return round(float(sp500_return_pct) * float(pos_mult), 2)
    return round(float(sp500_return_pct) * float(neg_mult), 2)


def extract_tv_layout_id(raw_input: str) -> str:
    """
    Extracts the TradingView Layout ID from either a full URL like:
    `https://www.tradingview.com/chart/AbCdEf12/?symbol=NASDAQ:BEAM`
    or a bare layout ID like `AbCdEf12`.
    """
    s = (raw_input or "").strip()
    if not s:
        return ""
    m = re.search(r"tradingview\.com/chart/([A-Za-z0-9_\-]+)", s)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_\-]{4,20}", s):
        return s
    return ""


def build_tv_chart_url(exchange: str, ticker: str, layout_id: str) -> str:
    """Builds a direct TradingView chart link (optionally using the user's BKCHO Chart layout ID)."""
    clean_id = extract_tv_layout_id(layout_id)
    sym_param = f"{exchange}%3A{ticker}"
    if clean_id:
        return f"https://www.tradingview.com/chart/{clean_id}/?symbol={sym_param}"
    return f"https://www.tradingview.com/chart/?symbol={sym_param}"


CONDITION_METADATA: List[Dict[str, str]] = [
    {
        "id": "c1",
        "short_name": "C1: Price > SMA150 & SMA200",
        "description": "Current price is above both medium-term (150D) and long-term (200D) moving averages.",
    },
    {
        "id": "c2",
        "short_name": "C2: SMA150 > SMA200",
        "description": "Medium-term (150D) moving average is above long-term (200D) moving average.",
    },
    {
        "id": "c3",
        "short_name": "C3: SMA200 Trending Up",
        "description": "Long-term (200D) moving average is higher than N trading days ago.",
    },
    {
        "id": "c4",
        "short_name": "C4: SMA50 > SMA150 > SMA200",
        "description": "Short-, medium-, and long-term moving averages are in stacked bullish alignment.",
    },
    {
        "id": "c5",
        "short_name": "C5: Price > SMA50",
        "description": "Current price is above the short-term (50D) moving average.",
    },
    {
        "id": "c6",
        "short_name": "C6: Price >= 52W Low + X%",
        "description": "Current price has pulled sufficiently above its 52-week low.",
    },
    {
        "id": "c7",
        "short_name": "C7: Price Near 52W High",
        "description": "Current price is within Y% of its 52-week high.",
    },
    {
        "id": "c8",
        "short_name": "C8: RS Percentile >= P",
        "description": "Weighted 3/6/9/12M Relative Strength percentile ranking against the candidate pool.",
    },
    {
        "id": "c9",
        "short_name": "C9: SMA10 >= SMA20",
        "description": "Short-term swing moving average alignment (10D SMA >= 20D SMA).",
    },
    {
        "id": "c10",
        "short_name": "C10: 1M Perf vs S&P 500",
        "description": "1-Month performance exceeds dynamic S&P 500 benchmark threshold (2x up / 0.5x down).",
    },
    {
        "id": "c11",
        "short_name": "C11: 6M Perf vs S&P 500",
        "description": "6-Month performance exceeds dynamic S&P 500 benchmark threshold (2x up / 0.5x down).",
    },
]
