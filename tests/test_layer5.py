"""
Unit Tests for Layer 5: Risk Management & Position Sizing Calculator.
"""

import unittest
import pandas as pd

from src.layers.layer5_risk import evaluate_layer5_position_sizing


class TestLayer5Risk(unittest.TestCase):
    def setUp(self) -> None:
        self.df_mock = pd.DataFrame([
            {
                "ticker": "NORMAL",
                "close": 100.00,
                "last_contraction_pct": 5.0,
                "ema_20": 97.00,
                "qualified_all": True,
                "l2_qualified": True,
                "l3_qualified": True,
                "l4_qualified": True,
            },
            {
                "ticker": "WIDE_STOP",
                "close": 50.00,
                "last_contraction_pct": 12.0,  # Wide contraction
                "ema_20": 42.00,
                "qualified_all": True,
                "l2_qualified": True,
                "l3_qualified": True,
                "l4_qualified": True,
            },
            {
                "ticker": "TIGHT_RISK",
                "close": 200.00,
                "last_contraction_pct": 3.0,
                "ema_20": 198.00,
                "qualified_all": True,
                "l2_qualified": True,
                "l3_qualified": True,
                "l4_qualified": True,
            },
        ])

    def test_evaluate_layer5_position_sizing_and_risk(self) -> None:
        cfg = {
            "l5_enabled": True,
            "risk_gate_enabled": True,
            "account_equity": 100000.0,
            "max_risk_pct_per_trade": 1.0,  # $1,000 risk budget
            "max_stop_loss_pct": 7.0,
            "min_reward_risk_ratio": 2.5,
            "max_portfolio_allocation_pct": 25.0,  # $25,000 max capital
        }

        df_out, meta = evaluate_layer5_position_sizing(self.df_mock, cfg)

        self.assertEqual(meta["account_equity"], 100000.0)
        self.assertEqual(meta["max_dollar_risk"], 1000.0)
        self.assertEqual(meta["max_capital_allocation"], 25000.0)

        # 1. NORMAL stock ($100 close)
        row_norm = df_out[df_out["ticker"] == "NORMAL"].iloc[0]
        # Risk % must be <= 7.0%
        self.assertLessEqual(row_norm["risk_pct"], 7.0)
        # Position value must be <= $25,000 (cap)
        self.assertLessEqual(row_norm["position_value"], 25000.0)
        # Dollar risk per share * recommended shares should be ~ $1,000
        dollar_risk = row_norm["recommended_shares"] * row_norm["risk_per_share"]
        self.assertLessEqual(dollar_risk, 1050.0)
        # Target price must reflect 2.5R
        expected_target = round(100.0 + (2.5 * row_norm["risk_per_share"]), 2)
        self.assertEqual(row_norm["target_price"], expected_target)

        # 2. WIDE_STOP stock ($50 close, wide contraction)
        row_wide = df_out[df_out["ticker"] == "WIDE_STOP"].iloc[0]
        # Stop must be clamped at max 7.0% ($46.50)
        self.assertAlmostEqual(row_wide["risk_pct"], 7.0, delta=0.2)
        self.assertGreaterEqual(row_wide["stop_loss_price"], 46.50)

        # 3. TIGHT_RISK stock (risk per share is small, so capital cap of 25% binds)
        row_tight = df_out[df_out["ticker"] == "TIGHT_RISK"].iloc[0]
        # Position capital cannot exceed $25,000
        self.assertLessEqual(row_tight["position_value"], 25000.0)
        self.assertLessEqual(row_tight["portfolio_alloc_pct"], 25.0)

    def test_layer5_gate_qualification(self) -> None:
        cfg = {
            "l5_enabled": True,
            "risk_gate_enabled": True,
            "max_stop_loss_pct": 6.0,
        }
        df_out, meta = evaluate_layer5_position_sizing(self.df_mock, cfg)
        for _, row in df_out.iterrows():
            if row["risk_pct"] <= 6.0:
                self.assertTrue(row["l5_qualified"])
            else:
                self.assertFalse(row["l5_qualified"])


if __name__ == "__main__":
    unittest.main()
