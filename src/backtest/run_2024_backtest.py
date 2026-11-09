"""
CLI Runner for the 2024 Historical Backtest & JLaw USIC Benchmark Evaluation.

Usage:
  1. Fetch & cache 2023-2024 historical dataset (requires network):
     python -m src.backtest.run_2024_backtest --cache-dir <path> --fetch-only
  2. Run full PIT feature engine, Phase A recall audit, and Phase B/C simulations (offline):
     python -m src.backtest.run_2024_backtest --cache-dir <path> --simulate-only
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Dict, Any

import numpy as np

from src.backtest.historical_data_loader import (
    get_default_cache_dir,
    load_or_fetch_2024_historical_dataset,
)
from src.backtest.pit_feature_engine import build_pit_panel
from src.backtest.portfolio_simulator import (
    precompute_daily_screens,
    run_monster_winner_recall_audit,
    run_walk_forward_simulation,
)
from src.config.builtin_presets import BUILTIN_PRESETS
from src.config.settings import (
    get_default_layer0_config,
    get_default_layer1_config,
    get_default_layer2_config,
    get_default_layer3_config,
    get_default_layer4_config,
    get_default_layer5_config,
)


def _summarize_funnel(daily_screens: Dict[str, Dict[str, Any]], dates_2024: list[str]) -> Dict[str, Any]:
    l0_c, l1_c, l2_c, l3_c, l4_c, trig_c, bz_c, od_c = [], [], [], [], [], [], [], []
    for d in dates_2024:
        pack = daily_screens.get(d)
        if not pack:
            continue
        sm = pack["summary_meta"]
        df = pack["df_scored"]
        l0_c.append(sm.get("layer0_count", 0))
        l1_c.append(sm.get("qualified_count", 0))
        l2_c.append(sm.get("l2_qualified_count", 0))
        l3_c.append(sm.get("l3_qualified_count", 0))
        l4_c.append(sm.get("l4_qualified_count", 0))
        if not df.empty:
            q3 = df.get("qualified_all", False) & df.get("l2_qualified", False) & df.get("l3_qualified", False)
            sub = df[q3]
            trig_c.append(int((sub["action_status"] == "TRIGGERED").sum()))
            bz_c.append(int((sub["action_status"] == "BUY_ZONE").sum()))
            od_c.append(int((sub["action_status"] == "ON_DECK").sum()))

    return {
        "avg_l0_count": round(float(np.mean(l0_c)), 1) if l0_c else 0.0,
        "avg_l1_count": round(float(np.mean(l1_c)), 1) if l1_c else 0.0,
        "avg_l2_count": round(float(np.mean(l2_c)), 1) if l2_c else 0.0,
        "avg_l3_table2_count": round(float(np.mean(l3_c)), 1) if l3_c else 0.0,
        "avg_l4_actionable_count": round(float(np.mean(l4_c)), 1) if l4_c else 0.0,
        "total_table2_triggered_signals_2024": int(np.sum(trig_c)),
        "total_table2_buy_zone_signals_2024": int(np.sum(bz_c)),
        "total_table2_on_deck_signals_2024": int(np.sum(od_c)),
        "days_with_triggered_signal": int(sum(1 for x in trig_c if x > 0)),
        "days_with_on_deck_signal": int(sum(1 for x in od_c if x > 0)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run 2024 US Stock Screener Backtest vs JLaw USIC.")
    parser.add_argument("--cache-dir", type=str, default="", help="External directory for OHLCV cache & JSON output")
    parser.add_argument("--pool-size", type=int, default=1050, help="Target US liquid stock pool size")
    parser.add_argument("--fetch-only", action="store_true", help="Only fetch and cache market data")
    parser.add_argument("--simulate-only", action="store_true", help="Run simulation from existing cache only")
    args = parser.parse_args()

    cache_dir = Path(args.cache_dir) if args.cache_dir else get_default_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    bundle = load_or_fetch_2024_historical_dataset(
        cache_dir=cache_dir,
        target_pool_size=args.pool_size,
        force_refresh=False,
    )
    print(
        f"Loaded dataset: {len(bundle['metadata_df'])} tickers, "
        f"{len(bundle['ohlcv_map'])} OHLCV histories ({time.perf_counter() - t0:.1f}s)"
    )
    if args.fetch_only:
        return

    print("\n[Step 1] Building Point-in-Time (PIT) vectorized feature panel (zero look-ahead)...")
    t1 = time.perf_counter()
    panel = build_pit_panel(
        metadata_df=bundle["metadata_df"],
        ohlcv_map=bundle["ohlcv_map"],
        sp500_df=bundle["sp500_df"],
    )
    dates_2024 = panel["trading_dates_2024"]
    print(f"         Built {len(dates_2024)} trading days in 2024 ({time.perf_counter() - t1:.1f}s)")

    print("\n[Step 2] Running Updated Production Pipeline (P0+P1+P2) across all 2024 trading days...")
    t2 = time.perf_counter()
    screens_pit_default = precompute_daily_screens(panel, feature_mode="pit_clean")

    # Legacy pre-P0 baseline (for Before vs After comparison)
    l1_legacy = get_default_layer1_config()
    l1_legacy["ipo_mode_enabled"] = False
    l3_legacy = get_default_layer3_config()
    l3_legacy["min_adr_pct"] = 0.0
    screens_asis_bug = precompute_daily_screens(
        panel,
        feature_mode="asis_live_snapshot",
        layer1_cfg=l1_legacy,
        layer3_cfg=l3_legacy,
    )

    # Built-in JLaw 2024 USIC Championship Preset from `src/config/builtin_presets.py`
    jlaw_preset_key = "🏆 JLaw 2024 USIC Championship ($1B Cap + RS≥85 + ADR≥3.2% + Hybrid Exit)"
    jlaw_preset = BUILTIN_PRESETS[jlaw_preset_key]
    screens_pro_1b = precompute_daily_screens(
        panel,
        feature_mode="pit_clean",
        layer0_cfg=jlaw_preset["layer0"],
        layer1_cfg=jlaw_preset["layer1"],
        layer2_cfg=jlaw_preset["layer2"],
        layer3_cfg=jlaw_preset["layer3"],
        layer4_cfg=jlaw_preset["layer4"],
        layer5_cfg=jlaw_preset["layer5"],
    )
    print(f"         Completed 3x252 full 6-layer pipeline runs ({time.perf_counter() - t2:.1f}s)")

    funnel_pit = _summarize_funnel(screens_pit_default, dates_2024)
    funnel_asis = _summarize_funnel(screens_asis_bug, dates_2024)
    funnel_pro = _summarize_funnel(screens_pro_1b, dates_2024)

    print("\n[Step 3] Phase A: Auditing 28 Signature 2024 Monster Winners...")
    recall_default = run_monster_winner_recall_audit(panel, screens_pit_default)
    recall_pro = run_monster_winner_recall_audit(panel, screens_pro_1b)

    caught_def = sum(1 for r in recall_default if r["caught_by_screener"])
    caught_pro = sum(1 for r in recall_pro if r["caught_by_screener"])
    print(f"         Default ($3B Mkt Cap) Recall: {caught_def}/{len(recall_default)} leaders caught in Table 2")
    print(f"         Pro ($1B Mkt Cap + Local Pivot) Recall: {caught_pro}/{len(recall_pro)} leaders caught in Table 2")

    print("\n[Step 4] Phase B: Running 2x2 Core Portfolio Matrix + Diagnostic Variants...")
    runs: Dict[str, Dict[str, Any]] = {}

    # 1. Mode A (Pre-set Pivot Buy-Stop from T-1 ON_DECK) + Model 1 (Fixed +2.5R)
    runs["M1_ModeA_Fixed25R"] = run_walk_forward_simulation(
        panel, screens_pit_default, entry_mode="ON_DECK_STOP", exit_model="FIXED_2_5R"
    )
    # 2. Mode A (Pre-set Pivot Buy-Stop from T-1 ON_DECK) + Model 2 (JLaw Hybrid: 50% @ +2.5R + EMA21 Trail)
    runs["M2_ModeA_JLawHybrid"] = run_walk_forward_simulation(
        panel, screens_pit_default, entry_mode="ON_DECK_STOP", exit_model="JLAW_HYBRID"
    )
    # 3. Mode B (Next-Day Open after T TRIGGERED) + Model 1 (Fixed +2.5R)
    runs["M3_ModeB_Fixed25R"] = run_walk_forward_simulation(
        panel, screens_pit_default, entry_mode="TRIGGERED_NEXT_OPEN", exit_model="FIXED_2_5R"
    )
    # 4. Mode B (Next-Day Open after T TRIGGERED) + Model 2 (JLaw Hybrid: 50% @ +2.5R + EMA21 Trail)
    runs["M4_ModeB_JLawHybrid"] = run_walk_forward_simulation(
        panel, screens_pit_default, entry_mode="TRIGGERED_NEXT_OPEN", exit_model="JLAW_HYBRID"
    )

    # Diagnostic Variant D1: As-Is Unshifted Snapshot Bug on Mode B + JLaw Hybrid
    runs["D1_AsIs_LiveBug_ModeB_JLaw"] = run_walk_forward_simulation(
        panel, screens_asis_bug, entry_mode="TRIGGERED_NEXT_OPEN", exit_model="JLAW_HYBRID"
    )
    # Diagnostic Variant D2: Pro Signal Upgrade ($1B Mkt Cap + Local 20D Pivot + SPY>EMA21 Regime) @ Standard 1% Risk / 25% Cap
    runs["D2_ProSignals_1PctRisk_ModeA_JLaw"] = run_walk_forward_simulation(
        panel,
        screens_pro_1b,
        entry_mode="ON_DECK_STOP",
        exit_model="JLAW_HYBRID",
        require_spy_above_ema21=True,
    )
    runs["D2b_ProSignals_1PctRisk_ModeB_JLaw"] = run_walk_forward_simulation(
        panel,
        screens_pro_1b,
        entry_mode="TRIGGERED_NEXT_OPEN",
        exit_model="JLAW_HYBRID",
        require_spy_above_ema21=True,
    )
    # Diagnostic Variant D3: Championship USIC Sizing (2.0% Risk, 33% Max Alloc = 3-4 Concentrated Leaders + SPY>EMA21)
    runs["D3_USIC_Concentrated_ModeA_JLaw"] = run_walk_forward_simulation(
        panel,
        screens_pro_1b,
        entry_mode="ON_DECK_STOP",
        exit_model="JLAW_HYBRID",
        risk_pct_per_trade=2.0,
        max_alloc_pct=33.3,
        require_spy_above_ema21=True,
    )
    runs["D3b_USIC_Concentrated_ModeB_JLaw"] = run_walk_forward_simulation(
        panel,
        screens_pro_1b,
        entry_mode="TRIGGERED_NEXT_OPEN",
        exit_model="JLAW_HYBRID",
        risk_pct_per_trade=2.0,
        max_alloc_pct=33.3,
        require_spy_above_ema21=True,
    )

    print("\n================ 2024 BACKTEST SUMMARY SCORECARD ================")
    for name, rdata in runs.items():
        m = rdata["metrics"]
        print(
            f"{name:36s} | Return: {m['total_return_pct']:+7.2f}% | MaxDD: {m['max_drawdown_pct']:6.2f}% "
            f"| Trades: {m['total_trades']:3d} | Win%: {m['win_rate_pct']:5.1f}% "
            f"| PF: {m['profit_factor']:5.2f} | Sharpe: {m['sharpe_ratio']:4.2f}"
        )

    # Save structured summary JSON to cache_dir for detailed UAT report construction
    summary_payload = {
        "universe_size": int(len(bundle["metadata_df"])),
        "trading_days_2024": int(len(dates_2024)),
        "funnel_pit_default": funnel_pit,
        "funnel_asis_live_bug": funnel_asis,
        "funnel_pro_1b": funnel_pro,
        "recall_default": recall_default,
        "recall_pro": recall_pro,
        "simulations": {
            k: {
                "metrics": v["metrics"],
                "top_10_winners": sorted(v["trades"], key=lambda x: x["pnl_dollars"], reverse=True)[:10],
                "top_10_losers": sorted(v["trades"], key=lambda x: x["pnl_dollars"])[:10],
                "all_trades_count": len(v["trades"]),
                "sample_trades": v["trades"][:40],
            }
            for k, v in runs.items()
        },
    }
    out_json = cache_dir / "backtest_2024_results_summary.json"
    with open(out_json, "w", encoding="utf-8") as fh:
        json.dump(summary_payload, fh, indent=2)
    print(f"\nSaved complete JSON report data to: {out_json}")


if __name__ == "__main__":
    main()
