"""
Layer 2 — Momentum & Industry Strength Scoring & Ranking Engine.
Applies the 5-Member Expert Panel consensus methodology:
1. Computes Industry & Sector rotation momentum across the Layer 0 candidate pool:
   Group Score = 0.40 * 1M + 0.35 * 3M + 0.25 * 6M (with <3 stock small-sample Bayesian shrinkage to Sector)
2. Combines 75% Industry RS Percentile + 25% Sector RS Percentile to get Group Tailwind RS (1-99)
3. Evaluates In-Group Leadership Rank (#1 = 100, #2 = 90, #3 = 80, tapering down)
4. Computes Layer 2 Composite Score (0-100) = w_stock * Stock_RS + w_group * Group_RS + w_lead * Leader_Score
5. Evaluates Layer 2 Gate: Industry in Top X% (default: Top 40%, Group RS >= 60) OR Lone Wolf Override (Stock RS >= 90)
"""

from __future__ import annotations

from typing import Dict, Any, Tuple, List
import numpy as np
import pandas as pd


def _calc_leader_score(rank: int) -> float:
    """Assigns leadership score (0-100) based on rank within industry."""
    if rank == 1:
        return 100.0
    if rank == 2:
        return 90.0
    if rank == 3:
        return 80.0
    if rank == 4:
        return 65.0
    return max(30.0, 60.0 - (rank - 5) * 8.0)


def compute_group_momentum_rankings(df_l0: pd.DataFrame) -> Tuple[Dict[str, float], Dict[str, float], List[Dict[str, Any]]]:
    """
    Computes Industry and Sector rotation percentiles (1-99) using the entire Layer 0 liquid pool.
    Group Return = 0.40 * 1M + 0.35 * 3M + 0.25 * 6M
    Small groups (< 3 stocks) are Bayesian-shrunk towards their parent sector average.
    """
    if df_l0 is None or df_l0.empty:
        return {}, {}, []

    df = df_l0.copy()

    # Gracefully ensure industry and sector columns exist
    if "industry" not in df.columns:
        df["industry"] = "General"
    else:
        df["industry"] = df["industry"].fillna("General")

    if "sector" not in df.columns:
        df["sector"] = "General"
    else:
        df["sector"] = df["sector"].fillna("General")

    # Calculate raw momentum score per stock
    p1 = df["perf_1m"].fillna(0.0) if "perf_1m" in df.columns else pd.Series(0.0, index=df.index)
    p3 = df["perf_3m"].fillna(0.0) if "perf_3m" in df.columns else pd.Series(0.0, index=df.index)
    p6 = df["perf_6m"].fillna(0.0) if "perf_6m" in df.columns else pd.Series(0.0, index=df.index)
    df["stock_rot_raw"] = 0.40 * p1 + 0.35 * p3 + 0.25 * p6

    # 1. Sector level benchmark
    sector_stats = df.groupby("sector", observed=False)["stock_rot_raw"].agg(["mean", "count"]).reset_index()
    sector_stats = sector_stats.dropna(subset=["sector"])
    if len(sector_stats) > 1:
        s_rank = sector_stats["mean"].rank(pct=True, ascending=True)
        sector_stats["sector_rs_pct"] = np.clip(np.ceil(s_rank * 99.0), 1, 99).astype(int)
    else:
        sector_stats["sector_rs_pct"] = 99
    sector_map = dict(zip(sector_stats["sector"], sector_stats["sector_rs_pct"]))
    sector_mean_map = dict(zip(sector_stats["sector"], sector_stats["mean"]))

    # 2. Industry level benchmark
    ind_grouped = df.groupby(["industry", "sector"], observed=False).agg(
        ind_mean=("stock_rot_raw", "mean"),
        stock_count=("ticker", "count"),
        above_sma50_count=("close", lambda s: int((s > df.loc[s.index, "sma_50"]).sum()) if "sma_50" in df.columns else len(s)),
    ).reset_index()
    ind_grouped = ind_grouped.dropna(subset=["industry"])

    # Bayesian shrinkage for small industries (< 3 stocks)
    def _shrink_ind_mean(row: pd.Series) -> float:
        cnt = row["stock_count"]
        imean = row["ind_mean"]
        smean = sector_mean_map.get(row["sector"], imean)
        if cnt >= 3:
            return float(imean)
        if cnt == 2:
            return float(0.65 * imean + 0.35 * smean)
        return float(0.40 * imean + 0.60 * smean)

    ind_grouped["adj_ind_mean"] = ind_grouped.apply(_shrink_ind_mean, axis=1)

    if len(ind_grouped) > 1:
        ind_rank = ind_grouped["adj_ind_mean"].rank(pct=True, ascending=True)
        ind_grouped["industry_rs_pct"] = np.clip(np.ceil(ind_rank * 99.0), 1, 99).astype(int)
        ind_grouped["industry_rank_num"] = ind_grouped["adj_ind_mean"].rank(ascending=False).astype(int)
    else:
        ind_grouped["industry_rs_pct"] = 99
        ind_grouped["industry_rank_num"] = 1

    ind_rs_map = dict(zip(ind_grouped["industry"], ind_grouped["industry_rs_pct"]))
    ind_rank_map = dict(zip(ind_grouped["industry"], ind_grouped["industry_rank_num"]))
    ind_count_map = dict(zip(ind_grouped["industry"], ind_grouped["stock_count"]))

    # Prepare top leaderboard list for UI popover
    leaderboard = []
    ind_sorted = ind_grouped.sort_values(by="adj_ind_mean", ascending=False).reset_index(drop=True)
    for _, r in ind_sorted.iterrows():
        stk_cnt = int(r["stock_count"])
        above_50 = int(r["above_sma50_count"])
        breadth_pct = round((above_50 / max(1, stk_cnt)) * 100.0, 1)
        leaderboard.append({
            "industry": str(r["industry"]),
            "sector": str(r["sector"]),
            "rank": int(r["industry_rank_num"]),
            "total_industries": len(ind_sorted),
            "rs_pct": int(r["industry_rs_pct"]),
            "stock_count": stk_cnt,
            "breadth_pct": breadth_pct,
            "mean_perf": round(float(r["adj_ind_mean"]), 2),
        })

    return ind_rs_map, sector_map, leaderboard


def evaluate_layer2_momentum_and_sector(
    df_l1_scored: pd.DataFrame,
    df_l0_pool: pd.DataFrame,
    layer2_cfg: Dict[str, Any],
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Evaluates Layer 2 Momentum, Industry Strength & In-Group Leadership.
    Applies weights, computes `composite_score`, and flags `l2_pass` via Top Group Gate / Lone Wolf Override.
    """
    if df_l1_scored is None or df_l1_scored.empty:
        return pd.DataFrame(), {
            "l2_enabled": bool(layer2_cfg.get("l2_enabled", True)),
            "l2_qualified_count": 0,
            "lone_wolf_count": 0,
            "group_gate_pass_count": 0,
            "leaderboard": [],
        }

    df = df_l1_scored.copy()

    # Gracefully ensure industry and sector columns exist
    if "industry" not in df.columns:
        df["industry"] = "General"
    else:
        df["industry"] = df["industry"].fillna("General")

    if "sector" not in df.columns:
        df["sector"] = "General"
    else:
        df["sector"] = df["sector"].fillna("General")

    # 1. Compute market-wide Industry & Sector rankings from the Layer 0 pool
    ind_rs_map, sector_rs_map, leaderboard = compute_group_momentum_rankings(df_l0_pool)

    # 2. Map industry and sector percentiles onto qualified stocks
    df["industry_rs_pct"] = df["industry"].map(ind_rs_map).fillna(50).astype(int)
    df["sector_rs_pct"] = df["sector"].map(sector_rs_map).fillna(50).astype(int)

    # Combined Group RS = 75% Industry RS + 25% Sector RS (O'Neil 37% : 12% ratio)
    df["group_rs_percentile"] = np.clip(
        np.round(0.75 * df["industry_rs_pct"] + 0.25 * df["sector_rs_pct"]), 1, 99
    ).astype(int)

    # 3. Calculate Intra-Industry Rank & Leadership Score
    # Rank stocks within their industry based on stock rs_raw_score (or rs_percentile)
    df["rank_in_group"] = df.groupby("industry")["rs_percentile"].rank(ascending=False, method="min").astype(int)
    df["group_total_candidates"] = df.groupby("industry")["ticker"].transform("count").astype(int)
    df["leader_score"] = df["rank_in_group"].apply(_calc_leader_score)

    # 4. Compute Layer 2 Composite Score (0 - 100) + Q3 CAN SLIM Fundamental Quality Integration
    w_stock = float(layer2_cfg.get("weight_stock_rs", 0.50))
    w_group = float(layer2_cfg.get("weight_group_rs", 0.35))
    w_lead = float(layer2_cfg.get("weight_lead_rank", 0.15))

    has_fundamentals = ("eps_growth_yoy" in df.columns) or ("rev_growth_yoy" in df.columns)
    eps_col = pd.to_numeric(df.get("eps_growth_yoy", pd.Series(np.nan, index=df.index)), errors="coerce")
    rev_col = pd.to_numeric(df.get("rev_growth_yoy", pd.Series(np.nan, index=df.index)), errors="coerce")
    roe_col = pd.to_numeric(df.get("roe_pct", pd.Series(np.nan, index=df.index)), errors="coerce")

    min_eps_g = float(layer2_cfg.get("min_eps_growth_yoy", 20.0))
    min_rev_g = float(layer2_cfg.get("min_rev_growth_yoy", 20.0))
    fund_gate_on = bool(layer2_cfg.get("fund_gate_enabled", False))

    # Build CAN SLIM Fundamental Badge & Tie-Breaker Boost (+0 to +3.0 pts when real fundamental data exists)
    fund_badges = []
    fund_boosts = []
    fund_passes = []
    for idx_r, row_r in df.iterrows():
        eg = eps_col.loc[idx_r]
        rg = rev_col.loc[idx_r]
        roe_v = roe_col.loc[idx_r]
        rs_v = int(row_r.get("rs_percentile", 50))
        if pd.isna(eg) and pd.isna(rg):
            fund_badges.append("— (Price/RS Mode)")
            fund_boosts.append(0.0)
            fund_passes.append(True)
        else:
            eg_v = float(eg) if pd.notna(eg) else 0.0
            rg_v = float(rg) if pd.notna(rg) else 0.0
            roe_f = float(roe_v) if pd.notna(roe_v) else 0.0
            is_c_pass = (eg_v >= min_eps_g) or (rg_v >= min_rev_g)
            is_a_plus = (eg_v >= 25.0 and rg_v >= 20.0) or (eg_v >= 40.0) or (rg_v >= 35.0)
            if is_a_plus:
                fund_badges.append(f"💎 CAN SLIM A+ (EPS {eg_v:+.0f}% · Rev {rg_v:+.0f}%)")
                fund_boosts.append(2.5 if roe_f >= 15.0 else 2.0)
            elif is_c_pass:
                fund_badges.append(f"✅ Growth (EPS {eg_v:+.0f}% · Rev {rg_v:+.0f}%)")
                fund_boosts.append(1.0)
            elif rs_v >= 90:
                fund_badges.append(f"🔄 Turnaround RS {rs_v} (EPS {eg_v:+.0f}%)")
                fund_boosts.append(0.0)
            else:
                fund_badges.append(f"⚠️ Slow Growth (EPS {eg_v:+.0f}% · Rev {rg_v:+.0f}%)")
                fund_boosts.append(-1.5)
            # Minervini SEPA rule: pass if EPS >= min OR Sales >= min OR RS >= 90 Turnaround Leader
            fund_passes.append(bool(is_c_pass or rs_v >= 90))

    df["fund_badge"] = fund_badges
    df["fund_pass"] = fund_passes
    df["fund_boost"] = fund_boosts

    raw_comp = (
        w_stock * df["rs_percentile"]
        + w_group * df["group_rs_percentile"]
        + w_lead * df["leader_score"]
        + (df["fund_boost"] if has_fundamentals else 0.0)
    )
    df["composite_score"] = np.clip(raw_comp, 0.0, 100.0).round(1)

    # 5. Evaluate Layer 2 Gate: Industry in Top X% OR Lone Wolf Exemption (plus optional CAN SLIM Gate)
    l2_enabled = bool(layer2_cfg.get("l2_enabled", True))
    gate_enabled = bool(layer2_cfg.get("group_gate_enabled", True))
    top_pct = float(layer2_cfg.get("top_group_pct", 40.0))  # e.g., Top 40% -> group_rs_percentile >= 60
    min_group_rs_required = max(1, int(100.0 - top_pct))

    lone_wolf_enabled = bool(layer2_cfg.get("lone_wolf_enabled", True))
    lone_wolf_min_rs = int(layer2_cfg.get("lone_wolf_min_rs", 90))

    df["pass_group_gate"] = df["group_rs_percentile"] >= min_group_rs_required
    df["is_lone_wolf"] = lone_wolf_enabled & (df["rs_percentile"] >= lone_wolf_min_rs) & (~df["pass_group_gate"])

    if not l2_enabled or not gate_enabled:
        df["l2_qualified"] = df["fund_pass"] if (l2_enabled and fund_gate_on) else True
        df["l2_badge"] = "⚪ L2 Gate: OFF"
    else:
        base_l2_q = df["pass_group_gate"] | df["is_lone_wolf"]
        df["l2_qualified"] = (base_l2_q & df["fund_pass"]) if fund_gate_on else base_l2_q
        
        def _make_l2_badge(row: pd.Series) -> str:
            if row["pass_group_gate"]:
                return f"✅ Strong Ind (RS {row['group_rs_percentile']})"
            if row["is_lone_wolf"]:
                return f"🦅 Lone Wolf (RS {row['rs_percentile']})"
            return f"❌ Lagging Ind (RS {row['group_rs_percentile']})"

        df["l2_badge"] = df.apply(_make_l2_badge, axis=1)

    # Build human-readable industry leader rank string (e.g. "#1/8 (RS 98)")
    df["industry_rank_str"] = (
        "#" + df["rank_in_group"].astype(str)
        + "/" + df["group_total_candidates"].astype(str)
        + " (" + df["industry"].fillna("Unknown") + ")"
    )

    # Sort final watchlist by:
    # 1. L1 Qualified (True first)
    # 2. L2 Qualified (True first)
    # 3. Composite Score (descending)
    # 4. Stock RS Percentile (descending)
    df = df.sort_values(
        by=["qualified_all", "l2_qualified", "composite_score", "rs_percentile"],
        ascending=[False, False, False, False],
    ).reset_index(drop=True)

    summary_meta = {
        "l2_enabled": l2_enabled,
        "group_gate_enabled": gate_enabled,
        "top_group_pct": top_pct,
        "min_group_rs_required": min_group_rs_required,
        "l2_qualified_count": int((df["qualified_all"] & df["l2_qualified"]).sum()),
        "lone_wolf_count": int((df["qualified_all"] & df["is_lone_wolf"]).sum()),
        "group_gate_pass_count": int((df["qualified_all"] & df["pass_group_gate"]).sum()),
        "leaderboard": leaderboard,
    }

    return df, summary_meta
