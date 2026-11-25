"""
2025 Full-Year Walk-Forward Backtest & JLaw 2025 USIC (+252.3%) Benchmark Runner (`src/backtest/run_2025_backtest.py`).
- Fetches/caches 2023-11-01 to 2026-01-10 daily OHLCV for ~1,020 liquid US equities + ^GSPC.
- Runs the full 6-layer updated production pipeline (`P0 + P1 + P2`) across all 2025 NYSE/NASDAQ trading days.
- Audits 28 Signature 2025 US Momentum Leaders (Phase A Recall).
- Simulates:
    1. Default Settings Matrix (`M1`..`M4`)
    2. Built-in 🏆 JLaw USIC Preset @ 1.0% Risk (`D2b`)
    3. Built-in 🏆 JLaw USIC Preset @ 2.0% Risk (`D3b` Baseline: +2.5R Partial / 50% sold)
    4. What-If Scenario 1 (`D3b_S1_3R_50Pct`: +3.0R Partial / 50% sold)
    5. What-If Scenario 2 (`D3b_S2_2R_40Pct`: +2.0R Partial / 40% sold)
- Exports comprehensive JSON and multi-sheet Excel workbooks.
"""

from __future__ import annotations

import json
import pickle
import time
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from src.backtest.historical_data_loader import load_or_fetch_2024_historical_dataset
from src.backtest.pit_feature_engine import build_pit_panel
from src.backtest.portfolio_simulator import (
    precompute_daily_screens,
    run_walk_forward_simulation,
)
from src.config.builtin_presets import BUILTIN_PRESETS

CACHE_DIR_2024 = Path(
    r"C:\Users\User\.gemini\antigravity\brain\9c87e4f7-7ae9-4bd7-9d9b-53c0f1e12b32\scratch\backtest_2024_cache"
)
CACHE_DIR_2025 = Path(
    r"C:\Users\User\.gemini\antigravity\brain\9c87e4f7-7ae9-4bd7-9d9b-53c0f1e12b32\scratch\backtest_2025_cache"
)
OUT_DIR = Path(
    r"C:\Users\User\.gemini\antigravity\brain\9c87e4f7-7ae9-4bd7-9d9b-53c0f1e12b32"
)

# 28 Signature 2025 US Momentum Leaders across AI Software, Space/Defense, Power/Nuclear, Semis, and Fintech
SIGNATURE_2025_WINNERS: List[Dict[str, str]] = [
    {"ticker": "PLTR", "wave": "2025 AI Enterprise Leader", "company_name": "Palantir Technologies"},
    {"ticker": "APP", "wave": "2025 AI AdTech Leader", "company_name": "AppLovin Corp."},
    {"ticker": "HOOD", "wave": "2025 Fintech & Crypto Leader", "company_name": "Robinhood Markets"},
    {"ticker": "RKLB", "wave": "2025 Space & Launch Leader", "company_name": "Rocket Lab USA"},
    {"ticker": "ASTS", "wave": "2025 Space Telecom Leader", "company_name": "AST SpaceMobile"},
    {"ticker": "AVGO", "wave": "2025 Custom AI Silicon", "company_name": "Broadcom Inc."},
    {"ticker": "NVDA", "wave": "2025 AI Blackwell Cycle", "company_name": "NVIDIA Corp."},
    {"ticker": "GEV", "wave": "2025 Power Grid Supercycle", "company_name": "GE Vernova Inc."},
    {"ticker": "VST", "wave": "2025 AI Power Generation", "company_name": "Vistra Corp."},
    {"ticker": "CEG", "wave": "2025 Nuclear AI Power", "company_name": "Constellation Energy"},
    {"ticker": "CLS", "wave": "2025 Hyperscaler AI Hardware", "company_name": "Celestica Inc."},
    {"ticker": "CRDO", "wave": "2025 AI Optical Interconnect", "company_name": "Credo Technology"},
    {"ticker": "ALAB", "wave": "2025 AI Connectivity IPO", "company_name": "Astera Labs"},
    {"ticker": "RDDT", "wave": "2025 AI Data & Social IPO", "company_name": "Reddit Inc."},
    {"ticker": "HIMS", "wave": "2025 Telehealth Momentum", "company_name": "Hims & Hers Health"},
    {"ticker": "CVNA", "wave": "2025 Auto E-Commerce Leader", "company_name": "Carvana Co."},
    {"ticker": "AXON", "wave": "2025 Public Safety AI", "company_name": "Axon Enterprise"},
    {"ticker": "NET", "wave": "2025 Edge Cloud & Cyber AI", "company_name": "Cloudflare Inc."},
    {"ticker": "SNOW", "wave": "2025 Enterprise Data Cloud", "company_name": "Snowflake Inc."},
    {"ticker": "SHOP", "wave": "2025 Global Commerce Leader", "company_name": "Shopify Inc."},
    {"ticker": "SPOT", "wave": "2025 Audio Streaming Margin Leader", "company_name": "Spotify Technology"},
    {"ticker": "NFLX", "wave": "2025 Media & Ad Tier Leader", "company_name": "Netflix Inc."},
    {"ticker": "TSLA", "wave": "2025 Autonomy & Robotics Wave", "company_name": "Tesla Inc."},
    {"ticker": "MSTR", "wave": "2025 Bitcoin Treasury Proxy", "company_name": "MicroStrategy Inc."},
    {"ticker": "COIN", "wave": "2025 Crypto Exchange Leader", "company_name": "Coinbase Global"},
    {"ticker": "VRT", "wave": "2025 Data Center Thermal", "company_name": "Vertiv Holdings"},
    {"ticker": "ANET", "wave": "2025 AI Ethernet Switching", "company_name": "Arista Networks"},
    {"ticker": "KTOS", "wave": "2025 Defense Drone Leader", "company_name": "Kratos Defense"},
]


def load_or_fetch_2025_dataset(force_refresh: bool = False) -> Dict[str, Any]:
    CACHE_DIR_2025.mkdir(parents=True, exist_ok=True)
    for cname in ["dataset_2025_pool1050.pkl", "dataset_2024_pool1050.pkl"]:
        cache_file = CACHE_DIR_2025 / cname
        if cache_file.exists() and not force_refresh:
            with open(cache_file, "rb") as fh:
                return pickle.load(fh)

    bundle = load_or_fetch_2024_historical_dataset(
        cache_dir=CACHE_DIR_2025,
        target_pool_size=1050,
        start_date="2023-10-15",
        end_date="2026-01-10",
        force_refresh=False,
    )
    return bundle


def run_2025_recall_audit(
    panel: Dict[str, Any],
    daily_screens: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    dates_2025 = panel["trading_dates_2024"]
    ohlc_by_sym = panel["ohlc_by_sym"]
    by_date_raw = panel["by_date"]

    scored_by_sym_date: Dict[str, Dict[str, pd.Series]] = {w["ticker"]: {} for w in SIGNATURE_2025_WINNERS}
    for d_str in dates_2025:
        day_pack = daily_screens.get(d_str)
        if not day_pack:
            continue
        df_s = day_pack["df_scored"]
        if df_s.empty:
            continue
        sub = df_s[df_s["ticker"].isin(scored_by_sym_date.keys())]
        for _, row in sub.iterrows():
            scored_by_sym_date[str(row["ticker"])][d_str] = row

    audit_rows: List[Dict[str, Any]] = []
    for item in SIGNATURE_2025_WINNERS:
        sym = item["ticker"]
        ohlc = ohlc_by_sym.get(sym)
        if ohlc is None or ohlc.empty:
            continue
        ohlc_yr = ohlc.loc[(ohlc.index >= "2025-01-01") & (ohlc.index <= "2025-12-31")]
        if ohlc_yr.empty:
            continue

        first_close = float(ohlc_yr["close"].iloc[0])
        last_close = float(ohlc_yr["close"].iloc[-1])
        min_low_yr = float(ohlc_yr["low"].min())
        peak_high_yr = float(ohlc_yr["high"].max())
        yr_ret = round(((last_close / first_close) - 1.0) * 100.0, 1)
        max_swing_gain = round(((peak_high_yr / min_low_yr) - 1.0) * 100.0, 1)

        sym_days = scored_by_sym_date.get(sym, {})
        l0_days = len(sym_days)
        l1_days = l2_days = l3_days = l4_act_days = l4_trig_days = 0
        first_l3_date = first_trig_date = ""
        first_l3_price = first_trig_price = 0.0

        for d_str in dates_2025:
            if d_str not in sym_days:
                continue
            r = sym_days[d_str]
            q1 = bool(r.get("qualified_all", False))
            q2 = q1 and bool(r.get("l2_qualified", False))
            q3 = q2 and bool(r.get("l3_qualified", False))
            q4 = q3 and bool(r.get("l4_qualified", False))
            is_trig = q3 and str(r.get("action_status", "")) == "TRIGGERED"

            if q1:
                l1_days += 1
            if q2:
                l2_days += 1
            if q3:
                l3_days += 1
                if not first_l3_date:
                    first_l3_date = d_str
                    first_l3_price = float(r["close"])
            if q4:
                l4_act_days += 1
            if is_trig:
                l4_trig_days += 1
                if not first_trig_date:
                    first_trig_date = d_str
                    first_trig_price = float(r["close"])

        ref_date = first_trig_date or first_l3_date
        ref_price = first_trig_price if first_trig_date else first_l3_price
        post_gain = 0.0
        if ref_date and ref_price > 0:
            after_df = ohlc_yr.loc[ohlc_yr.index >= ref_date]
            if not after_df.empty:
                subseq_high = float(after_df["high"].max())
                post_gain = round(((subseq_high / ref_price) - 1.0) * 100.0, 1)

        audit_rows.append(
            {
                "ticker": sym,
                "wave": item["wave"],
                "company_name": item["company_name"],
                "yr_2025_return_pct": yr_ret,
                "max_2025_low_to_high_pct": max_swing_gain,
                "l0_days": l0_days,
                "l1_days": l1_days,
                "l2_days": l2_days,
                "l3_days": l3_days,
                "l4_actionable_days": l4_act_days,
                "l4_triggered_days": l4_trig_days,
                "first_l3_setup_date": first_l3_date or "—",
                "first_l3_setup_price": first_l3_price,
                "first_triggered_date": first_trig_date or "—",
                "first_triggered_price": first_trig_price,
                "post_signal_peak_gain_pct": post_gain,
                "caught_by_screener": bool(l3_days > 0 or l4_act_days > 0),
                "caught_in_l4": bool(l4_act_days > 0),
            }
        )
    return audit_rows


def _enrich_ledger(trades: List[Dict[str, Any]], initial_equity: float = 100000.0) -> List[Dict[str, Any]]:
    running = initial_equity
    out = []
    for idx, t in enumerate(trades, start=1):
        init_sh = int(t["initial_shares"])
        buy_px = float(t["entry_price"])
        final_px = float(t["exit_price"])
        part_px = t.get("partial_exit_price")
        part_sh = int(t.get("partial_shares_sold") or 0)
        pnl = float(t["pnl_dollars"])

        if part_px is not None and part_sh > 0:
            part_px_f = float(part_px)
            rem_sh = init_sh - part_sh
            part_amt = round(part_sh * part_px_f, 2)
            final_amt = round(rem_sh * final_px, 2)
            total_sold_amt = round(part_amt + final_amt, 2)
            amt_spent = round(total_sold_amt - pnl, 2)
        else:
            part_sh = 0
            rem_sh = init_sh
            part_amt = 0.0
            total_sold_amt = round(init_sh * final_px, 2)
            amt_spent = round(total_sold_amt - pnl, 2)
            final_amt = total_sold_amt

        running = round(running + pnl, 2)
        cum_ret_pct = round(((running / initial_equity) - 1.0) * 100.0, 2)
        item = dict(t)
        item.update(
            {
                "trade_no": idx,
                "amount_spent": amt_spent,
                "partial_shares": part_sh,
                "partial_amount_sold": part_amt,
                "final_shares": rem_sh,
                "final_amount_sold": final_amt,
                "total_amount_sold": total_sold_amt,
                "running_total_asset": running,
                "cumulative_return_pct": cum_ret_pct,
            }
        )
        out.append(item)
    return out


def main() -> None:
    t0 = time.perf_counter()
    bundle = load_or_fetch_2025_dataset(force_refresh=False)
    print(f"Loaded 2025 dataset: {len(bundle['metadata_df'])} tickers, {len(bundle['ohlcv_map'])} OHLCV histories ({time.perf_counter()-t0:.1f}s)")

    t1 = time.perf_counter()
    panel = build_pit_panel(
        metadata_df=bundle["metadata_df"],
        ohlcv_map=bundle["ohlcv_map"],
        sp500_df=bundle["sp500_df"],
        eval_start="2024-12-20",
        eval_end="2025-12-31",
    )
    # Redirect `trading_dates_2024` key used by portfolio_simulator to the 2025 trading dates
    dates_2025 = [d for d in panel["all_eval_dates"] if "2025-01-01" <= d <= "2025-12-31"]
    panel["trading_dates_2024"] = dates_2025
    print(f"Built 2025 PIT feature panel across {len(dates_2025)} trading days ({time.perf_counter()-t1:.1f}s)")

    t2 = time.perf_counter()
    screens_default = precompute_daily_screens(panel, feature_mode="pit_clean")

    jlaw_preset_key = "🏆 JLaw 2024 USIC Championship ($1B Cap + RS≥85 + ADR≥3.2% + Hybrid Exit)"
    jlaw_preset = BUILTIN_PRESETS[jlaw_preset_key]
    screens_jlaw = precompute_daily_screens(
        panel,
        feature_mode="pit_clean",
        layer0_cfg=jlaw_preset["layer0"],
        layer1_cfg=jlaw_preset["layer1"],
        layer2_cfg=jlaw_preset["layer2"],
        layer3_cfg=jlaw_preset["layer3"],
        layer4_cfg=jlaw_preset["layer4"],
        layer5_cfg=jlaw_preset["layer5"],
    )
    print(f"Completed 2025 6-layer daily screening runs ({time.perf_counter()-t2:.1f}s)")

    recall_def = run_2025_recall_audit(panel, screens_default)
    recall_jlaw = run_2025_recall_audit(panel, screens_jlaw)

    runs: Dict[str, Dict[str, Any]] = {}
    # Default 2x2 Matrix
    runs["M1_Default_ModeA_Fixed25R"] = run_walk_forward_simulation(
        panel, screens_default, entry_mode="ON_DECK_STOP", exit_model="FIXED_2_5R"
    )
    runs["M2_Default_ModeA_JLawHybrid"] = run_walk_forward_simulation(
        panel, screens_default, entry_mode="ON_DECK_STOP", exit_model="JLAW_HYBRID"
    )
    runs["M3_Default_ModeB_Fixed25R"] = run_walk_forward_simulation(
        panel, screens_default, entry_mode="TRIGGERED_NEXT_OPEN", exit_model="FIXED_2_5R"
    )
    runs["M4_Default_ModeB_JLawHybrid"] = run_walk_forward_simulation(
        panel, screens_default, entry_mode="TRIGGERED_NEXT_OPEN", exit_model="JLAW_HYBRID"
    )

    # JLaw Preset @ 1% Risk (D2b)
    runs["D2b_JLawPreset_1PctRisk_2_5R_50Pct"] = run_walk_forward_simulation(
        panel,
        screens_jlaw,
        entry_mode="TRIGGERED_NEXT_OPEN",
        exit_model="JLAW_HYBRID",
        risk_pct_per_trade=1.0,
        max_alloc_pct=25.0,
        reward_risk_ratio=2.5,
        partial_sell_fraction=0.50,
        require_spy_above_ema21=True,
    )

    # JLaw Preset @ 2% Risk Baseline (D3b: +2.5R / 50% sold)
    runs["D3b_Baseline_2_5R_50Pct"] = run_walk_forward_simulation(
        panel,
        screens_jlaw,
        entry_mode="TRIGGERED_NEXT_OPEN",
        exit_model="JLAW_HYBRID",
        risk_pct_per_trade=2.0,
        max_alloc_pct=33.3,
        reward_risk_ratio=2.5,
        partial_sell_fraction=0.50,
        require_spy_above_ema21=True,
    )

    # What-If Scenario 1 on D3b (+3.0R Partial, 50% sold)
    runs["D3b_Scenario1_3_0R_50Pct"] = run_walk_forward_simulation(
        panel,
        screens_jlaw,
        entry_mode="TRIGGERED_NEXT_OPEN",
        exit_model="JLAW_HYBRID",
        risk_pct_per_trade=2.0,
        max_alloc_pct=33.3,
        reward_risk_ratio=3.0,
        partial_sell_fraction=0.50,
        require_spy_above_ema21=True,
    )

    # What-If Scenario 2 on D3b (+2.0R Partial, 40% sold)
    runs["D3b_Scenario2_2_0R_40Pct"] = run_walk_forward_simulation(
        panel,
        screens_jlaw,
        entry_mode="TRIGGERED_NEXT_OPEN",
        exit_model="JLAW_HYBRID",
        risk_pct_per_trade=2.0,
        max_alloc_pct=33.3,
        reward_risk_ratio=2.0,
        partial_sell_fraction=0.40,
        require_spy_above_ema21=True,
    )

    # Also test What-If Scenario 1 & 2 on M4 Default ($3B Cap, 1% Risk) for completeness
    runs["M4_Scenario1_3_0R_50Pct"] = run_walk_forward_simulation(
        panel,
        screens_default,
        entry_mode="TRIGGERED_NEXT_OPEN",
        exit_model="JLAW_HYBRID",
        reward_risk_ratio=3.0,
        partial_sell_fraction=0.50,
    )
    runs["M4_Scenario2_2_0R_40Pct"] = run_walk_forward_simulation(
        panel,
        screens_default,
        entry_mode="TRIGGERED_NEXT_OPEN",
        exit_model="JLAW_HYBRID",
        reward_risk_ratio=2.0,
        partial_sell_fraction=0.40,
    )

    print("\n================ 2025 FULL-YEAR BACKTEST SCORECARD ================")
    for name, rdata in runs.items():
        m = rdata["metrics"]
        print(
            f"{name:36s} | Return: {m['total_return_pct']:+7.2f}% | MaxDD: {m['max_drawdown_pct']:6.2f}% "
            f"| Trades: {m['total_trades']:3d} | Win%: {m['win_rate_pct']:5.1f}% "
            f"| PF: {m['profit_factor']:5.2f} | Sharpe: {m['sharpe_ratio']:4.2f}"
        )

    caught_def = sum(1 for r in recall_def if r["caught_by_screener"])
    caught_jlaw = sum(1 for r in recall_jlaw if r["caught_by_screener"])
    print(f"2025 Monster Winner Recall: Default={caught_def}/{len(recall_def)}, JLaw Preset={caught_jlaw}/{len(recall_jlaw)}")

    # Save structured JSON summary
    out_json = CACHE_DIR_2025 / "backtest_2025_results_summary.json"
    with open(out_json, "w", encoding="utf-8") as fh:
        json.dump(
            {
                "trading_days_2025": len(dates_2025),
                "recall_default": recall_def,
                "recall_jlaw": recall_jlaw,
                "simulations": {
                    k: {
                        "metrics": v["metrics"],
                        "trades": _enrich_ledger(v["trades"]),
                    }
                    for k, v in runs.items()
                },
            },
            fh,
            indent=2,
        )
    print(f"Saved 2025 JSON summary to: {out_json}")

    # Export Multi-Sheet Excel Report for 2025 Backtest + What-If Scenarios
    t_base = _enrich_ledger(runs["D3b_Baseline_2_5R_50Pct"]["trades"])
    t_s1 = _enrich_ledger(runs["D3b_Scenario1_3_0R_50Pct"]["trades"])
    t_s2 = _enrich_ledger(runs["D3b_Scenario2_2_0R_40Pct"]["trades"])

    score_rows = []
    labels_map = [
        ("M1_Default_ModeA_Fixed25R", "M1: Default ($3B Cap, 1% Risk) — Mode A (ON_DECK Stop) + Fixed +2.5R (100% Sold)"),
        ("M2_Default_ModeA_JLawHybrid", "M2: Default ($3B Cap, 1% Risk) — Mode A (ON_DECK Stop) + JLaw Hybrid (+2.5R / 50%)"),
        ("M3_Default_ModeB_Fixed25R", "M3: Default ($3B Cap, 1% Risk) — Mode B (TRIGGERED Open) + Fixed +2.5R (100% Sold)"),
        ("M4_Default_ModeB_JLawHybrid", "M4: Default ($3B Cap, 1% Risk) — Mode B (TRIGGERED Open) + JLaw Hybrid (+2.5R / 50%)"),
        ("M4_Scenario1_3_0R_50Pct", "M4 What-If 1: Default ($3B Cap, 1% Risk) — Partial +3.0R (50% Sold) + 21 EMA Trail"),
        ("M4_Scenario2_2_0R_40Pct", "M4 What-If 2: Default ($3B Cap, 1% Risk) — Partial +2.0R (40% Sold) + 21 EMA Trail"),
        ("D2b_JLawPreset_1PctRisk_2_5R_50Pct", "D2b: 🏆 JLaw Preset ($1B Cap, 1% Risk) — Mode B + JLaw Hybrid (+2.5R / 50%)"),
        ("D3b_Baseline_2_5R_50Pct", "D3b Baseline: 🏆 JLaw Preset ($1B Cap, 2% Risk) — Partial +2.5R (50% Sold) + 21 EMA Trail"),
        ("D3b_Scenario1_3_0R_50Pct", "D3b What-If 1: 🏆 JLaw Preset ($1B Cap, 2% Risk) — Partial +3.0R (50% Sold) + 21 EMA Trail"),
        ("D3b_Scenario2_2_0R_40Pct", "D3b What-If 2: 🏆 JLaw Preset ($1B Cap, 2% Risk) — Partial +2.0R (40% Sold) + 21 EMA Trail"),
    ]
    base_d3b_ret = runs["D3b_Baseline_2_5R_50Pct"]["metrics"]["total_return_pct"]
    for key, label in labels_map:
        m = runs[key]["metrics"]
        score_rows.append(
            {
                "Run Code": key,
                "Strategy Description": label,
                "2025 Initial Asset ($)": 100000.00,
                "2025 Final Total Asset ($)": m["final_equity"],
                "2025 Net Return (%)": m["total_return_pct"],
                "vs. D3b Baseline (%)": round(m["total_return_pct"] - base_d3b_ret, 2) if key.startswith("D3b_") else None,
                "S&P 500 2025 Return (%)": m["sp500_return_pct"],
                "JLaw 2025 USIC Official (%)": 252.30,
                "Max Drawdown (%)": m["max_drawdown_pct"],
                "Total Trades": m["total_trades"],
                "Win Rate (%)": m["win_rate_pct"],
                "Avg Win (%)": m["avg_win_pct"],
                "Avg Win (R)": m["avg_win_r"],
                "Avg Loss (%)": m["avg_loss_pct"],
                "Expectancy (R)": m["expectancy_r"],
                "Profit Factor": m["profit_factor"],
                "Sharpe Ratio": m["sharpe_ratio"],
                "Avg Invested (%)": m["avg_invested_pct"],
            }
        )
    df_score = pd.DataFrame(score_rows)

    # Side-by-side Trade Comparison for D3b Baseline vs What-If 1 (3R/50%) vs What-If 2 (2R/40%)
    map_b = {(t["ticker"], t["entry_date"]): t for t in t_base}
    map_1 = {(t["ticker"], t["entry_date"]): t for t in t_s1}
    map_2 = {(t["ticker"], t["entry_date"]): t for t in t_s2}
    all_keys = sorted(
        set(map_b.keys()) | set(map_1.keys()) | set(map_2.keys()),
        key=lambda k: (
            (map_b.get(k) or map_1.get(k) or map_2.get(k))["exit_date"],
            k[1],
            k[0],
        ),
    )

    comp_rows = []
    for idx, k in enumerate(all_keys, start=1):
        tb = map_b.get(k)
        t1 = map_1.get(k)
        t2 = map_2.get(k)
        ref = tb or t1 or t2

        b_ret = tb["return_pct"] if tb else None
        s1_ret = t1["return_pct"] if t1 else None
        s2_ret = t2["return_pct"] if t2 else None

        b_cum = tb["cumulative_return_pct"] if tb else None
        s1_cum = t1["cumulative_return_pct"] if t1 else None
        s2_cum = t2["cumulative_return_pct"] if t2 else None

        comp_rows.append(
            {
                "Trade #": idx,
                "Ticker": ref["ticker"],
                "Company Name": ref["company_name"],
                "Date of Purchase": ref["entry_date"],
                "Buy Price ($)": ref["entry_price"],
                "Base (+2.5R/50%) Exit Date": tb["exit_date"] if tb else "Not Taken",
                "Base Partial Price ($)": tb["partial_exit_price"] if tb else None,
                "Base Final Price ($)": tb["exit_price"] if tb else None,
                "Base Trade Return (%)": b_ret,
                "Base Trade PnL ($)": tb["pnl_dollars"] if tb else None,
                "Base Total Asset ($)": tb["running_total_asset"] if tb else None,
                "Base Cumulative Return (%)": b_cum,
                "Scen 1 (+3R/50%) Exit Date": t1["exit_date"] if t1 else "Not Taken",
                "Scen 1 Partial Price ($)": t1["partial_exit_price"] if t1 else None,
                "Scen 1 Final Price ($)": t1["exit_price"] if t1 else None,
                "Scen 1 Trade Return (%)": s1_ret,
                "Scen 1 Trade Return Change vs Base (%)": round(s1_ret - b_ret, 2) if (s1_ret is not None and b_ret is not None) else None,
                "Scen 1 Trade PnL ($)": t1["pnl_dollars"] if t1 else None,
                "Scen 1 Total Asset ($)": t1["running_total_asset"] if t1 else None,
                "Scen 1 Cumulative Return (%)": s1_cum,
                "Scen 1 Cumul. Return Change vs Base (%)": round(s1_cum - b_cum, 2) if (s1_cum is not None and b_cum is not None) else None,
                "Scen 2 (+2R/40%) Exit Date": t2["exit_date"] if t2 else "Not Taken",
                "Scen 2 Partial Price ($)": t2["partial_exit_price"] if t2 else None,
                "Scen 2 Final Price ($)": t2["exit_price"] if t2 else None,
                "Scen 2 Trade Return (%)": s2_ret,
                "Scen 2 Trade Return Change vs Base (%)": round(s2_ret - b_ret, 2) if (s2_ret is not None and b_ret is not None) else None,
                "Scen 2 Trade PnL ($)": t2["pnl_dollars"] if t2 else None,
                "Scen 2 Total Asset ($)": t2["running_total_asset"] if t2 else None,
                "Scen 2 Cumulative Return (%)": s2_cum,
                "Scen 2 Cumul. Return Change vs Base (%)": round(s2_cum - b_cum, 2) if (s2_cum is not None and b_cum is not None) else None,
            }
        )
    df_comp = pd.DataFrame(comp_rows)

    def _to_ledger_df(enriched: List[Dict[str, Any]]) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "Trade #": t["trade_no"],
                    "Ticker": t["ticker"],
                    "Company Name": t["company_name"],
                    "Date of Purchase": t["entry_date"],
                    "Shares Purchased": t["initial_shares"],
                    "Buy Price ($)": t["entry_price"],
                    "Amount Spent ($)": t["amount_spent"],
                    "Partial Exit Date": t.get("partial_exit_date") or "—",
                    "Partial Shares Sold": t["partial_shares"],
                    "Partial Sell Price ($)": t["partial_exit_price"],
                    "Partial Amount Sold ($)": t["partial_amount_sold"],
                    "Date of Final Selling": t["exit_date"],
                    "Final Shares Sold": t["final_shares"],
                    "Final Sell Price ($)": t["exit_price"],
                    "Final Amount Sold ($)": t["final_amount_sold"],
                    "Total Shares Sold": t["initial_shares"],
                    "Total Amount Sold ($)": t["total_amount_sold"],
                    "Net Profit / Loss ($)": t["pnl_dollars"],
                    "Trade Return (%)": t["return_pct"],
                    "R-Multiple (R)": t["r_multiple"],
                    "Net Total Asset ($)": t["running_total_asset"],
                    "Total Asset Cumulative Return (%)": t["cumulative_return_pct"],
                    "Exit Reason": t["exit_reason"],
                }
                for t in enriched
            ]
        )

    df_b_full = _to_ledger_df(t_base)
    df_s1_full = _to_ledger_df(t_s1)
    df_s2_full = _to_ledger_df(t_s2)
    df_recall = pd.DataFrame(recall_jlaw)

    xlsx_path = OUT_DIR / "Backtest_2025_FullYear_JLaw_USIC_and_WhatIf_Report.xlsx"
    csv_path = OUT_DIR / "Backtest_2025_FullYear_JLaw_USIC_and_WhatIf_Report.csv"
    df_comp.to_csv(csv_path, index=False, encoding="utf-8-sig")

    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        df_score.to_excel(writer, sheet_name="1_2025_Executive_Scorecard", index=False)
        df_comp.to_excel(writer, sheet_name="2_D3b_WhatIf_Trade_Comparison", index=False)
        df_b_full.to_excel(writer, sheet_name="3_D3b_Baseline_2.5R_50Pct", index=False)
        df_s1_full.to_excel(writer, sheet_name="4_D3b_Scen1_3.0R_50Pct", index=False)
        df_s2_full.to_excel(writer, sheet_name="5_D3b_Scen2_2.0R_40Pct", index=False)
        df_recall.to_excel(writer, sheet_name="6_2025_Monster_Winners_Recall", index=False)

        header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True, size=10)
        win_fill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
        loss_fill = PatternFill(start_color="FCE4D6", end_color="FCE4D6", fill_type="solid")
        thin_border = Border(
            left=Side(style="thin", color="D9D9D9"),
            right=Side(style="thin", color="D9D9D9"),
            top=Side(style="thin", color="D9D9D9"),
            bottom=Side(style="thin", color="D9D9D9"),
        )

        for sname in writer.sheets:
            ws = writer.sheets[sname]
            ws.row_dimensions[1].height = 30
            ws.freeze_panes = "C2"
            for col_idx in range(1, ws.max_column + 1):
                c = ws.cell(row=1, column=col_idx)
                c.fill = header_fill
                c.font = header_font
                c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

            for row_idx in range(2, ws.max_row + 1):
                for col_idx in range(1, ws.max_column + 1):
                    c = ws.cell(row=row_idx, column=col_idx)
                    c.border = thin_border
                    if sname == "1_2025_Executive_Scorecard":
                        val = ws.cell(row=row_idx, column=5).value or 0.0
                        c.fill = win_fill if val > 0 else loss_fill
                    elif sname == "6_2025_Monster_Winners_Recall":
                        caught = bool(ws.cell(row=row_idx, column=17).value)
                        c.fill = win_fill if caught else loss_fill
                    else:
                        pnl_col = 10 if sname == "2_D3b_WhatIf_Trade_Comparison" else 18
                        val = ws.cell(row=row_idx, column=pnl_col).value
                        c.fill = win_fill if (isinstance(val, (int, float)) and val > 0) else loss_fill

            for col_idx in range(1, ws.max_column + 1):
                col_letter = get_column_letter(col_idx)
                max_len = max(
                    len(str(ws.cell(row=r, column=col_idx).value or ""))
                    for r in range(1, ws.max_row + 1)
                )
                ws.column_dimensions[col_letter].width = max(13, min(max_len + 4, 34))

    print(f"Exported 2025 Excel workbook to: {xlsx_path}")


if __name__ == "__main__":
    main()
