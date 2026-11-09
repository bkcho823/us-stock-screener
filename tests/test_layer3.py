"""
Unit Tests for Layer 3 (`src/layers/layer3_vcp.py`) — Minervini VCP Pattern,
Last Contraction Amplitude, Volume Dry-up, and JLaw 21/50 EMA Alignment.
"""

import unittest
import pandas as pd

from src.config import get_default_layer3_config
from src.layers.layer3_vcp import (
    _calc_vcp_tightness_score,
    evaluate_layer3_vcp_and_structure,
)


class TestLayer3VCP(unittest.TestCase):
    def test_vcp_tightness_score_formula(self) -> None:
        # Ideal VCP setup: tight contraction (3.5%), low volume dry-up (35%), EMA aligned
        score_high = _calc_vcp_tightness_score(3.5, 35.0, True)
        self.assertGreaterEqual(score_high, 85.0)

        # Loose setup: wide contraction (14%), high volume (110%), EMA not aligned
        score_low = _calc_vcp_tightness_score(14.0, 110.0, False)
        self.assertLess(score_low, 35.0)

    def test_evaluate_layer3_vcp_and_structure(self) -> None:
        df_l2 = pd.DataFrame([
            {
                "ticker": "PERF", "close": 150.0, "ema_21": 145.0, "ema_50": 138.0,
                "last_contraction_pct": 4.5, "vol_dryup_pct": 45.0, "composite_score": 92.0,
                "rs_percentile": 95, "qualified_all": True, "l2_qualified": True
            },
            {
                "ticker": "WIDE", "close": 80.0, "ema_21": 75.0, "ema_50": 70.0,
                "last_contraction_pct": 14.0, "vol_dryup_pct": 95.0, "composite_score": 75.0,
                "rs_percentile": 80, "qualified_all": True, "l2_qualified": True
            },
            {
                "ticker": "BEAR", "close": 40.0, "ema_21": 42.0, "ema_50": 45.0,
                "last_contraction_pct": 5.0, "vol_dryup_pct": 40.0, "composite_score": 70.0,
                "rs_percentile": 75, "qualified_all": True, "l2_qualified": True
            },
        ])

        l3_cfg = get_default_layer3_config()
        l3_cfg["vcp_gate_enabled"] = True
        l3_cfg["require_ema_alignment"] = True
        l3_cfg["max_contraction_pct"] = 8.0
        l3_cfg["max_vol_dryup_pct"] = 65.0
        l3_cfg["min_tightness_score"] = 60.0

        df_out, meta = evaluate_layer3_vcp_and_structure(df_l2, l3_cfg)

        self.assertIn("vcp_score", df_out.columns)
        self.assertIn("vcp_badge", df_out.columns)
        self.assertIn("l3_qualified", df_out.columns)

        # PERF satisfies all VCP criteria & EMA alignment
        perf_row = df_out[df_out["ticker"] == "PERF"].iloc[0]
        self.assertTrue(perf_row["l3_qualified"])
        self.assertTrue(perf_row["ema_aligned"])
        self.assertIn("VCP", perf_row["vcp_badge"])

        # WIDE fails contraction tightness & vol dryup
        wide_row = df_out[df_out["ticker"] == "WIDE"].iloc[0]
        self.assertFalse(wide_row["l3_qualified"])

        # BEAR has bad EMA alignment (Close < 21EMA < 50EMA)
        bear_row = df_out[df_out["ticker"] == "BEAR"].iloc[0]
        self.assertFalse(bear_row["l3_qualified"])

    def test_layer3_adr_filter_excludes_low_beta_crawlers(self) -> None:
        df_l2 = pd.DataFrame([
            {
                "ticker": "FAST", "close": 100.0, "ema_21": 96.0, "ema_50": 90.0,
                "last_contraction_pct": 4.2, "vol_dryup_pct": 42.0, "adr_20_pct": 4.5,
                "composite_score": 90.0, "rs_percentile": 92, "qualified_all": True, "l2_qualified": True
            },
            {
                "ticker": "SLOW_BANK", "close": 50.0, "ema_21": 49.0, "ema_50": 48.0,
                "last_contraction_pct": 3.8, "vol_dryup_pct": 40.0, "adr_20_pct": 1.6,
                "composite_score": 82.0, "rs_percentile": 85, "qualified_all": True, "l2_qualified": True
            },
        ])
        l3_cfg = get_default_layer3_config()
        l3_cfg["min_adr_pct"] = 3.2
        df_out, meta = evaluate_layer3_vcp_and_structure(df_l2, l3_cfg)
        self.assertTrue(bool(df_out[df_out["ticker"] == "FAST"].iloc[0]["l3_qualified"]))
        self.assertFalse(bool(df_out[df_out["ticker"] == "SLOW_BANK"].iloc[0]["l3_qualified"]))


if __name__ == "__main__":
    unittest.main()
