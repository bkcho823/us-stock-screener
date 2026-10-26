"""
Default configurations, presets, and condition definitions for:
- Layer 0: Candidate Universe Pre-Filter (12 adjustable controls)
- Layer 1: Extended 11-Condition Trend & Momentum Template
"""

from pathlib import Path
from typing import Dict, Any, List

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

SNAPSHOT_FILE = DATA_DIR / "daily_snapshot.parquet"
BENCHMARK_FILE = DATA_DIR / "benchmark_sp500.json"
PRESETS_FILE = DATA_DIR / "presets.json"
RUN_HISTORY_FILE = DATA_DIR / "run_history.json"

ALL_EXCHANGES: List[str] = ["NYSE", "NASDAQ", "AMEX"]

# Baseline floor used when fetching the daily universe cache so the user can lower
# Market Cap (e.g. from $3B down to $500M) or Volume in the UI and re-filter in <1s
# without needing to re-download from the network.
BASELINE_CACHE_MIN_MKT_CAP_B: float = 0.5  # $500M floor for cached universe
BASELINE_CACHE_MIN_PRICE: float = 5.0      # $5 floor for cached universe
BASELINE_CACHE_MIN_VOL: int = 100_000      # 100K volume floor for cached universe


def get_default_layer0_config() -> Dict[str, Any]:
    """
    Default Layer 0 Pre-Filter matching Bryan's TradingView setup:
    - Market Cap >= $3.0B
    - Price >= $10
    - 1D, 10D, 30D, 60D, 90D Volume > 500,000 shares
    - Dollar Volume (Price x Vol) > $50M
    - US Major Exchanges (NYSE, NASDAQ, AMEX), Exclude ETFs, Include ADRs
    """
    return {
        "min_market_cap_b": 3.0,        # $ Billions (adjustable e.g. 2.0 -> 3.0)
        "max_market_cap_b": 0.0,        # 0.0 means No Upper Limit
        "min_price": 10.0,              # USD
        "min_vol_1d": 500_000,          # Current day volume (shares)
        "min_vol_10d": 500_000,         # 10D average volume (shares)
        "min_vol_30d": 500_000,         # 30D average volume (shares)
        "min_vol_60d": 500_000,         # 60D average volume (shares)
        "min_vol_90d": 500_000,         # 90D average volume (shares)
        "min_dollar_vol_m": 50.0,       # Price x Volume in $ Millions
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
        # Independent ON/OFF toggles for all 11 conditions
        "c1_enabled": True,   # Close > SMA150 and Close > SMA200
        "c2_enabled": True,   # SMA150 > SMA200
        "c3_enabled": True,   # SMA200 trending up over N lookback trading days
        "c4_enabled": True,   # SMA50 > SMA150 > SMA200
        "c5_enabled": True,   # Close > SMA50
        "c6_enabled": True,   # Close >= 52W Low * (1 + min_pct_above_52w_low / 100)
        "c7_enabled": True,   # Close >= 52W High * (1 - max_pct_below_52w_high / 100)
        "c8_enabled": True,   # RS Percentile >= min_rs_percentile
        "c9_enabled": True,   # SMA10 >= SMA20
        "c10_enabled": True,  # 1M Perf > Dynamic S&P 500 1M threshold
        "c11_enabled": True,  # 6M Perf > Dynamic S&P 500 6M threshold

        # Adjustable numeric thresholds for Layer 1
        "c3_lookback_days": 20,           # Default ~1 month (20 trading days); supports 5, 10, 20, 30, 40, 60
        "c6_min_pct_above_52w_low": 30.0, # Default 30% above 52W low
        "c7_max_pct_below_52w_high": 25.0,# Default within 25% of 52W high
        "c8_min_rs_percentile": 70,       # Default 70th percentile (1-99)

        # Dynamic S&P 500 Outperformance Settings (Conditions 10 & 11)
        "c10_use_dynamic_sp500": True,
        "c10_pos_multiplier": 2.0,        # 2x when S&P 500 1M >= 0%
        "c10_neg_multiplier": 0.5,        # 0.5x when S&P 500 1M < 0% (holds up twice as well)
        "c10_manual_min_pct": 7.0,        # Used if manual override is selected (TradingView default: 7%)

        "c11_use_dynamic_sp500": True,
        "c11_pos_multiplier": 2.0,        # 2x when S&P 500 6M >= 0%
        "c11_neg_multiplier": 0.5,        # 0.5x when S&P 500 6M < 0%
        "c11_manual_min_pct": 24.0,       # Used if manual override is selected (TradingView default: 24%)
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


BUILTIN_PRESETS: Dict[str, Dict[str, Any]] = {
    "Bryan's Full Setup ($3B + 500K Vol + $50M DolVol + All 11 Rules)": {
        "description": "Combines your TradingView Layer 0 ($3B Mkt Cap, 500K 1D/10D/30D/60D/90D Vol, $50M Dollar Vol) with all 8 Minervini Trend Template rules + SMA10>=SMA20 + Dynamic S&P 500 1M/6M.",
        "layer0": get_default_layer0_config(),
        "layer1": get_default_layer1_config(),
    },
    "Bryan's Current TradingView Filter ($3B + TV Rules Only)": {
        "description": "Matches your exact TradingView screenshot: Layer 0 ($3B, 500K Vol, $50M DolVol) + Price > SMA200, SMA10 >= SMA20, and 1M & 6M Outperformance (with other Minervini rules toggled off).",
        "layer0": get_default_layer0_config(),
        "layer1": {
            **get_default_layer1_config(),
            "c1_enabled": True,   # Close > SMA200 (and SMA150)
            "c2_enabled": False,
            "c3_enabled": False,
            "c4_enabled": False,
            "c5_enabled": False,
            "c6_enabled": False,
            "c7_enabled": False,
            "c8_enabled": False,
            "c9_enabled": True,   # SMA10 >= SMA20
            "c10_enabled": True,  # 1M Perf > Y%
            "c11_enabled": True,  # 6M Perf > Y%
        },
    },
    "BRD Classic Minervini ($2B Mkt Cap + 8 Core Trend Rules)": {
        "description": "Original BRD baseline: Market Cap >= $2B, 300K Volume, and the classic 8 Mark Minervini Trend Template conditions.",
        "layer0": {
            **get_default_layer0_config(),
            "min_market_cap_b": 2.0,
            "min_vol_1d": 300_000,
            "min_vol_10d": 300_000,
            "min_vol_30d": 300_000,
            "min_vol_60d": 300_000,
            "min_vol_90d": 300_000,
            "min_dollar_vol_m": 20.0,
        },
        "layer1": {
            **get_default_layer1_config(),
            "c9_enabled": False,
            "c10_enabled": False,
            "c11_enabled": False,
        },
    },
}
