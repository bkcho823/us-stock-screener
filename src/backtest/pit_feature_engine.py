"""
Point-in-Time (PIT) Vectorized Feature Engine (`src/backtest/pit_feature_engine.py`).
Transforms raw daily OHLCV histories (2022-11-01 -> 2025-01-10) into exact daily universe
snapshots (`df_universe` + `sp500_bm`) for every trading day of 2024 with ZERO look-ahead bias.

Supports three feature modes for UAT & Senior Trader benchmarking:
  1. `pit_clean` (Default Unbiased VCP Benchmark):
     - `high_52w`, `low_52w`, `last_contraction_pct`, and `vol_dryup_pct` are computed from bars
       strictly prior to Day T (`<= T-1`) so a legitimate Day T high-volume breakout (`>= 120%` vol)
       above prior resistance is not self-disqualified by its own breakout bar.
  2. `asis_live_snapshot` (UAT Defect Reproduction):
     - Reproduces the current live EOD snapshot calculation where Day T's own `High`, `Close`, and
       `vol_1d` are included inside `high_52w`, `last_contraction_pct`, and `vol_dryup_pct`.
  3. `pit_local_pivot` (Senior Trader Pro Enhancement):
     - Uses `pit_clean` coil metrics PLUS supplies the true 20-day local consolidation high (`swing_high_20d`)
       when a Stage 2 stock is consolidating >8% below its 52-week high.
"""

from __future__ import annotations

from typing import Dict, Any, List, Tuple

import numpy as np
import pandas as pd


def build_sp500_pit_Lookup(sp500_df: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
    """
    Precomputes point-in-time S&P 500 benchmark metrics and regime moving averages for every trading date.
    """
    df = sp500_df.sort_index().copy()
    closes = df["Close"]

    sma20 = closes.rolling(20).mean()
    ema21 = closes.ewm(span=21, adjust=False).mean()
    sma50 = closes.rolling(50).mean()
    sma200 = closes.rolling(200).mean()

    perf_1m = ((closes / closes.shift(21)) - 1.0) * 100.0
    perf_3m = ((closes / closes.shift(63)) - 1.0) * 100.0
    perf_6m = ((closes / closes.shift(126)) - 1.0) * 100.0
    perf_12m = ((closes / closes.shift(252)) - 1.0) * 100.0

    lookup: Dict[str, Dict[str, Any]] = {}
    for dt, row in df.iterrows():
        d_str = pd.Timestamp(dt).strftime("%Y-%m-%d")
        c_val = float(row["Close"])
        e21_val = float(ema21.loc[dt]) if not np.isnan(ema21.loc[dt]) else c_val
        s50_val = float(sma50.loc[dt]) if not np.isnan(sma50.loc[dt]) else c_val
        s200_val = float(sma200.loc[dt]) if not np.isnan(sma200.loc[dt]) else c_val

        lookup[d_str] = {
            "symbol": "^GSPC",
            "as_of_date": d_str,
            "last_close": round(c_val, 2),
            "open": round(float(row["Open"]), 2),
            "high": round(float(row["High"]), 2),
            "low": round(float(row["Low"]), 2),
            "ema_21": round(e21_val, 2),
            "sma_20": round(float(sma20.loc[dt]) if not np.isnan(sma20.loc[dt]) else c_val, 2),
            "sma_50": round(s50_val, 2),
            "sma_200": round(s200_val, 2),
            "above_ema21": bool(c_val >= e21_val),
            "above_sma50": bool(c_val >= s50_val),
            "above_sma200": bool(c_val >= s200_val),
            "perf_1m_pct": round(float(perf_1m.loc[dt]) if not np.isnan(perf_1m.loc[dt]) else 0.0, 2),
            "perf_3m_pct": round(float(perf_3m.loc[dt]) if not np.isnan(perf_3m.loc[dt]) else 0.0, 2),
            "perf_6m_pct": round(float(perf_6m.loc[dt]) if not np.isnan(perf_6m.loc[dt]) else 0.0, 2),
            "perf_12m_pct": round(float(perf_12m.loc[dt]) if not np.isnan(perf_12m.loc[dt]) else 0.0, 2),
        }
    return lookup


def build_pit_panel(
    metadata_df: pd.DataFrame,
    ohlcv_map: Dict[str, pd.DataFrame],
    sp500_df: pd.DataFrame,
    eval_start: str = "2023-12-26",
    eval_end: str = "2024-12-31",
) -> Dict[str, Any]:
    """
    Precomputes all daily technical features across all stocks and slices them by trading date
    over `[eval_start, eval_end]` for instant O(1) day lookup during walk-forward backtesting.
    """
    sp500_lookup = build_sp500_pit_Lookup(sp500_df)
    meta_by_sym = metadata_df.set_index("ticker").to_dict(orient="index")

    start_ts = pd.Timestamp(eval_start)
    end_ts = pd.Timestamp(eval_end)

    per_stock_frames: List[pd.DataFrame] = []
    ohlc_fast_lookup: Dict[str, pd.DataFrame] = {}

    for sym, raw_df in ohlcv_map.items():
        if sym not in meta_by_sym or raw_df is None or len(raw_df) < 35:
            continue

        df = raw_df.sort_index().copy()
        df = df[~df.index.duplicated(keep="last")]
        meta = meta_by_sym[sym]

        o = df["Open"].astype(float)
        h = df["High"].astype(float)
        l = df["Low"].astype(float)
        c = df["Close"].astype(float)
        v = df["Volume"].astype(float).fillna(0.0)

        # Unbiased prior-bar volume averages (excludes Day T surge from baseline denominator)
        v_prev = v.shift(1)
        vol_10d = v_prev.rolling(10, min_periods=5).mean().fillna(v)
        vol_30d = v_prev.rolling(30, min_periods=10).mean().fillna(vol_10d)
        vol_60d = v_prev.rolling(60, min_periods=20).mean().fillna(vol_30d)
        vol_90d = v_prev.rolling(90, min_periods=30).mean().fillna(vol_60d)

        shares_est = float(meta.get("shares_est", 0.0) or 0.0)
        mkt_cap_b = (shares_est * c) / 1e9 if shares_est > 0 else pd.Series(5.0, index=df.index)
        dollar_vol_m = (c * v) / 1e6

        sma_10 = c.rolling(10).mean()
        sma_20 = c.rolling(20).mean()
        sma_50 = c.rolling(50).mean()
        sma_100 = c.rolling(100).mean()
        sma_150 = c.rolling(150).mean()
        sma_200 = c.rolling(200).mean()

        ema_20 = c.ewm(span=20, adjust=False).mean()
        ema_21 = c.ewm(span=21, adjust=False).mean()
        ema_50 = c.ewm(span=50, adjust=False).mean()

        first_c = float(c.iloc[0]) if len(c) > 0 and c.iloc[0] > 0 else 1.0
        perf_1m = ((c / c.shift(21)) - 1.0) * 100.0
        perf_3m = ((c / c.shift(63)) - 1.0) * 100.0
        perf_6m = ((c / c.shift(126)) - 1.0) * 100.0
        # Match TradingView since-inception fallback once stock has >=150 bars
        c_shift_189 = c.shift(189).fillna(first_c)
        c_shift_252 = c.shift(252).fillna(first_c)
        perf_9m = ((c / c_shift_189) - 1.0) * 100.0
        perf_12m = ((c / c_shift_252) - 1.0) * 100.0

        rs_raw_score = (
            0.40 * perf_3m.fillna(0.0)
            + 0.20 * perf_6m.fillna(0.0)
            + 0.20 * perf_9m.fillna(0.0)
            + 0.20 * perf_12m.fillna(0.0)
        )

        # --- Clean Point-in-Time (Pre-Day-T) VCP & Pivot Features ---
        h_prev = h.shift(1)
        l_prev = l.shift(1)
        c_prev = c.shift(1)

        high_52w_pit = h_prev.rolling(252, min_periods=50).max().fillna(h)
        low_52w_pit = l_prev.rolling(252, min_periods=50).min().fillna(l)
        swing_high_20d_pit = h_prev.rolling(20, min_periods=8).max().fillna(high_52w_pit)

        coil_hi_pit = c_prev.rolling(10, min_periods=5).max()
        coil_lo_pit = c_prev.rolling(10, min_periods=5).min()
        contraction_pit = (((coil_hi_pit - coil_lo_pit) / coil_hi_pit.replace(0, np.nan)) * 100.0).clip(1.0, 40.0).fillna(10.0)

        vol_coil_med_pit = v_prev.rolling(5, min_periods=3).median()
        vol_dryup_pit = ((vol_coil_med_pit / vol_60d.replace(0, np.nan)) * 100.0).clip(10.0, 200.0).fillna(80.0)

        # --- As-Is Live Snapshot Features (includes Day T bar) ---
        high_52w_asis = h.rolling(252, min_periods=50).max()
        low_52w_asis = l.rolling(252, min_periods=50).min()
        coil_hi_asis = c.rolling(10, min_periods=5).max()
        coil_lo_asis = c.rolling(10, min_periods=5).min()
        contraction_asis = (((coil_hi_asis - coil_lo_asis) / coil_hi_asis.replace(0, np.nan)) * 100.0).clip(1.0, 40.0).fillna(10.0)
        vol_dryup_asis = ((v / vol_60d.replace(0, np.nan)) * 100.0).clip(10.0, 200.0).fillna(80.0)

        bar_age = np.arange(1, len(df) + 1)

        feat = pd.DataFrame(
            {
                "date_str": df.index.strftime("%Y-%m-%d"),
                "ticker": sym,
                "company_name": str(meta.get("company_name", sym)),
                "exchange": str(meta.get("exchange", "NASDAQ")),
                "sector": str(meta.get("sector", "General") or "General"),
                "industry": str(meta.get("industry", "General") or "General"),
                "is_etf_or_fund": bool(meta.get("is_etf_or_fund", False)),
                "is_adr": bool(meta.get("is_adr", False)),
                "bar_age": bar_age,
                "open": o.round(2),
                "high": h.round(2),
                "low": l.round(2),
                "close": c.round(2),
                "vol_1d": v.round(0),
                "vol_10d": vol_10d.round(0),
                "vol_30d": vol_30d.round(0),
                "vol_60d": vol_60d.round(0),
                "vol_90d": vol_90d.round(0),
                "dollar_vol_m": dollar_vol_m.round(2),
                "market_cap_b": mkt_cap_b.round(3),
                "sma_10": sma_10.round(2),
                "sma_20": sma_20.round(2),
                "sma_50": sma_50.round(2),
                "sma_100": sma_100.round(2),
                "sma_150": sma_150.round(2),
                "sma_200": sma_200.round(2),
                "sma_200_lag_5": sma_200.shift(5).round(2),
                "sma_200_lag_10": sma_200.shift(10).round(2),
                "sma_200_lag_15": sma_200.shift(15).round(2),
                "sma_200_lag_20": sma_200.shift(20).round(2),
                "sma_200_lag_30": sma_200.shift(30).round(2),
                "sma_200_lag_40": sma_200.shift(40).round(2),
                "sma_200_lag_60": sma_200.shift(60).round(2),
                "ema_20": ema_20.round(2),
                "ema_21": ema_21.round(2),
                "ema_50": ema_50.round(2),
                "perf_1m": perf_1m.round(2),
                "perf_3m": perf_3m.round(2),
                "perf_6m": perf_6m.round(2),
                "perf_9m": perf_9m.round(2),
                "perf_12m": perf_12m.round(2),
                "rs_raw_score": rs_raw_score.round(2),
                "high_52w_pit": high_52w_pit.round(2),
                "low_52w_pit": low_52w_pit.round(2),
                "swing_high_20d_pit": swing_high_20d_pit.round(2),
                "contraction_pit": contraction_pit.round(2),
                "vol_dryup_pit": vol_dryup_pit.round(1),
                "high_52w_asis": high_52w_asis.round(2),
                "low_52w_asis": low_52w_asis.round(2),
                "contraction_asis": contraction_asis.round(2),
                "vol_dryup_asis": vol_dryup_asis.round(1),
            },
            index=df.index,
        )

        sliced = feat.loc[(feat.index >= start_ts) & (feat.index <= end_ts)].copy()
        if not sliced.empty:
            per_stock_frames.append(sliced)
            ohlc_fast_lookup[sym] = sliced.set_index("date_str")[
                ["open", "high", "low", "close", "vol_1d", "ema_21", "ema_50", "sma_50", "bar_age"]
            ]

    if not per_stock_frames:
        return {
            "trading_dates_2024": [],
            "all_eval_dates": [],
            "by_date": {},
            "ohlc_by_sym": {},
            "sp500_lookup": sp500_lookup,
        }

    full_panel = pd.concat(per_stock_frames, ignore_index=True)
    by_date: Dict[str, pd.DataFrame] = {
        str(dt): grp.reset_index(drop=True) for dt, grp in full_panel.groupby("date_str", sort=True)
    }

    all_eval_dates = sorted(d for d in by_date.keys() if d in sp500_lookup)
    trading_dates_2024 = [d for d in all_eval_dates if "2024-01-01" <= d <= "2024-12-31"]

    return {
        "trading_dates_2024": trading_dates_2024,
        "all_eval_dates": all_eval_dates,
        "by_date": by_date,
        "ohlc_by_sym": ohlc_fast_lookup,
        "sp500_lookup": sp500_lookup,
    }


def extract_day_universe(
    panel: Dict[str, Any],
    date_str: str,
    feature_mode: str = "pit_clean",
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Materializes the exact `df_universe` and `sp500_bm` inputs expected by
    `run_screening_pipeline(...)` for a single historical trading date.
    """
    base_df = panel["by_date"].get(date_str)
    sp500_bm = panel["sp500_lookup"].get(date_str, {})
    if base_df is None or base_df.empty:
        return pd.DataFrame(), sp500_bm

    df = base_df.copy()
    if feature_mode == "asis_live_snapshot":
        df["high_52w"] = df["high_52w_asis"]
        df["low_52w"] = df["low_52w_asis"]
        df["last_contraction_pct"] = df["contraction_asis"]
        df["vol_dryup_pct"] = df["vol_dryup_asis"]
    else:
        df["high_52w"] = df["high_52w_pit"]
        df["low_52w"] = df["low_52w_pit"]
        df["last_contraction_pct"] = df["contraction_pit"]
        df["vol_dryup_pct"] = df["vol_dryup_pit"]

    return df, sp500_bm
