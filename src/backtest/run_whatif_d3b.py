"""
Run What-If Scenario Comparison on D3b (🏆 JLaw 2024 USIC Championship Preset, 2.0% Risk, 33.3% Max Alloc):
- Baseline: Partial Exit at +2.5R (50% sold) + 21 EMA Trail (50% held)
- Scenario 1: Partial Exit at +3.0R (50% sold) + 21 EMA Trail (50% held)
- Scenario 2: Partial Exit at +2.0R (40% sold) + 21 EMA Trail (60% held)

Exports a formatted multi-sheet Excel workbook (`D3b_2024_WhatIf_3R_vs_2R40Pct_Comparison.xlsx`) and `.csv` file.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List
import pandas as pd

from src.backtest.historical_data_loader import load_or_fetch_2024_historical_dataset
from src.backtest.pit_feature_engine import build_pit_panel
from src.backtest.portfolio_simulator import precompute_daily_screens, run_walk_forward_simulation
from src.config.builtin_presets import BUILTIN_PRESETS

CACHE_DIR = Path(
    r"C:\Users\User\.gemini\antigravity\brain\9c87e4f7-7ae9-4bd7-9d9b-53c0f1e12b32\scratch\backtest_2024_cache"
)
OUT_DIR = Path(
    r"C:\Users\User\.gemini\antigravity\brain\9c87e4f7-7ae9-4bd7-9d9b-53c0f1e12b32"
)


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
        ret_pct = float(t["return_pct"])
        r_mult = float(t["r_multiple"])

        if part_px is not None and part_sh > 0:
            part_px_f = float(part_px)
            rem_sh = init_sh - part_sh
            part_amt = round(part_sh * part_px_f, 2)
            final_amt = round(rem_sh * final_px, 2)
            total_sold_amt = round(part_amt + final_amt, 2)
            amt_spent = round(total_sold_amt - pnl, 2)
        else:
            part_px_f = None
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
    bundle = load_or_fetch_2024_historical_dataset(cache_dir=CACHE_DIR, target_pool_size=1050, force_refresh=False)
    panel = build_pit_panel(
        metadata_df=bundle["metadata_df"],
        ohlcv_map=bundle["ohlcv_map"],
        sp500_df=bundle["sp500_df"],
    )

    jlaw_preset_key = "🏆 JLaw 2024 USIC Championship ($1B Cap + RS≥85 + ADR≥3.2% + Hybrid Exit)"
    jlaw_preset = BUILTIN_PRESETS[jlaw_preset_key]
    screens_pro = precompute_daily_screens(
        panel,
        feature_mode="pit_clean",
        layer0_cfg=jlaw_preset["layer0"],
        layer1_cfg=jlaw_preset["layer1"],
        layer2_cfg=jlaw_preset["layer2"],
        layer3_cfg=jlaw_preset["layer3"],
        layer4_cfg=jlaw_preset["layer4"],
        layer5_cfg=jlaw_preset["layer5"],
    )

    # 1. Baseline: +2.5R Partial (50% sold)
    sim_base = run_walk_forward_simulation(
        panel,
        screens_pro,
        entry_mode="TRIGGERED_NEXT_OPEN",
        exit_model="JLAW_HYBRID",
        risk_pct_per_trade=2.0,
        max_alloc_pct=33.3,
        reward_risk_ratio=2.5,
        partial_sell_fraction=0.50,
        require_spy_above_ema21=True,
    )

    # 2. Scenario 1: +3.0R Partial (50% sold)
    sim_s1 = run_walk_forward_simulation(
        panel,
        screens_pro,
        entry_mode="TRIGGERED_NEXT_OPEN",
        exit_model="JLAW_HYBRID",
        risk_pct_per_trade=2.0,
        max_alloc_pct=33.3,
        reward_risk_ratio=3.0,
        partial_sell_fraction=0.50,
        require_spy_above_ema21=True,
    )

    # 3. Scenario 2: +2.0R Partial (40% sold)
    sim_s2 = run_walk_forward_simulation(
        panel,
        screens_pro,
        entry_mode="TRIGGERED_NEXT_OPEN",
        exit_model="JLAW_HYBRID",
        risk_pct_per_trade=2.0,
        max_alloc_pct=33.3,
        reward_risk_ratio=2.0,
        partial_sell_fraction=0.40,
        require_spy_above_ema21=True,
    )

    t_base = _enrich_ledger(sim_base["trades"])
    t_s1 = _enrich_ledger(sim_s1["trades"])
    t_s2 = _enrich_ledger(sim_s2["trades"])

    # Save raw JSON for quick inspection
    summary_json = OUT_DIR / "scratch" / "whatif_d3b_results.json"
    with open(summary_json, "w", encoding="utf-8") as fh:
        json.dump(
            {
                "baseline_2_5R_50pct": {"metrics": sim_base["metrics"], "trades": t_base},
                "scenario1_3_0R_50pct": {"metrics": sim_s1["metrics"], "trades": t_s1},
                "scenario2_2_0R_40pct": {"metrics": sim_s2["metrics"], "trades": t_s2},
            },
            fh,
            indent=2,
        )

    # Build Sheet 1: Executive Portfolio Summary Table
    m0 = sim_base["metrics"]
    m1 = sim_s1["metrics"]
    m2 = sim_s2["metrics"]

    df_exec = pd.DataFrame(
        [
            {
                "Scenario": "Baseline (Current D3b)",
                "Partial Exit Rule": "Sell 50% at +2.5R | Trail 50% on 21 EMA",
                "Initial Capital ($)": 100000.00,
                "Final Total Asset ($)": m0["final_equity"],
                "Total Asset Cumulative Return (%)": m0["total_return_pct"],
                "Return Change vs. Baseline (%)": 0.00,
                "Net Dollar Change vs. Baseline ($)": 0.00,
                "Max Drawdown (%)": m0["max_drawdown_pct"],
                "Total Trades": m0["total_trades"],
                "Win Rate (%)": m0["win_rate_pct"],
                "Avg Win (%)": m0["avg_win_pct"],
                "Avg Win (R)": m0["avg_win_r"],
                "Avg Loss (%)": m0["avg_loss_pct"],
                "Expectancy per Trade (R)": m0["expectancy_r"],
                "Profit Factor": m0["profit_factor"],
                "Sharpe Ratio": m0["sharpe_ratio"],
            },
            {
                "Scenario": "What-If Scenario 1 (+3.0R Partial, 50% Sold)",
                "Partial Exit Rule": "Sell 50% at +3.0R | Trail 50% on 21 EMA",
                "Initial Capital ($)": 100000.00,
                "Final Total Asset ($)": m1["final_equity"],
                "Total Asset Cumulative Return (%)": m1["total_return_pct"],
                "Return Change vs. Baseline (%)": round(m1["total_return_pct"] - m0["total_return_pct"], 2),
                "Net Dollar Change vs. Baseline ($)": round(m1["final_equity"] - m0["final_equity"], 2),
                "Max Drawdown (%)": m1["max_drawdown_pct"],
                "Total Trades": m1["total_trades"],
                "Win Rate (%)": m1["win_rate_pct"],
                "Avg Win (%)": m1["avg_win_pct"],
                "Avg Win (R)": m1["avg_win_r"],
                "Avg Loss (%)": m1["avg_loss_pct"],
                "Expectancy per Trade (R)": m1["expectancy_r"],
                "Profit Factor": m1["profit_factor"],
                "Sharpe Ratio": m1["sharpe_ratio"],
            },
            {
                "Scenario": "What-If Scenario 2 (+2.0R Partial, 40% Sold)",
                "Partial Exit Rule": "Sell 40% at +2.0R | Trail 60% on 21 EMA",
                "Initial Capital ($)": 100000.00,
                "Final Total Asset ($)": m2["final_equity"],
                "Total Asset Cumulative Return (%)": m2["total_return_pct"],
                "Return Change vs. Baseline (%)": round(m2["total_return_pct"] - m0["total_return_pct"], 2),
                "Net Dollar Change vs. Baseline ($)": round(m2["final_equity"] - m0["final_equity"], 2),
                "Max Drawdown (%)": m2["max_drawdown_pct"],
                "Total Trades": m2["total_trades"],
                "Win Rate (%)": m2["win_rate_pct"],
                "Avg Win (%)": m2["avg_win_pct"],
                "Avg Win (R)": m2["avg_win_r"],
                "Avg Loss (%)": m2["avg_loss_pct"],
                "Expectancy per Trade (R)": m2["expectancy_r"],
                "Profit Factor": m2["profit_factor"],
                "Sharpe Ratio": m2["sharpe_ratio"],
            },
        ]
    )

    # Build Sheet 2: Side-by-Side Trade-by-Trade Return & Cumulative Asset Comparison
    # Index trades by (ticker, entry_date) for exact 1-to-1 matching
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

        b_r = tb["r_multiple"] if tb else None
        s1_r = t1["r_multiple"] if t1 else None
        s2_r = t2["r_multiple"] if t2 else None

        b_pnl = tb["pnl_dollars"] if tb else 0.0
        s1_pnl = t1["pnl_dollars"] if t1 else 0.0
        s2_pnl = t2["pnl_dollars"] if t2 else 0.0

        b_cum = tb["cumulative_return_pct"] if tb else None
        s1_cum = t1["cumulative_return_pct"] if t1 else None
        s2_cum = t2["cumulative_return_pct"] if t2 else None

        b_asset = tb["running_total_asset"] if tb else None
        s1_asset = t1["running_total_asset"] if t1 else None
        s2_asset = t2["running_total_asset"] if t2 else None

        comp_rows.append(
            {
                "Trade #": idx,
                "Ticker": ref["ticker"],
                "Company Name": ref["company_name"],
                "Date of Purchase": ref["entry_date"],
                "Buy Price ($)": ref["entry_price"],
                # Baseline (+2.5R, 50%)
                "Base (+2.5R/50%) Exit Date": tb["exit_date"] if tb else "Not Taken",
                "Base Partial Price ($)": tb["partial_exit_price"] if tb else None,
                "Base Final Price ($)": tb["exit_price"] if tb else None,
                "Base Trade Return (%)": b_ret,
                "Base R-Multiple (R)": b_r,
                "Base Trade PnL ($)": b_pnl if tb else None,
                "Base Total Asset ($)": b_asset,
                "Base Cumulative Return (%)": b_cum,
                # Scenario 1 (+3.0R, 50%)
                "Scen 1 (+3R/50%) Exit Date": t1["exit_date"] if t1 else "Not Taken",
                "Scen 1 Partial Price ($)": t1["partial_exit_price"] if t1 else None,
                "Scen 1 Final Price ($)": t1["exit_price"] if t1 else None,
                "Scen 1 Trade Return (%)": s1_ret,
                "Scen 1 Trade Return Change vs Base (%)": round(s1_ret - b_ret, 2) if (s1_ret is not None and b_ret is not None) else None,
                "Scen 1 R-Multiple (R)": s1_r,
                "Scen 1 Trade PnL ($)": s1_pnl if t1 else None,
                "Scen 1 Total Asset ($)": s1_asset,
                "Scen 1 Cumulative Return (%)": s1_cum,
                "Scen 1 Cumul. Return Change vs Base (%)": round(s1_cum - b_cum, 2) if (s1_cum is not None and b_cum is not None) else None,
                # Scenario 2 (+2.0R, 40%)
                "Scen 2 (+2R/40%) Exit Date": t2["exit_date"] if t2 else "Not Taken",
                "Scen 2 Partial Price ($)": t2["partial_exit_price"] if t2 else None,
                "Scen 2 Final Price ($)": t2["exit_price"] if t2 else None,
                "Scen 2 Trade Return (%)": s2_ret,
                "Scen 2 Trade Return Change vs Base (%)": round(s2_ret - b_ret, 2) if (s2_ret is not None and b_ret is not None) else None,
                "Scen 2 R-Multiple (R)": s2_r,
                "Scen 2 Trade PnL ($)": s2_pnl if t2 else None,
                "Scen 2 Total Asset ($)": s2_asset,
                "Scen 2 Cumulative Return (%)": s2_cum,
                "Scen 2 Cumul. Return Change vs Base (%)": round(s2_cum - b_cum, 2) if (s2_cum is not None and b_cum is not None) else None,
                # Notes
                "What Changed & Why": (
                    "Identical (-1R Stop-Loss before +2R)"
                    if (tb and t1 and t2 and tb["partial_exit_price"] is None and t1["partial_exit_price"] is None and t2["partial_exit_price"] is None)
                    else (
                        f"Base: {tb['exit_reason'] if tb else 'N/A'} | "
                        f"S1(3R): {t1['exit_reason'] if t1 else 'N/A'} | "
                        f"S2(2R/40%): {t2['exit_reason'] if t2 else 'N/A'}"
                    )
                ),
            }
        )

    df_comp = pd.DataFrame(comp_rows)

    def _to_sheet_df(enriched: List[Dict[str, Any]]) -> pd.DataFrame:
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

    df_s1_full = _to_sheet_df(t_s1)
    df_s2_full = _to_sheet_df(t_s2)

    xlsx_path = OUT_DIR / "D3b_2024_WhatIf_3R_vs_2R40Pct_Comparison.xlsx"
    csv_path = OUT_DIR / "D3b_2024_WhatIf_3R_vs_2R40Pct_Comparison.csv"
    df_comp.to_csv(csv_path, index=False, encoding="utf-8-sig")

    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        df_exec.to_excel(writer, sheet_name="1_Executive_Summary", index=False)
        df_comp.to_excel(writer, sheet_name="2_Trade_by_Trade_Comparison", index=False)
        df_s1_full.to_excel(writer, sheet_name="3_Scenario1_3R_50Pct_Ledger", index=False)
        df_s2_full.to_excel(writer, sheet_name="4_Scenario2_2R_40Pct_Ledger", index=False)

        header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True, size=10)
        win_fill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
        loss_fill = PatternFill(start_color="FCE4D6", end_color="FCE4D6", fill_type="solid")
        neutral_fill = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
        thin_border = Border(
            left=Side(style="thin", color="D9D9D9"),
            right=Side(style="thin", color="D9D9D9"),
            top=Side(style="thin", color="D9D9D9"),
            bottom=Side(style="thin", color="D9D9D9"),
        )

        for sname in writer.sheets:
            ws = writer.sheets[sname]
            ws.row_dimensions[1].height = 30
            ws.freeze_panes = "E2" if sname == "2_Trade_by_Trade_Comparison" else "C2"
            for col_idx in range(1, ws.max_column + 1):
                c = ws.cell(row=1, column=col_idx)
                c.fill = header_fill
                c.font = header_font
                c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

            for row_idx in range(2, ws.max_row + 1):
                for col_idx in range(1, ws.max_column + 1):
                    c = ws.cell(row=row_idx, column=col_idx)
                    c.border = thin_border
                    if sname == "1_Executive_Summary":
                        c.fill = win_fill if row_idx == 4 else (neutral_fill if row_idx == 2 else loss_fill)
                    else:
                        # Highlight winners vs losers
                        pnl_col = 11 if sname == "2_Trade_by_Trade_Comparison" else 18
                        val = ws.cell(row=row_idx, column=pnl_col).value
                        c.fill = win_fill if (isinstance(val, (int, float)) and val > 0) else loss_fill

            for col_idx in range(1, ws.max_column + 1):
                col_letter = get_column_letter(col_idx)
                max_len = max(
                    len(str(ws.cell(row=r, column=col_idx).value or ""))
                    for r in range(1, ws.max_row + 1)
                )
                ws.column_dimensions[col_letter].width = max(13, min(max_len + 4, 34))

    print("\n================ WHAT-IF SCENARIO SUMMARY ================")
    print(f"Baseline (+2.5R / 50% sold): Final=${m0['final_equity']:,.2f} ({m0['total_return_pct']:+.2f}%) | MaxDD={m0['max_drawdown_pct']:.2f}% | Win%={m0['win_rate_pct']:.1f}% | PF={m0['profit_factor']:.2f}")
    print(f"Scenario 1 (+3.0R / 50% sold): Final=${m1['final_equity']:,.2f} ({m1['total_return_pct']:+.2f}%, {m1['total_return_pct']-m0['total_return_pct']:+.2f}%) | MaxDD={m1['max_drawdown_pct']:.2f}% | Win%={m1['win_rate_pct']:.1f}% | PF={m1['profit_factor']:.2f}")
    print(f"Scenario 2 (+2.0R / 40% sold): Final=${m2['final_equity']:,.2f} ({m2['total_return_pct']:+.2f}%, {m2['total_return_pct']-m0['total_return_pct']:+.2f}%) | MaxDD={m2['max_drawdown_pct']:.2f}% | Win%={m2['win_rate_pct']:.1f}% | PF={m2['profit_factor']:.2f}")
    print(f"Saved Excel workbook to: {xlsx_path}")


if __name__ == "__main__":
    main()
