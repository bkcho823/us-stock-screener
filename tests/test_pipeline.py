"""
End-to-End Unit Tests for the Pluggable Screening Pipeline (`src/layers/pipeline.py`).
"""

import unittest
import pandas as pd

from src.config import get_default_layer0_config, get_default_layer1_config
from src.layers import run_screening_pipeline, ScreeningPipelineResult


class TestScreeningPipeline(unittest.TestCase):
    def test_pipeline_execution_returns_structured_result(self) -> None:
        df_universe = pd.DataFrame(
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
                    "ticker": "TINY",
                    "company_name": "Tiny Microcap",
                    "exchange": "NASDAQ",
                    "sector": "Technology",
                    "is_etf_or_fund": False,
                    "is_adr": False,
                    "market_cap_b": 0.6,
                    "close": 12.0,
                    "vol_1d": 200_000,
                    "vol_10d": 200_000,
                    "vol_30d": 200_000,
                    "vol_60d": 200_000,
                    "vol_90d": 200_000,
                    "dollar_vol_m": 2.4,
                    "sma_10": 12.0,
                    "sma_20": 11.0,
                    "sma_50": 10.0,
                    "sma_150": 9.0,
                    "sma_200": 8.0,
                    "sma_200_lag_20": 7.5,
                    "low_52w": 6.0,
                    "high_52w": 12.5,
                    "perf_1m": 15.0,
                    "perf_3m": 25.0,
                    "perf_6m": 50.0,
                    "perf_9m": 60.0,
                    "perf_12m": 80.0,
                    "rs_raw_score": 48.0,
                },
            ]
        )

        res = run_screening_pipeline(
            df_universe=df_universe,
            sp500_bm={"perf_1m_pct": 2.0, "perf_6m_pct": 8.0},
            layer0_cfg=get_default_layer0_config(),
            layer1_cfg=get_default_layer1_config(),
        )
        self.assertIsInstance(res, ScreeningPipelineResult)
        self.assertEqual(len(res.df_l0), 1)
        self.assertEqual(res.df_scored.iloc[0]["ticker"], "NVDA")
        self.assertEqual(res.summary_meta["qualified_count"], 1)
        self.assertGreaterEqual(res.elapsed_ms, 0.0)


if __name__ == "__main__":
    unittest.main()
