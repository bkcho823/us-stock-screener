"""
Unit and end-to-end verification tests for Layer 0 Pre-Filter, Dynamic S&P 500 Multiplier,
Pool-wide Relative Strength (RS) Percentile, and Layer 1 11-Condition Trend Template.
"""

import pandas as pd
from src.config import (
    get_default_layer0_config,
    get_default_layer1_config,
    compute_dynamic_sp500_threshold,
)
from src.screener_engine import (
    apply_layer0_filter,
    evaluate_layer1_conditions,
    build_stock_condition_breakdown,
)


def test_dynamic_sp500_thresholds():
    # Positive S&P 500 return (+3.0%) -> 2.0x = +6.0%
    assert compute_dynamic_sp500_threshold(3.0, True, 2.0, 0.5, 7.0) == 6.0
    # Negative S&P 500 return (-4.0%) -> 0.5x = -2.0%
    assert compute_dynamic_sp500_threshold(-4.0, True, 2.0, 0.5, 7.0) == -2.0
    # Manual override
    assert compute_dynamic_sp500_threshold(3.0, False, 2.0, 0.5, 7.5) == 7.5


def test_layer0_and_layer1_end_to_end():
    sample_data = pd.DataFrame(
        [
            {
                "ticker": "NVDA",
                "company_name": "NVIDIA Corp",
                "exchange": "NASDAQ",
                "sector": "Technology",
                "is_etf_or_fund": False,
                "is_adr": False,
                "market_cap_b": 3100.0,
                "close": 140.0,
                "vol_1d": 45_000_000,
                "vol_10d": 48_000_000,
                "vol_30d": 50_000_000,
                "vol_60d": 52_000_000,
                "vol_90d": 55_000_000,
                "dollar_vol_m": 6300.0,
                "sma_10": 138.0,
                "sma_20": 134.0,
                "sma_50": 128.0,
                "sma_150": 115.0,
                "sma_200": 105.0,
                "sma_200_lag_20": 98.0,
                "low_52w": 75.0,
                "high_52w": 143.0,
                "perf_1m": 9.5,
                "perf_3m": 22.0,
                "perf_6m": 45.0,
                "perf_9m": 80.0,
                "perf_12m": 130.0,
                "rs_raw_score": 59.8,
            },
            {
                "ticker": "MIDC",
                "company_name": "MidCap Example Inc",
                "exchange": "NYSE",
                "sector": "Industrials",
                "is_etf_or_fund": False,
                "is_adr": False,
                "market_cap_b": 2.4,  # Between $2B and $3B to test Market Cap slider
                "close": 55.0,
                "vol_1d": 800_000,
                "vol_10d": 750_000,
                "vol_30d": 700_000,
                "vol_60d": 680_000,
                "vol_90d": 650_000,
                "dollar_vol_m": 44.0,
                "sma_10": 54.0,
                "sma_20": 52.0,
                "sma_50": 50.0,
                "sma_150": 46.0,
                "sma_200": 42.0,
                "sma_200_lag_20": 40.0,
                "low_52w": 35.0,
                "high_52w": 58.0,
                "perf_1m": 4.0,
                "perf_3m": 10.0,
                "perf_6m": 15.0,
                "perf_9m": 20.0,
                "perf_12m": 25.0,
                "rs_raw_score": 16.0,
            },
        ]
    )

    l0 = get_default_layer0_config()  # Default min_market_cap_b = 3.0B, min_dollar_vol_m = 50M
    df_l0_strict = apply_layer0_filter(sample_data, l0)
    assert len(df_l0_strict) == 1
    assert df_l0_strict.iloc[0]["ticker"] == "NVDA"

    # Change Market Cap from 3B to 2B and Dollar Vol to 40M -> Both pass Layer 0
    l0_relaxed = {**l0, "min_market_cap_b": 2.0, "min_dollar_vol_m": 40.0}
    df_l0_both = apply_layer0_filter(sample_data, l0_relaxed)
    assert len(df_l0_both) == 2

    # Evaluate Layer 1 with S&P 500 1M = +3.0% (Target +6.0%) and 6M = +10.0% (Target +20.0%)
    l1 = get_default_layer1_config()
    sp500_bm = {"perf_1m_pct": 3.0, "perf_6m_pct": 10.0}
    df_scored, meta = evaluate_layer1_conditions(df_l0_both, l1, sp500_bm)

    assert meta["y_1m_threshold_pct"] == 6.0
    assert meta["y_6m_threshold_pct"] == 20.0
    assert meta["qualified_count"] == 1  # NVDA passes all 11/11; MIDC fails C8, C10, C11

    nvda_row = df_scored[df_scored["ticker"] == "NVDA"].iloc[0]
    assert bool(nvda_row["qualified_all"]) is True
    assert int(nvda_row["passed_count"]) == 11

    breakdown = build_stock_condition_breakdown(nvda_row, l1, meta)
    assert len(breakdown) == 11
    print("All Layer 0 & Layer 1 unit tests passed!")


if __name__ == "__main__":
    test_dynamic_sp500_thresholds()
    test_layer0_and_layer1_end_to_end()
