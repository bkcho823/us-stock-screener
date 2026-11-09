"""
2024 Walk-Forward Portfolio Simulator & Monster Winner Recall Auditor (`src/backtest/portfolio_simulator.py`).

Implements:
  - Phase A: 28-Stock Signature 2024 Monster Winner Recall & Bottleneck Audit
  - Phase B: Full 252-Day Walk-Forward Portfolio Simulation (Jan 2 - Dec 31, 2024)
    comparing:
      * Entry Mode A (`ON_DECK_STOP`): Pre-set intraday Buy-Stop at `pivot_price` for stocks
        flagged `ON_DECK` at Day `T-1` close (skipping excessive gap-ups > +5% above pivot).
      * Entry Mode B (`TRIGGERED_NEXT_OPEN`): Buy at `Open[T]` for stocks flagged `TRIGGERED`
        at Day `T-1` close (provided `Open[T] <= pivot_price * 1.05`).
    crossed with:
      * Exit Model 1 (`FIXED_2_5R`): Mechanical Layer 5 exit — Hard Stop at `-1R`, sell 100% at `+2.5R`.
      * Exit Model 2 (`JLAW_HYBRID`): Championship Hybrid — Hard Stop at `-1R`, sell 50% at `+2.5R`
        (and raise stop on remaining 50% to breakeven), trail remaining 50% until daily `Close < EMA21`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.backtest.historical_data_loader import SIGNATURE_2024_WINNERS
from src.backtest.pit_feature_engine import extract_day_universe
from src.config.settings import (
    get_default_layer0_config,
    get_default_layer1_config,
    get_default_layer2_config,
    get_default_layer3_config,
    get_default_layer4_config,
    get_default_layer5_config,
)
from src.layers.pipeline import run_screening_pipeline


@dataclass
class OpenPosition:
    ticker: str
    company_name: str
    sector: str
    industry: str
    signal_date: str
    entry_date: str
    entry_price: float
    initial_shares: int
    remaining_shares: int
    initial_stop: float
    current_stop: float
    risk_per_share: float
    target_price: float
    vcp_score: float
    composite_score: float
    rs_percentile: int
    partial_taken: bool = False
    realized_pnl: float = 0.0
    partial_exit_date: str = ""
    partial_exit_price: float = 0.0
    partial_shares_sold: int = 0


def precompute_daily_screens(
    panel: Dict[str, Any],
    feature_mode: str = "pit_clean",
    layer0_cfg: Optional[Dict[str, Any]] = None,
    layer1_cfg: Optional[Dict[str, Any]] = None,
    layer2_cfg: Optional[Dict[str, Any]] = None,
    layer3_cfg: Optional[Dict[str, Any]] = None,
    layer4_cfg: Optional[Dict[str, Any]] = None,
    layer5_cfg: Optional[Dict[str, Any]] = None,
    use_local_20d_pivot: bool = False,
) -> Dict[str, Dict[str, Any]]:
    """
    Runs `run_screening_pipeline` across every evaluation date (last week of Dec 2023 + all 252 days of 2024)
    and stores the daily `ScreeningPipelineResult` dictionary.
    """
    l0 = layer0_cfg or get_default_layer0_config()
    l1 = layer1_cfg or get_default_layer1_config()
    l2 = layer2_cfg or get_default_layer2_config()
    l3 = layer3_cfg or get_default_layer3_config()
    l4 = layer4_cfg or get_default_layer4_config()
    l5 = layer5_cfg or get_default_layer5_config()

    daily_results: Dict[str, Dict[str, Any]] = {}
    for d_str in panel["all_eval_dates"]:
        df_univ, sp500_bm = extract_day_universe(panel, d_str, feature_mode=feature_mode)
        if df_univ.empty:
            continue

        res = run_screening_pipeline(
            df_universe=df_univ,
            sp500_bm=sp500_bm,
            layer0_cfg=l0,
            layer1_cfg=l1,
            layer2_cfg=l2,
            layer3_cfg=l3,
            layer4_cfg=l4,
            layer5_cfg=l5,
        )
        df_scored = res.df_scored

        # Optional Pro enhancement diagnostic: replace artificial `close*(1+offset)` fallback
        # with actual 20-day local consolidation high (`swing_high_20d_pit`) when >8% below 52W high
        if use_local_20d_pivot and not df_scored.empty and "swing_high_20d_pit" in df_scored.columns:
            df_scored = _recompute_layer4_with_local_swing_pivot(df_scored, l4)

        daily_results[d_str] = {
            "df_scored": df_scored,
            "summary_meta": res.summary_meta,
            "sp500_bm": sp500_bm,
        }
    return daily_results


def _recompute_layer4_with_local_swing_pivot(
    df_scored: pd.DataFrame,
    layer4_cfg: Dict[str, Any],
) -> pd.DataFrame:
    """
    Diagnostic helper: uses actual 20-day consolidation swing high (`swing_high_20d_pit`)
    as pivot resistance whenever a stock is consolidating >8% below its 52-week high.
    """
    df = df_scored.copy()
    min_vol_exp = float(layer4_cfg.get("min_vol_expansion_pct", 120.0))
    max_bz = float(layer4_cfg.get("max_buy_zone_pct", 3.5))
    on_deck_pct = float(layer4_cfg.get("on_deck_pct", 3.0))

    pivots = []
    for _, r in df.iterrows():
        c = float(r["close"])
        h52 = float(r["high_52w"])
        sw20 = float(r.get("swing_high_20d_pit", h52))
        if h52 > 0 and c >= h52:
            piv = h52
        elif h52 > 0 and ((h52 - c) / c) <= 0.08:
            piv = h52
        else:
            piv = sw20 if sw20 > 0 else c
        pivots.append(round(piv, 2))

    df["pivot_price"] = pivots
    df["dist_to_pivot_pct"] = (((df["close"] - df["pivot_price"]) / df["pivot_price"]) * 100.0).round(2)

    statuses = []
    for _, r in df.iterrows():
        dist = float(r["dist_to_pivot_pct"])
        vexp = float(r["vol_expansion_pct"])
        if 0.0 <= dist <= max_bz and vexp >= min_vol_exp:
            statuses.append("TRIGGERED")
        elif 0.0 <= dist <= max_bz:
            statuses.append("BUY_ZONE")
        elif -on_deck_pct <= dist < 0.0:
            statuses.append("ON_DECK")
        elif dist > max_bz:
            statuses.append("EXTENDED")
        else:
            statuses.append("BUILDING")
    df["action_status"] = statuses
    df["l4_qualified"] = df["action_status"].isin(["TRIGGERED", "BUY_ZONE", "ON_DECK"])
    return df


def run_monster_winner_recall_audit(
    panel: Dict[str, Any],
    daily_screens: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Phase A: Audits all 28 Signature 2024 US Momentum Leaders across every 2024 trading day.
    Determines exact recall rate, first actionable setup date & price, subsequent peak gain,
    and primary filter bottleneck when delayed or missed.
    """
    dates_2024 = panel["trading_dates_2024"]
    ohlc_by_sym = panel["ohlc_by_sym"]
    by_date_raw = panel["by_date"]

    # Index daily scored rows per ticker for fast O(1) audit
    scored_by_sym_date: Dict[str, Dict[str, pd.Series]] = {w["ticker"]: {} for w in SIGNATURE_2024_WINNERS}
    for d_str in dates_2024:
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
    for item in SIGNATURE_2024_WINNERS:
        sym = item["ticker"]
        ohlc = ohlc_by_sym.get(sym)
        if ohlc is None or ohlc.empty:
            audit_rows.append(
                {
                    "ticker": sym,
                    "wave": item["wave"],
                    "company_name": item["company_name"],
                    "data_available": False,
                    "yr_2024_return_pct": 0.0,
                    "max_2024_gain_pct": 0.0,
                    "days_in_2024": 0,
                    "l0_days": 0,
                    "l1_days": 0,
                    "l2_days": 0,
                    "l3_days": 0,
                    "l4_actionable_days": 0,
                    "l4_triggered_days": 0,
                    "first_l3_setup_date": "—",
                    "first_l3_setup_price": 0.0,
                    "first_triggered_date": "—",
                    "first_triggered_price": 0.0,
                    "post_signal_peak_gain_pct": 0.0,
                    "caught_by_screener": False,
                    "bottleneck_diagnosis": "No OHLCV data",
                }
            )
            continue

        ohlc_2024 = ohlc.loc[(ohlc.index >= "2024-01-01") & (ohlc.index <= "2024-12-31")]
        if ohlc_2024.empty:
            continue

        first_close = float(ohlc_2024["close"].iloc[0])
        last_close = float(ohlc_2024["close"].iloc[-1])
        peak_high_2024 = float(ohlc_2024["high"].max())
        yr_ret = round(((last_close / first_close) - 1.0) * 100.0, 1)
        max_gain_from_jan = round(((peak_high_2024 / first_close) - 1.0) * 100.0, 1)

        sym_days = scored_by_sym_date.get(sym, {})
        l0_days = len(sym_days)
        l1_days = 0
        l2_days = 0
        l3_days = 0
        l4_act_days = 0
        l4_trig_days = 0

        first_l3_date = ""
        first_l3_price = 0.0
        first_trig_date = ""
        first_trig_price = 0.0

        l1_miss_reasons: Dict[str, int] = {}

        for d_str in dates_2024:
            if d_str not in sym_days:
                continue
            r = sym_days[d_str]
            q1 = bool(r.get("qualified_all", False))
            q2 = q1 and bool(r.get("l2_qualified", False))
            q3 = q2 and bool(r.get("l3_qualified", False))
            q4 = q3 and bool(r.get("l4_qualified", False))
            is_trig = q3 and str(r.get("action_status", "")) == "TRIGGERED"

            if not q1:
                for cid in ["c1", "c2", "c3", "c4", "c5", "c6", "c7", "c8", "c9", "c10", "c11"]:
                    if not bool(r.get(f"{cid}_pass", True)):
                        l1_miss_reasons[cid.upper()] = l1_miss_reasons.get(cid.upper(), 0) + 1

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

        # Compute post-signal gain to subsequent 2024 high
        ref_date = first_trig_date or first_l3_date
        ref_price = first_trig_price if first_trig_date else first_l3_price
        post_gain = 0.0
        if ref_date and ref_price > 0:
            after_df = ohlc_2024.loc[ohlc_2024.index >= ref_date]
            if not after_df.empty:
                subseq_high = float(after_df["high"].max())
                post_gain = round(((subseq_high / ref_price) - 1.0) * 100.0, 1)

        # Bottleneck diagnosis when stock had 0 L3/L4 days or delayed entry
        max_bar_age = int(ohlc_2024["bar_age"].max())
        min_mkt_cap_2024 = 0.0
        max_mkt_cap_2024 = 0.0
        raw_mc_vals = []
        for d_str in dates_2024:
            bdf = by_date_raw.get(d_str)
            if bdf is not None:
                m = bdf[bdf["ticker"] == sym]
                if not m.empty:
                    raw_mc_vals.append(float(m.iloc[0]["market_cap_b"]))
        if raw_mc_vals:
            min_mkt_cap_2024 = round(min(raw_mc_vals), 2)
            max_mkt_cap_2024 = round(max(raw_mc_vals), 2)

        if max_bar_age < 200 and l3_days == 0 and l4_act_days == 0:
            diag = f"Recent IPO/Spin-off ({max_bar_age} bars < 200D SMA warmup)"
        elif l0_days == 0:
            diag = f"Blocked at L0 (Mkt Cap ${min_mkt_cap_2024:.1f}B-${max_mkt_cap_2024:.1f}B < Floor or Dollar Vol)"
        elif l1_days == 0:
            top_miss = sorted(l1_miss_reasons.items(), key=lambda x: x[1], reverse=True)[:2]
            miss_str = ", ".join(f"{k}" for k, _ in top_miss)
            diag = f"Blocked at L1 Trend ({miss_str})"
        elif l2_days == 0:
            diag = "Blocked at L2 Industry Rank"
        elif l3_days == 0:
            diag = "Passed L1+L2 Trend, but range >8% (high-volatility parabolic leader)"
        elif l4_act_days == 0:
            diag = "Passed L3 VCP, but >8% below 52W High (local pivot bug)"
        else:
            if max_bar_age < 200:
                diag = f"✅ Caught via P2 IPO Stage 2 Mode ({max_bar_age} bars)"
            elif min_mkt_cap_2024 < 3.0 and l0_days < 180:
                diag = f"✅ Caught (Note: <$3B Mkt Cap early in 2024, min ${min_mkt_cap_2024:.2f}B)"
            else:
                diag = "✅ Caught cleanly in Table 2"

        audit_rows.append(
            {
                "ticker": sym,
                "wave": item["wave"],
                "company_name": item["company_name"],
                "data_available": True,
                "yr_2024_return_pct": yr_ret,
                "max_2024_gain_pct": max_gain_from_jan,
                "min_mkt_cap_b": min_mkt_cap_2024,
                "max_mkt_cap_b": max_mkt_cap_2024,
                "days_in_2024": len(ohlc_2024),
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
                "caught_by_screener": bool(l4_act_days > 0 or l3_days > 0),
                "caught_in_l4": bool(l4_act_days > 0),
                "bottleneck_diagnosis": diag,
            }
        )

    return audit_rows


def _select_ranked_table2_candidates(df_scored: pd.DataFrame, allowed_statuses: List[str]) -> pd.DataFrame:
    """
    Filters `df_scored` to Table 2 qualified setups matching `allowed_statuses` and sorts
    by the exact Table 2 priority (`_status_rank`, `vcp_score` desc, `composite_score` desc).
    """
    if df_scored is None or df_scored.empty:
        return pd.DataFrame()

    mask = (
        df_scored.get("qualified_all", False)
        & df_scored.get("l2_qualified", False)
        & df_scored.get("l3_qualified", False)
        & df_scored.get("l5_qualified", True)
        & df_scored["action_status"].isin(allowed_statuses)
    )
    sub = df_scored[mask].copy()
    if sub.empty:
        return sub

    status_rank_map = {"TRIGGERED": 0, "BUY_ZONE": 1, "ON_DECK": 2, "EXTENDED": 3, "BUILDING": 4}
    sub["_status_rank"] = sub["action_status"].map(status_rank_map).fillna(5)
    sub = sub.sort_values(
        by=["_status_rank", "composite_score", "vcp_score", "rs_percentile"],
        ascending=[True, False, False, False],
    ).reset_index(drop=True)
    return sub


def run_walk_forward_simulation(
    panel: Dict[str, Any],
    daily_screens: Dict[str, Dict[str, Any]],
    entry_mode: str = "ON_DECK_STOP",      # "ON_DECK_STOP" (Mode A) or "TRIGGERED_NEXT_OPEN" (Mode B)
    exit_model: str = "JLAW_HYBRID",       # "FIXED_2_5R" (Model 1) or "JLAW_HYBRID" (Model 2)
    initial_equity: float = 100_000.0,
    risk_pct_per_trade: float = 1.0,
    max_alloc_pct: float = 25.0,
    max_stop_loss_pct: float = 7.0,
    reward_risk_ratio: float = 2.5,
    max_chase_above_pivot_pct: float = 5.0,
    slippage_bps: float = 10.0,            # 0.10% slippage per leg
    require_spy_above_ema21: bool = False, # Optional Senior Trader Market Regime gate
    allow_buy_zone_in_mode_b: bool = False,
) -> Dict[str, Any]:
    """
    Simulates chronological daily trading across all 252 trading days of 2024.
    Signals generated at Day `T-1` close are eligible for execution on Day `T`!
    """
    all_dates = panel["all_eval_dates"]
    dates_2024 = panel["trading_dates_2024"]
    ohlc_by_sym = panel["ohlc_by_sym"]
    sp500_lookup = panel["sp500_lookup"]

    slip = slippage_bps / 10_000.0
    cash = float(initial_equity)
    open_positions: Dict[str, OpenPosition] = {}
    closed_trades: List[Dict[str, Any]] = []
    equity_curve: List[Dict[str, Any]] = []

    # Map each 2024 date to its immediate prior trading date (`T-1`)
    idx_map = {d: i for i, d in enumerate(all_dates)}

    for d_str in dates_2024:
        d_idx = idx_map.get(d_str, 0)
        prev_date = all_dates[d_idx - 1] if d_idx > 0 else ""

        # ------------------------------------------------------------------
        # Step 1: Process Exits on Existing Open Positions (Intraday Stops/Targets, then EOD EMA21)
        # ------------------------------------------------------------------
        to_close: List[Tuple[str, float, str]] = []
        for sym, pos in list(open_positions.items()):
            sym_bars = ohlc_by_sym.get(sym)
            if sym_bars is None or d_str not in sym_bars.index:
                continue
            bar = sym_bars.loc[d_str]
            b_open = float(bar["open"])
            b_high = float(bar["high"])
            b_low = float(bar["low"])
            b_close = float(bar["close"])
            b_ema21 = float(bar["ema_21"])

            if exit_model == "FIXED_2_5R":
                # Conservative rule: check stop-loss first unless open gapped straight to target
                if b_open >= pos.target_price:
                    exit_px = round(b_open * (1.0 - slip), 4)
                    to_close.append((sym, exit_px, "Target +2.5R (Gap)"))
                elif b_low <= pos.current_stop:
                    raw_stop_fill = min(b_open, pos.current_stop)
                    exit_px = round(raw_stop_fill * (1.0 - slip), 4)
                    to_close.append((sym, exit_px, "Stop-Loss (-1R)"))
                elif b_high >= pos.target_price:
                    exit_px = round(pos.target_price * (1.0 - slip), 4)
                    to_close.append((sym, exit_px, "Target (+2.5R)"))

            else:  # JLAW_HYBRID: 50% @ +2.5R (move stop to BE), 50% trailed on Close < EMA21
                if not pos.partial_taken:
                    # 1. Check hard initial stop (-1R)
                    if b_low <= pos.current_stop and b_open < pos.target_price:
                        raw_stop_fill = min(b_open, pos.current_stop)
                        exit_px = round(raw_stop_fill * (1.0 - slip), 4)
                        to_close.append((sym, exit_px, "Stop-Loss (-1R)"))
                        continue

                    # 2. Check +2.5R partial profit target (sell 50%, raise stop to Breakeven)
                    if b_high >= pos.target_price:
                        raw_t_fill = max(b_open, pos.target_price)
                        part_px = round(raw_t_fill * (1.0 - slip), 4)
                        sell_sh = max(1, pos.remaining_shares // 2)
                        if sell_sh >= pos.remaining_shares:
                            to_close.append((sym, part_px, "Target (+2.5R)"))
                            continue

                        cash += sell_sh * part_px
                        pos.realized_pnl += sell_sh * (part_px - pos.entry_price)
                        pos.remaining_shares -= sell_sh
                        pos.partial_taken = True
                        pos.partial_exit_date = d_str
                        pos.partial_exit_price = part_px
                        pos.partial_shares_sold = sell_sh
                        pos.current_stop = pos.entry_price  # Move stop to Breakeven!

                        # Check EOD 21 EMA trail on remaining 50%
                        if b_close < b_ema21:
                            exit_px = round(b_close * (1.0 - slip), 4)
                            to_close.append((sym, exit_px, "Partial +2.5R then EMA21 Close"))
                        continue

                else:
                    # Already took +2.5R partial on a prior day:
                    # 1. Intraday Breakeven Stop protection
                    if b_low <= pos.current_stop:
                        raw_be_fill = min(b_open, pos.current_stop)
                        exit_px = round(raw_be_fill * (1.0 - slip), 4)
                        to_close.append((sym, exit_px, "Runner Breakeven Stop (after +2.5R)"))
                        continue
                    # 2. JLaw EOD Closing Basis Trail: Close < 21 EMA
                    if b_close < b_ema21:
                        exit_px = round(b_close * (1.0 - slip), 4)
                        to_close.append((sym, exit_px, "JLaw EMA21 Trail Exit"))
                        continue

        for sym, exit_px, reason in to_close:
            pos = open_positions.pop(sym)
            cash += pos.remaining_shares * exit_px
            final_leg_pnl = pos.remaining_shares * (exit_px - pos.entry_price)
            total_pnl = pos.realized_pnl + final_leg_pnl
            total_risk_dollars = pos.initial_shares * pos.risk_per_share
            r_mult = total_pnl / total_risk_dollars if total_risk_dollars > 0 else 0.0
            cost_basis = pos.initial_shares * pos.entry_price
            ret_pct = (total_pnl / cost_basis) * 100.0 if cost_basis > 0 else 0.0

            closed_trades.append(
                {
                    "ticker": pos.ticker,
                    "company_name": pos.company_name,
                    "sector": pos.sector,
                    "industry": pos.industry,
                    "signal_date": pos.signal_date,
                    "entry_date": pos.entry_date,
                    "exit_date": d_str,
                    "entry_price": round(pos.entry_price, 2),
                    "exit_price": round(exit_px, 2),
                    "partial_exit_price": round(pos.partial_exit_price, 2) if pos.partial_taken else None,
                    "initial_shares": pos.initial_shares,
                    "pnl_dollars": round(total_pnl, 2),
                    "return_pct": round(ret_pct, 2),
                    "r_multiple": round(r_mult, 2),
                    "exit_reason": reason,
                    "vcp_score": pos.vcp_score,
                    "composite_score": pos.composite_score,
                    "rs_percentile": pos.rs_percentile,
                    "status": "CLOSED",
                }
            )

        # ------------------------------------------------------------------
        # Step 2: Evaluate New Entries on Day `T` from Day `T-1` Watchlist Signals
        # ------------------------------------------------------------------
        prev_pack = daily_screens.get(prev_date) if prev_date else None
        prev_sp500 = sp500_lookup.get(prev_date, {}) if prev_date else {}
        regime_ok = True
        if require_spy_above_ema21 and prev_sp500:
            regime_ok = bool(prev_sp500.get("above_ema21", True))

        if prev_pack is not None and regime_ok:
            # Mark-to-market current equity before sizing new trades
            mtm_val = 0.0
            for sym_open, p_open in open_positions.items():
                sb = ohlc_by_sym.get(sym_open)
                px_now = float(sb.loc[d_str, "open"]) if (sb is not None and d_str in sb.index) else p_open.entry_price
                mtm_val += p_open.remaining_shares * px_now
            current_equity = cash + mtm_val

            max_positions = max(1, int(round(100.0 / max_alloc_pct)) + 1)  # e.g. up to 5 concurrent if <25% alloc

            if entry_mode == "ON_DECK_STOP":
                cands = _select_ranked_table2_candidates(prev_pack["df_scored"], ["ON_DECK"])
            else:
                statuses = ["TRIGGERED", "BUY_ZONE"] if allow_buy_zone_in_mode_b else ["TRIGGERED"]
                cands = _select_ranked_table2_candidates(prev_pack["df_scored"], statuses)

            for _, crow in cands.iterrows():
                if len(open_positions) >= max_positions:
                    break
                sym = str(crow["ticker"])
                if sym in open_positions:
                    continue

                sym_bars = ohlc_by_sym.get(sym)
                if sym_bars is None or d_str not in sym_bars.index:
                    continue
                bar = sym_bars.loc[d_str]
                b_open = float(bar["open"])
                b_high = float(bar["high"])
                b_low = float(bar["low"])
                b_close = float(bar["close"])

                pivot_px = float(crow["pivot_price"])
                max_chase_px = pivot_px * (1.0 + max_chase_above_pivot_pct / 100.0)
                setup_stop = float(crow["stop_loss_price"])

                raw_entry = 0.0
                if entry_mode == "ON_DECK_STOP":
                    # Must reach pivot_px intraday, and Open must not gap > +5% above pivot
                    if b_open > max_chase_px or b_high < pivot_px:
                        continue
                    raw_entry = max(b_open, pivot_px)
                else:
                    # Mode B: Next-Day Open after EOD Triggered, provided Open is within max buy zone
                    if b_open > max_chase_px or b_open <= setup_stop:
                        continue
                    raw_entry = b_open

                entry_px = round(raw_entry * (1.0 + slip), 4)

                # Re-anchor Stop & 1R to actual fill price (preserving Layer 5 clamp rules)
                max_risk_stop = entry_px * (1.0 - max_stop_loss_pct / 100.0)
                stop_px = round(max(max_risk_stop, min(entry_px * 0.98, setup_stop)), 2)
                risk_ps = max(0.05, round(entry_px - stop_px, 4))
                if (risk_ps / entry_px) * 100.0 > max_stop_loss_pct + 0.25:
                    continue

                max_dollar_risk = current_equity * (risk_pct_per_trade / 100.0)
                max_cap_alloc = min(cash, current_equity * (max_alloc_pct / 100.0))
                if max_cap_alloc < entry_px:
                    continue

                sh_risk = int(max_dollar_risk / risk_ps)
                sh_cap = int(max_cap_alloc / entry_px)
                shares = min(sh_risk, sh_cap)
                if shares < 1:
                    continue

                cost = shares * entry_px
                if cost > cash:
                    continue

                target_px = round(entry_px + reward_risk_ratio * risk_ps, 2)
                cash -= cost

                new_pos = OpenPosition(
                    ticker=sym,
                    company_name=str(crow.get("company_name", sym)),
                    sector=str(crow.get("sector", "General")),
                    industry=str(crow.get("industry", "General")),
                    signal_date=prev_date,
                    entry_date=d_str,
                    entry_price=entry_px,
                    initial_shares=shares,
                    remaining_shares=shares,
                    initial_stop=stop_px,
                    current_stop=stop_px,
                    risk_per_share=risk_ps,
                    target_price=target_px,
                    vcp_score=float(crow.get("vcp_score", 0.0)),
                    composite_score=float(crow.get("composite_score", 0.0)),
                    rs_percentile=int(crow.get("rs_percentile", 0)),
                )

                # Conservative same-day reversal check: if Day T low breached stop_px after entry
                if b_low <= stop_px and b_close <= stop_px:
                    exit_px = round(stop_px * (1.0 - slip), 4)
                    cash += shares * exit_px
                    pnl = shares * (exit_px - entry_px)
                    closed_trades.append(
                        {
                            "ticker": sym,
                            "company_name": new_pos.company_name,
                            "sector": new_pos.sector,
                            "industry": new_pos.industry,
                            "signal_date": prev_date,
                            "entry_date": d_str,
                            "exit_date": d_str,
                            "entry_price": round(entry_px, 2),
                            "exit_price": round(exit_px, 2),
                            "partial_exit_price": None,
                            "initial_shares": shares,
                            "pnl_dollars": round(pnl, 2),
                            "return_pct": round(((exit_px / entry_px) - 1.0) * 100.0, 2),
                            "r_multiple": round(pnl / (shares * risk_ps), 2),
                            "exit_reason": "Same-Day Intraday Reversal Stop",
                            "vcp_score": new_pos.vcp_score,
                            "composite_score": new_pos.composite_score,
                            "rs_percentile": new_pos.rs_percentile,
                            "status": "CLOSED",
                        }
                    )
                else:
                    open_positions[sym] = new_pos

        # ------------------------------------------------------------------
        # Step 3: EOD Portfolio Mark-to-Market Valuation (USIC Accounting Basis)
        # ------------------------------------------------------------------
        pos_mkt_value = 0.0
        for sym_open, p_open in open_positions.items():
            sb = ohlc_by_sym.get(sym_open)
            if sb is not None and d_str in sb.index:
                px_eod = float(sb.loc[d_str, "close"])
            else:
                px_eod = p_open.entry_price
            pos_mkt_value += p_open.remaining_shares * px_eod

        total_eq = cash + pos_mkt_value
        sp_close = float(sp500_lookup.get(d_str, {}).get("last_close", 0.0))
        equity_curve.append(
            {
                "date": d_str,
                "equity": round(total_eq, 2),
                "cash": round(cash, 2),
                "invested_pct": round((pos_mkt_value / total_eq) * 100.0, 1) if total_eq > 0 else 0.0,
                "open_positions": len(open_positions),
                "sp500_close": sp_close,
            }
        )

    # Mark-to-market open positions at 2024-12-31 year-end close for complete trade ledger
    last_date = dates_2024[-1] if dates_2024 else "2024-12-31"
    all_trades = list(closed_trades)
    for sym_open, pos in open_positions.items():
        sb = ohlc_by_sym.get(sym_open)
        px_end = float(sb.loc[last_date, "close"]) if (sb is not None and last_date in sb.index) else pos.entry_price
        unreal_pnl = pos.remaining_shares * (px_end - pos.entry_price)
        total_pnl = pos.realized_pnl + unreal_pnl
        total_risk = pos.initial_shares * pos.risk_per_share
        r_mult = total_pnl / total_risk if total_risk > 0 else 0.0
        cost_basis = pos.initial_shares * pos.entry_price
        ret_pct = (total_pnl / cost_basis) * 100.0 if cost_basis > 0 else 0.0

        all_trades.append(
            {
                "ticker": pos.ticker,
                "company_name": pos.company_name,
                "sector": pos.sector,
                "industry": pos.industry,
                "signal_date": pos.signal_date,
                "entry_date": pos.entry_date,
                "exit_date": f"{last_date} (MTM)",
                "entry_price": round(pos.entry_price, 2),
                "exit_price": round(px_end, 2),
                "partial_exit_price": round(pos.partial_exit_price, 2) if pos.partial_taken else None,
                "initial_shares": pos.initial_shares,
                "pnl_dollars": round(total_pnl, 2),
                "return_pct": round(ret_pct, 2),
                "r_multiple": round(r_mult, 2),
                "exit_reason": "Held into Year-End (Mark-to-Market)",
                "vcp_score": pos.vcp_score,
                "composite_score": pos.composite_score,
                "rs_percentile": pos.rs_percentile,
                "status": "OPEN_MTM",
            }
        )

    metrics = _compute_performance_metrics(equity_curve, all_trades, initial_equity)
    return {
        "metrics": metrics,
        "equity_curve": equity_curve,
        "trades": all_trades,
    }


def _compute_performance_metrics(
    equity_curve: List[Dict[str, Any]],
    trades: List[Dict[str, Any]],
    initial_equity: float,
) -> Dict[str, Any]:
    if not equity_curve:
        return {"total_return_pct": 0.0, "total_trades": 0}

    eq_df = pd.DataFrame(equity_curve)
    final_eq = float(eq_df["equity"].iloc[-1])
    total_ret_pct = round(((final_eq / initial_equity) - 1.0) * 100.0, 2)

    # Benchmark S&P 500 2024 return
    sp_start = float(eq_df["sp500_close"].iloc[0])
    sp_end = float(eq_df["sp500_close"].iloc[-1])
    sp_ret_pct = round(((sp_end / sp_start) - 1.0) * 100.0, 2) if sp_start > 0 else 0.0

    # Max Drawdown & Sharpe / Sortino
    eq_series = eq_df["equity"].astype(float)
    rolling_peak = eq_series.cummax()
    dd_series = ((eq_series - rolling_peak) / rolling_peak) * 100.0
    max_dd_pct = round(float(dd_series.min()), 2)

    daily_rets = eq_series.pct_change().dropna()
    sharpe = 0.0
    if len(daily_rets) > 5 and float(daily_rets.std()) > 0:
        sharpe = round(float((daily_rets.mean() / daily_rets.std()) * np.sqrt(252)), 2)

    # Monthly returns breakdown (2024-01 .. 2024-12)
    eq_df["ym"] = eq_df["date"].str.slice(0, 7)
    monthly_returns: Dict[str, float] = {}
    prev_m_eq = initial_equity
    for ym, grp in eq_df.groupby("ym", sort=True):
        end_m_eq = float(grp["equity"].iloc[-1])
        monthly_returns[str(ym)] = round(((end_m_eq / prev_m_eq) - 1.0) * 100.0, 2)
        prev_m_eq = end_m_eq

    # Trade-level statistics
    n_trades = len(trades)
    if n_trades == 0:
        return {
            "initial_equity": initial_equity,
            "final_equity": final_eq,
            "total_return_pct": total_ret_pct,
            "sp500_return_pct": sp_ret_pct,
            "max_drawdown_pct": max_dd_pct,
            "sharpe_ratio": sharpe,
            "avg_invested_pct": round(float(eq_df["invested_pct"].mean()), 1),
            "total_trades": 0,
            "win_rate_pct": 0.0,
            "avg_win_pct": 0.0,
            "avg_loss_pct": 0.0,
            "avg_win_r": 0.0,
            "avg_loss_r": 0.0,
            "expectancy_r": 0.0,
            "profit_factor": 0.0,
            "monthly_returns": monthly_returns,
        }

    t_df = pd.DataFrame(trades)
    wins = t_df[t_df["pnl_dollars"] > 0]
    losses = t_df[t_df["pnl_dollars"] <= 0]

    win_rate = round((len(wins) / n_trades) * 100.0, 1)
    avg_win_pct = round(float(wins["return_pct"].mean()), 2) if not wins.empty else 0.0
    avg_loss_pct = round(float(losses["return_pct"].mean()), 2) if not losses.empty else 0.0
    avg_win_r = round(float(wins["r_multiple"].mean()), 2) if not wins.empty else 0.0
    avg_loss_r = round(float(losses["r_multiple"].mean()), 2) if not losses.empty else 0.0
    expectancy_r = round(float(t_df["r_multiple"].mean()), 2)

    gross_profit = float(wins["pnl_dollars"].sum()) if not wins.empty else 0.0
    gross_loss = abs(float(losses["pnl_dollars"].sum())) if not losses.empty else 0.0
    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)

    return {
        "initial_equity": initial_equity,
        "final_equity": round(final_eq, 2),
        "total_return_pct": total_ret_pct,
        "sp500_return_pct": sp_ret_pct,
        "max_drawdown_pct": max_dd_pct,
        "sharpe_ratio": sharpe,
        "avg_invested_pct": round(float(eq_df["invested_pct"].mean()), 1),
        "total_trades": n_trades,
        "winners_count": int(len(wins)),
        "losers_count": int(len(losses)),
        "win_rate_pct": win_rate,
        "avg_win_pct": avg_win_pct,
        "avg_loss_pct": avg_loss_pct,
        "avg_win_r": avg_win_r,
        "avg_loss_r": avg_loss_r,
        "expectancy_r": expectancy_r,
        "profit_factor": profit_factor,
        "max_single_trade_pct": round(float(t_df["return_pct"].max()), 2),
        "max_single_trade_r": round(float(t_df["r_multiple"].max()), 2),
        "worst_single_trade_pct": round(float(t_df["return_pct"].min()), 2),
        "monthly_returns": monthly_returns,
    }
