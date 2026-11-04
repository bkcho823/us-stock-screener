"""
Unit Tests for Layer 0 (`src/layers/layer0_universe.py`) — Candidate Universe Pre-Filter.
"""

import unittest
import pandas as pd

from src.config import get_default_layer0_config
from src.layers.layer0_universe import apply_layer0_filter


class TestLayer0Universe(unittest.TestCase):
    def setUp(self) -> None:
        self.sample_df = pd.DataFrame(
            [
                {
                    "ticker": "NVDA",
                    "exchange": "NASDAQ",
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
                },
                {
                    "ticker": "MIDC",
                    "exchange": "NYSE",
                    "is_etf_or_fund": False,
                    "is_adr": False,
                    "market_cap_b": 2.4,
                    "close": 55.0,
                    "vol_1d": 800_000,
                    "vol_10d": 750_000,
                    "vol_30d": 700_000,
                    "vol_60d": 680_000,
                    "vol_90d": 650_000,
                    "dollar_vol_m": 44.0,
                },
                {
                    "ticker": "QQQ",
                    "exchange": "NASDAQ",
                    "is_etf_or_fund": True,
                    "is_adr": False,
                    "market_cap_b": 250.0,
                    "close": 480.0,
                    "vol_1d": 30_000_000,
                    "vol_10d": 30_000_000,
                    "vol_30d": 30_000_000,
                    "vol_60d": 30_000_000,
                    "vol_90d": 30_000_000,
                    "dollar_vol_m": 14400.0,
                },
                {
                    "ticker": "TSM",
                    "exchange": "NYSE",
                    "is_etf_or_fund": False,
                    "is_adr": True,
                    "market_cap_b": 900.0,
                    "close": 190.0,
                    "vol_1d": 15_000_000,
                    "vol_10d": 15_000_000,
                    "vol_30d": 15_000_000,
                    "vol_60d": 15_000_000,
                    "vol_90d": 15_000_000,
                    "dollar_vol_m": 2850.0,
                },
            ]
        )

    def test_default_layer0_filters_etfs_and_small_caps(self) -> None:
        cfg = get_default_layer0_config()
        out = apply_layer0_filter(self.sample_df, cfg)
        self.assertEqual(out["ticker"].tolist(), ["NVDA", "TSM"])

    def test_relaxed_market_cap_and_exclude_adrs(self) -> None:
        cfg = {
            **get_default_layer0_config(),
            "min_market_cap_b": 2.0,
            "min_dollar_vol_m": 40.0,
            "include_adrs": False,
        }
        out = apply_layer0_filter(self.sample_df, cfg)
        self.assertEqual(out["ticker"].tolist(), ["NVDA", "MIDC"])


if __name__ == "__main__":
    unittest.main()
