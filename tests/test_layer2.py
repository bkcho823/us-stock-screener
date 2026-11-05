"""
Unit Tests for Layer 2 (`src/layers/layer2_sector.py`) — Industry & Sector Rotation Engine,
Leadership Ranking, Composite Scoring, and Lone Wolf Exemption.
"""

import unittest
import pandas as pd

from src.config import get_default_layer2_config
from src.layers.layer2_sector import (
    compute_group_momentum_rankings,
    evaluate_layer2_momentum_and_sector,
)


class TestLayer2Sector(unittest.TestCase):
    def setUp(self) -> None:
        # Sample Layer 0 Universe pool for industry benchmark calculations
        self.df_l0 = pd.DataFrame([
            {"ticker": "NVDA", "industry": "Semiconductors", "sector": "Technology", "close": 140, "sma_50": 130, "perf_1m": 12.0, "perf_3m": 35.0, "perf_6m": 60.0},
            {"ticker": "AVGO", "industry": "Semiconductors", "sector": "Technology", "close": 170, "sma_50": 160, "perf_1m": 10.0, "perf_3m": 25.0, "perf_6m": 45.0},
            {"ticker": "AMD", "industry": "Semiconductors", "sector": "Technology", "close": 150, "sma_50": 145, "perf_1m": 8.0, "perf_3m": 20.0, "perf_6m": 40.0},
            {"ticker": "AXON", "industry": "Defense", "sector": "Industrials", "close": 420, "sma_50": 390, "perf_1m": 2.0, "perf_3m": 5.0, "perf_6m": 10.0},
            {"ticker": "RTX", "industry": "Defense", "sector": "Industrials", "close": 120, "sma_50": 115, "perf_1m": 1.0, "perf_3m": 4.0, "perf_6m": 8.0},
            {"ticker": "SLOW", "industry": "Retail", "sector": "Consumer", "close": 20, "sma_50": 22, "perf_1m": -5.0, "perf_3m": -10.0, "perf_6m": -15.0},
        ])

        # Layer 1 scored output
        self.df_l1 = pd.DataFrame([
            {
                "ticker": "NVDA", "company_name": "Nvidia", "industry": "Semiconductors", "sector": "Technology",
                "rs_percentile": 98, "qualified_all": True, "passed_count": 11, "close": 140, "exchange": "NASDAQ", "market_cap_b": 3000
            },
            {
                "ticker": "AVGO", "company_name": "Broadcom", "industry": "Semiconductors", "sector": "Technology",
                "rs_percentile": 88, "qualified_all": True, "passed_count": 11, "close": 170, "exchange": "NASDAQ", "market_cap_b": 800
            },
            {
                "ticker": "AXON", "company_name": "Axon", "industry": "Defense", "sector": "Industrials",
                "rs_percentile": 94, "qualified_all": True, "passed_count": 11, "close": 420, "exchange": "NASDAQ", "market_cap_b": 35
            },
            {
                "ticker": "SLOW", "company_name": "Slow Retail", "industry": "Retail", "sector": "Consumer",
                "rs_percentile": 72, "qualified_all": True, "passed_count": 11, "close": 20, "exchange": "NYSE", "market_cap_b": 5
            },
        ])

    def test_group_momentum_rankings(self) -> None:
        ind_rs, sector_rs, leaderboard = compute_group_momentum_rankings(self.df_l0)
        self.assertIn("Semiconductors", ind_rs)
        self.assertIn("Defense", ind_rs)
        # Semiconductors had the highest returns (1M: 12%, 3M: 35%, 6M: 60%)
        self.assertGreater(ind_rs["Semiconductors"], ind_rs["Retail"])
        self.assertEqual(len(leaderboard), 3)

    def test_layer2_gate_and_lone_wolf_override(self) -> None:
        l2_cfg = get_default_layer2_config()
        # Top 40% Industry requirement (min group rs >= 60)
        l2_cfg["top_group_pct"] = 40.0
        l2_cfg["lone_wolf_enabled"] = True
        l2_cfg["lone_wolf_min_rs"] = 90

        df_out, meta = evaluate_layer2_momentum_and_sector(self.df_l1, self.df_l0, l2_cfg)

        self.assertIn("composite_score", df_out.columns)
        self.assertIn("l2_qualified", df_out.columns)
        self.assertIn("is_lone_wolf", df_out.columns)

        # NVDA in top industry should qualify
        nvda = df_out[df_out["ticker"] == "NVDA"].iloc[0]
        self.assertTrue(nvda["l2_qualified"])
        self.assertTrue(nvda["pass_group_gate"])
        self.assertEqual(nvda["rank_in_group"], 1)

        # AXON has individual RS 94 (>= 90), so even if Defense is not in top 40%, it passes via Lone Wolf
        axon = df_out[df_out["ticker"] == "AXON"].iloc[0]
        self.assertTrue(axon["l2_qualified"])
        if not axon["pass_group_gate"]:
            self.assertTrue(axon["is_lone_wolf"])

        # SLOW has RS 72 and is in Retail (weakest), should fail L2 gate
        slow = df_out[df_out["ticker"] == "SLOW"].iloc[0]
        self.assertFalse(slow["l2_qualified"])


if __name__ == "__main__":
    unittest.main()
