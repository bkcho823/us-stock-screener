"""
Unit Tests for the 2024 Backtest Engine (`src/backtest/`):
- Verifies zero look-ahead bias in `pit_feature_engine.py` (`pit_clean` vs `asis_live_snapshot`).
- Verifies A/B Exit Execution math (`FIXED_2_5R` vs `JLAW_HYBRID` 50% @ +2.5R + EMA21 trailing).
"""

from __future__ import annotations

import unittest
import numpy as np
import pandas as pd

from src.backtest.pit_feature_engine import build_pit_panel, extract_day_universe
from src.backtest.portfolio_simulator import precompute_daily_screens, run_walk_forward_simulation


class TestBacktestEngine(unittest.TestCase):
    def _make_synthetic_bundle(self):
        dates = pd.bdate_range("2023-01-02", "2024-06-28")
        n = len(dates)

        # S&P 500 steady uptrend
        sp_close = np.linspace(4000.0, 5200.0, n)
        sp500_df = pd.DataFrame(
            {
                "Open": sp_close * 0.999,
                "High": sp_close * 1.004,
                "Low": sp_close * 0.996,
                "Close": sp_close,
                "Volume": np.full(n, 2_500_000_000.0),
            },
            index=dates,
        )

        # Synthetic Monster Winner: steady Stage 2 climb -> tight 10-day VCP coil -> high-vol breakout -> multi-month run
        c = np.linspace(40.0, 100.0, n)
        v = np.full(n, 2_000_000.0)

        # Find a date index in Feb 2024 (~bar 285)
        b_idx = 285
        # Tight 10-day coil right below $100.00 with volume dry-up (45% of avg)
        for k in range(b_idx - 10, b_idx):
            c[k] = 98.5 + (k % 2) * 0.4  # ~0.4% tight coil beneath prior high
            v[k] = 850_000.0

        # Ensure prior 52W high right before b_idx is 100.0
        c[b_idx - 15] = 100.0

        # Breakout Day T (b_idx): closes at $101.50 (+1.5% above $100 pivot) on 250% volume!
        c[b_idx] = 101.5
        v[b_idx] = 5_000_000.0

        # Subsequent multi-week monster trend to $160 before dipping below EMA21
        for k in range(b_idx + 1, n - 5):
            c[k] = 101.5 + (k - b_idx) * 0.85
            v[k] = 2_500_000.0
        # Sharp drop below EMA21 at the very end to trigger EMA21 trail exit
        for k in range(n - 5, n):
            c[k] = 130.0

        lead_df = pd.DataFrame(
            {
                "Open": c * 0.998,
                "High": c * 1.015,
                "Low": c * 0.985,
                "Close": c,
                "Volume": v,
            },
            index=dates,
        )
        # Keep tight coil highs strictly <= 100.0 before b_idx with ~2.8% ADR
        for k in range(b_idx - 14, b_idx):
            lead_df.iloc[k, lead_df.columns.get_loc("High")] = 99.8
            lead_df.iloc[k, lead_df.columns.get_loc("Low")] = 97.1
        lead_df.iloc[b_idx - 15, lead_df.columns.get_loc("High")] = 100.0

        # Laggard stock so pool has >1 stock & industry rankings
        lag_c = np.linspace(50.0, 52.0, n)
        lag_df = pd.DataFrame(
            {
                "Open": lag_c,
                "High": lag_c * 1.005,
                "Low": lag_c * 0.995,
                "Close": lag_c,
                "Volume": np.full(n, 1_500_000.0),
            },
            index=dates,
        )

        metadata_df = pd.DataFrame(
            [
                {
                    "ticker": "LEAD",
                    "company_name": "Monster Leader Inc",
                    "exchange": "NASDAQ",
                    "sector": "Electronic Technology",
                    "industry": "Semiconductors",
                    "is_etf_or_fund": False,
                    "is_adr": False,
                    "shares_est": 100_000_000.0,  # $10B market cap at $100
                },
                {
                    "ticker": "LAGG",
                    "company_name": "Slow Co",
                    "exchange": "NYSE",
                    "sector": "Utilities",
                    "industry": "Electric Utilities",
                    "is_etf_or_fund": False,
                    "is_adr": False,
                    "shares_est": 100_000_000.0,
                },
            ]
        )
        return metadata_df, {"LEAD": lead_df, "LAGG": lag_df}, sp500_df, dates[b_idx].strftime("%Y-%m-%d")

    def test_zero_lookahead_pit_vs_asis_breakout_detection(self) -> None:
        meta_df, ohlcv_map, sp500_df, breakout_date = self._make_synthetic_bundle()
        panel = build_pit_panel(meta_df, ohlcv_map, sp500_df, eval_start="2023-12-26", eval_end="2024-06-28")

        # On breakout_date, Clean PIT uses pre-breakout coil (vol_dryup < 65% and high_52w == 100.0 < close 101.5)
        df_pit, _ = extract_day_universe(panel, breakout_date, feature_mode="pit_clean")
        lead_pit = df_pit[df_pit["ticker"] == "LEAD"].iloc[0]
        self.assertEqual(float(lead_pit["high_52w"]), 100.0)
        self.assertGreater(float(lead_pit["close"]), float(lead_pit["high_52w"]))
        self.assertLess(float(lead_pit["vol_dryup_pct"]), 65.0)

        # In contrast, As-Is Snapshot includes breakout day's High & 5M Volume in high_52w & vol_dryup_pct!
        df_asis, _ = extract_day_universe(panel, breakout_date, feature_mode="asis_live_snapshot")
        lead_asis = df_asis[df_asis["ticker"] == "LEAD"].iloc[0]
        self.assertGreater(float(lead_asis["high_52w"]), float(lead_asis["close"]))
        self.assertGreater(float(lead_asis["vol_dryup_pct"]), 150.0)

    def test_jlaw_hybrid_outperforms_fixed_target_on_multi_month_runner(self) -> None:
        meta_df, ohlcv_map, sp500_df, _ = self._make_synthetic_bundle()
        panel = build_pit_panel(meta_df, ohlcv_map, sp500_df, eval_start="2023-12-26", eval_end="2024-06-28")
        screens = precompute_daily_screens(panel, feature_mode="pit_clean")

        sim_fixed = run_walk_forward_simulation(
            panel, screens, entry_mode="TRIGGERED_NEXT_OPEN", exit_model="FIXED_2_5R"
        )
        sim_jlaw = run_walk_forward_simulation(
            panel, screens, entry_mode="TRIGGERED_NEXT_OPEN", exit_model="JLAW_HYBRID"
        )

        self.assertGreaterEqual(sim_fixed["metrics"]["total_trades"], 1)
        self.assertGreaterEqual(sim_jlaw["metrics"]["total_trades"], 1)
        # JLaw Hybrid rides the 50% runner well past +2.5R on a sustained Stage 2 leader
        self.assertGreater(
            sim_jlaw["metrics"]["total_return_pct"],
            sim_fixed["metrics"]["total_return_pct"],
        )


if __name__ == "__main__":
    unittest.main()
