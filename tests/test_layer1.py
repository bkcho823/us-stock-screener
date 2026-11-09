"""
Unit Tests for Layer 1 (`src/layers/layer1_trend.py`) — 11-Condition Trend & Momentum Engine,
Dynamic S&P 500 Multiplier, Pool-Wide RS Percentile, and URL Helpers.
"""

import unittest
import pandas as pd

from src.config import (
    get_default_layer1_config,
    compute_dynamic_sp500_threshold,
    extract_tv_layout_id,
    build_tv_chart_url,
)
from src.layers.layer1_trend import (
    evaluate_layer1_conditions,
    build_stock_condition_breakdown,
)


class TestLayer1Trend(unittest.TestCase):
    def test_dynamic_sp500_thresholds(self) -> None:
        self.assertEqual(compute_dynamic_sp500_threshold(3.0, True, 2.0, 0.5, 7.0), 6.0)
        self.assertEqual(compute_dynamic_sp500_threshold(-4.0, True, 2.0, 0.5, 7.0), -2.0)
        self.assertEqual(compute_dynamic_sp500_threshold(3.0, False, 2.0, 0.5, 7.5), 7.5)

    def test_tv_layout_url_helpers(self) -> None:
        self.assertEqual(
            extract_tv_layout_id("https://www.tradingview.com/chart/AbCdEf12/?symbol=NASDAQ:NVDA"),
            "AbCdEf12",
        )
        self.assertEqual(extract_tv_layout_id("XyZ98765"), "XyZ98765")
        self.assertEqual(
            build_tv_chart_url("NASDAQ", "NVDA", "AbCdEf12"),
            "https://www.tradingview.com/chart/AbCdEf12/?symbol=NASDAQ%3ANVDA",
        )

    def test_evaluate_layer1_conditions_and_breakdown(self) -> None:
        df_l0 = pd.DataFrame(
            [
                {
                    "ticker": "NVDA",
                    "company_name": "NVIDIA Corp",
                    "exchange": "NASDAQ",
                    "sector": "Technology",
                    "market_cap_b": 3100.0,
                    "close": 140.0,
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
                    "ticker": "LAGG",
                    "company_name": "Laggard Corp",
                    "exchange": "NYSE",
                    "sector": "Industrials",
                    "market_cap_b": 12.0,
                    "close": 55.0,
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

        l1 = get_default_layer1_config()
        sp500_bm = {"perf_1m_pct": 3.0, "perf_6m_pct": 10.0}
        df_scored, meta = evaluate_layer1_conditions(df_l0, l1, sp500_bm)

        self.assertEqual(meta["y_1m_threshold_pct"], 6.0)
        self.assertEqual(meta["y_6m_threshold_pct"], 20.0)
        self.assertEqual(meta["qualified_count"], 1)

        nvda_row = df_scored[df_scored["ticker"] == "NVDA"].iloc[0]
        self.assertTrue(bool(nvda_row["qualified_all"]))
        self.assertEqual(int(nvda_row["passed_count"]), 11)

        breakdown = build_stock_condition_breakdown(nvda_row, l1, meta)
        self.assertEqual(len(breakdown), 11)

    def test_ipo_lifecycle_stage2_mode(self) -> None:
        df_ipo = pd.DataFrame(
            [
                {
                    "ticker": "RDDT",
                    "company_name": "Reddit Inc",
                    "exchange": "NYSE",
                    "sector": "Technology",
                    "market_cap_b": 10.5,
                    "close": 65.0,
                    "sma_10": 63.0,
                    "sma_20": 60.0,
                    "ema_21": 60.5,
                    "sma_50": 54.0,
                    "sma_150": float("nan"),
                    "sma_200": float("nan"),
                    "sma_200_lag_20": float("nan"),
                    "bars_count": 75,
                    "low_52w": 38.0,
                    "high_52w": 67.0,
                    "perf_1m": 14.0,
                    "perf_3m": 42.0,
                    "perf_6m": float("nan"),
                    "rs_raw_score": 88.0,
                }
            ]
        )
        l1 = get_default_layer1_config()
        l1["ipo_mode_enabled"] = True
        l1["c8_min_rs_percentile"] = 50
        sp500_bm = {"perf_1m_pct": 2.0, "perf_6m_pct": 8.0}
        df_scored, meta = evaluate_layer1_conditions(df_ipo, l1, sp500_bm)
        rddt = df_scored.iloc[0]
        self.assertTrue(bool(rddt["is_ipo_stage2"]))
        self.assertTrue(bool(rddt["qualified_all"]))


if __name__ == "__main__":
    unittest.main()
