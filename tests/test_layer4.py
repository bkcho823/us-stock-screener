"""
Unit Tests for Layer 4: Actionable Entry Triggers & Pivot Detection Engine.
"""

import unittest
import pandas as pd

from src.layers.layer4_entry import evaluate_layer4_entry_signals


class TestLayer4Entry(unittest.TestCase):
    def setUp(self) -> None:
        # Create a mock dataframe of coiled Layer 3 setups
        self.df_mock = pd.DataFrame([
            {
                "ticker": "TRIG",
                "company_name": "Triggered Corp",
                "close": 101.50,
                "high_52w": 100.00,  # Pivot is 100.00, dist = +1.5%
                "last_contraction_pct": 4.0,
                "vol_1d": 1_500_000,
                "vol_60d": 1_000_000,  # Vol expansion = 150% (>= 120%)
                "qualified_all": True,
                "l2_qualified": True,
                "l3_qualified": True,
            },
            {
                "ticker": "BUY",
                "company_name": "BuyZone Inc",
                "close": 101.50,
                "high_52w": 100.00,  # Pivot is 100.00, dist = +1.5%
                "last_contraction_pct": 4.0,
                "vol_1d": 900_000,
                "vol_60d": 1_000_000,  # Vol expansion = 90% (< 120%)
                "qualified_all": True,
                "l2_qualified": True,
                "l3_qualified": True,
            },
            {
                "ticker": "DECK",
                "company_name": "OnDeck Ltd",
                "close": 98.50,
                "high_52w": 100.00,  # Pivot is 100.00, dist = -1.5% (-3% to 0%)
                "last_contraction_pct": 5.0,
                "vol_1d": 500_000,
                "vol_60d": 1_000_000,  # Vol expansion = 50%
                "qualified_all": True,
                "l2_qualified": True,
                "l3_qualified": True,
            },
            {
                "ticker": "EXT",
                "company_name": "Extended Holdings",
                "close": 110.00,
                "high_52w": 100.00,  # Pivot is 100.00, dist = +10.0% (> 3.5%)
                "last_contraction_pct": 6.0,
                "vol_1d": 2_000_000,
                "vol_60d": 1_000_000,
                "qualified_all": True,
                "l2_qualified": True,
                "l3_qualified": True,
            },
            {
                "ticker": "BASE",
                "company_name": "Basing Tech",
                "close": 90.00,
                "high_52w": 100.00,  # Pivot is 100.00, dist = -10.0% (< -3.0%)
                "last_contraction_pct": 8.0,
                "vol_1d": 600_000,
                "vol_60d": 1_000_000,
                "qualified_all": True,
                "l2_qualified": True,
                "l3_qualified": True,
            },
        ])

    def test_evaluate_layer4_entry_signals_classification(self) -> None:
        cfg = {
            "l4_enabled": True,
            "entry_gate_enabled": True,
            "min_vol_expansion_pct": 120.0,
            "max_buy_zone_pct": 3.5,
            "on_deck_pct": 3.0,
            "action_status_filter": "ALL",
        }
        df_out, meta = evaluate_layer4_entry_signals(self.df_mock, cfg)

        self.assertEqual(meta["triggered_count"], 1)
        self.assertEqual(meta["buy_zone_count"], 1)
        self.assertEqual(meta["on_deck_count"], 1)

        # Check statuses
        row_trig = df_out[df_out["ticker"] == "TRIG"].iloc[0]
        self.assertEqual(row_trig["action_status"], "TRIGGERED")
        self.assertTrue("🚀 TRIGGERED" in row_trig["action_status_badge"])
        self.assertTrue(row_trig["l4_qualified"])

        row_buy = df_out[df_out["ticker"] == "BUY"].iloc[0]
        self.assertEqual(row_buy["action_status"], "BUY_ZONE")
        self.assertTrue("⚡ BUY ZONE" in row_buy["action_status_badge"])
        self.assertTrue(row_buy["l4_qualified"])

        row_deck = df_out[df_out["ticker"] == "DECK"].iloc[0]
        self.assertEqual(row_deck["action_status"], "ON_DECK")
        self.assertTrue("⏳ ON DECK" in row_deck["action_status_badge"])
        self.assertTrue(row_deck["l4_qualified"])

        row_ext = df_out[df_out["ticker"] == "EXT"].iloc[0]
        self.assertEqual(row_ext["action_status"], "EXTENDED")
        self.assertFalse(row_ext["l4_qualified"])

        row_base = df_out[df_out["ticker"] == "BASE"].iloc[0]
        self.assertEqual(row_base["action_status"], "BUILDING")
        self.assertFalse(row_base["l4_qualified"])

    def test_action_status_filter_options(self) -> None:
        # 1. Triggered Only
        cfg_trig = {
            "l4_enabled": True,
            "entry_gate_enabled": True,
            "action_status_filter": "TRIGGERED_ONLY",
        }
        df_trig, _ = evaluate_layer4_entry_signals(self.df_mock, cfg_trig)
        qual_tickers = df_trig[df_trig["l4_qualified"]]["ticker"].tolist()
        self.assertEqual(qual_tickers, ["TRIG"])

        # 2. Buy Zone Only (Triggered + Buy Zone)
        cfg_bz = {
            "l4_enabled": True,
            "entry_gate_enabled": True,
            "action_status_filter": "BUY_ZONE_ONLY",
        }
        df_bz, _ = evaluate_layer4_entry_signals(self.df_mock, cfg_bz)
        qual_tickers_bz = df_bz[df_bz["l4_qualified"]]["ticker"].tolist()
        self.assertEqual(set(qual_tickers_bz), {"TRIG", "BUY"})

        # 3. On Deck Only
        cfg_deck = {
            "l4_enabled": True,
            "entry_gate_enabled": True,
            "action_status_filter": "ON_DECK_ONLY",
        }
        df_deck, _ = evaluate_layer4_entry_signals(self.df_mock, cfg_deck)
        qual_tickers_deck = df_deck[df_deck["l4_qualified"]]["ticker"].tolist()
        self.assertEqual(qual_tickers_deck, ["DECK"])

    def test_pre_breakout_coil_pivot_high_triggers_mid_base_vcp(self) -> None:
        # Stock is 14% below 52W high ($110), breaking out past 10D coil pivot ($94.50) at $95.80 on 180% vol
        df_coil = pd.DataFrame([
            {
                "ticker": "POWL",
                "company_name": "Powell Industries",
                "close": 95.80,
                "high_52w": 110.00,
                "prior_high_52w": 110.00,
                "coil_pivot_high": 94.50,
                "last_contraction_pct": 4.2,
                "vol_1d": 1_800_000,
                "vol_60d": 1_000_000,
                "qualified_all": True,
                "l2_qualified": True,
                "l3_qualified": True,
            }
        ])
        df_out, meta = evaluate_layer4_entry_signals(df_coil, {"min_vol_expansion_pct": 120.0, "max_buy_zone_pct": 3.5})
        row = df_out.iloc[0]
        self.assertEqual(row["pivot_price"], 94.50)
        self.assertEqual(row["action_status"], "TRIGGERED")
        self.assertEqual(meta["triggered_count"], 1)


if __name__ == "__main__":
    unittest.main()
