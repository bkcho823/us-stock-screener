"""
Yahoo Finance Historical Market Provider — Fetches S&P 500 Benchmark returns
and 252-day split-adjusted daily Close series for SMA150, SMA200 lag slopes, and 9M RS.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Any, Optional, Callable

import numpy as np
import pandas as pd
import requests
import yfinance as yf

from src.infrastructure.market_repo import save_sp500_benchmark
from src.providers.tradingview_scanner import TV_SCAN_URL


def fetch_sp500_benchmark() -> Dict[str, Any]:
    """
    Fetches S&P 500 (^GSPC, fallback SPY) daily history and calculates:
    - 1-Month return (21 trading days)
    - 6-Month return (126 trading days)
    Cross-checks with TradingView scanner if yfinance is rate-limited, then persists via market_repo.
    """
    result = {
        "symbol": "^GSPC",
        "last_close": 0.0,
        "ema_21": 0.0,
        "sma_50": 0.0,
        "ema_21_rising": True,
        "dist_to_ema21_pct": 0.0,
        "market_regime": "GREEN_POWER_TREND",
        "regime_badge": "🟢 POWER TREND (SPY > Rising 21EMA · Full Exposure)",
        "recommended_exposure_str": "1.0%–2.0% Risk · Up to 100%+ Invested",
        "perf_1m_pct": 0.0,
        "perf_3m_pct": 0.0,
        "perf_6m_pct": 0.0,
        "perf_12m_pct": 0.0,
        "as_of_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "updated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    }

    for ticker_sym in ["^GSPC", "SPY"]:
        try:
            hist = yf.Ticker(ticker_sym).history(period="1y", interval="1d", auto_adjust=True)
            if hist is not None and len(hist) >= 130:
                closes = hist["Close"].dropna()
                curr = float(closes.iloc[-1])
                c_1m = float(closes.iloc[-22]) if len(closes) >= 22 else float(closes.iloc[0])
                c_3m = float(closes.iloc[-64]) if len(closes) >= 64 else float(closes.iloc[0])
                c_6m = float(closes.iloc[-127]) if len(closes) >= 127 else float(closes.iloc[0])
                c_12m = float(closes.iloc[0])

                ema21_ser = closes.ewm(span=21, adjust=False).mean()
                sma50_ser = closes.rolling(50, min_periods=20).mean()
                ema21_val = float(ema21_ser.iloc[-1])
                ema21_5d_ago = float(ema21_ser.iloc[-6]) if len(ema21_ser) >= 6 else ema21_val
                sma50_val = float(sma50_ser.iloc[-1]) if not np.isnan(sma50_ser.iloc[-1]) else ema21_val
                ema21_rising = ema21_val >= ema21_5d_ago

                result["symbol"] = ticker_sym
                result["last_close"] = round(curr, 2)
                result["ema_21"] = round(ema21_val, 2)
                result["sma_50"] = round(sma50_val, 2)
                result["ema_21_rising"] = bool(ema21_rising)
                result["dist_to_ema21_pct"] = round(((curr - ema21_val) / ema21_val) * 100.0, 2) if ema21_val > 0 else 0.0
                result["perf_1m_pct"] = round(((curr / c_1m) - 1.0) * 100.0, 2)
                result["perf_3m_pct"] = round(((curr / c_3m) - 1.0) * 100.0, 2)
                result["perf_6m_pct"] = round(((curr / c_6m) - 1.0) * 100.0, 2)
                result["perf_12m_pct"] = round(((curr / c_12m) - 1.0) * 100.0, 2)
                result["as_of_date"] = str(closes.index[-1].date())
                break
        except Exception:
            continue

    if result["last_close"] == 0.0:
        try:
            payload = {
                "symbols": {"tickers": ["AMEX:SPY"], "query": {"types": []}},
                "columns": ["close", "Perf.1M", "Perf.3M", "Perf.6M", "Perf.Y", "EMA20", "SMA50"],
            }
            resp = requests.post(TV_SCAN_URL, json=payload, timeout=15)
            resp.raise_for_status()
            rows = resp.json().get("data", [])
            if rows:
                d = rows[0]["d"]
                curr = float(d[0] or 0.0)
                ema20_v = float(d[5] or curr) if len(d) > 5 else curr
                sma50_v = float(d[6] or curr) if len(d) > 6 else curr
                result["symbol"] = "SPY"
                result["last_close"] = round(curr, 2)
                result["ema_21"] = round(ema20_v, 2)
                result["sma_50"] = round(sma50_v, 2)
                result["ema_21_rising"] = bool(curr >= ema20_v)
                result["dist_to_ema21_pct"] = round(((curr - ema20_v) / ema20_v) * 100.0, 2) if ema20_v > 0 else 0.0
                result["perf_1m_pct"] = round(float(d[1] or 0.0), 2)
                result["perf_3m_pct"] = round(float(d[2] or 0.0), 2)
                result["perf_6m_pct"] = round(float(d[3] or 0.0), 2)
                result["perf_12m_pct"] = round(float(d[4] or 0.0), 2)
        except Exception:
            pass

    # Classify JLaw Market Regime Traffic Light
    c_val = float(result["last_close"])
    e21_val = float(result["ema_21"])
    s50_val = float(result["sma_50"])
    is_rising = bool(result["ema_21_rising"])

    if c_val > 0 and e21_val > 0:
        if c_val >= e21_val and (e21_val >= s50_val or is_rising):
            result["market_regime"] = "GREEN_POWER_TREND"
            result["regime_badge"] = f"🟢 POWER TREND ({result['symbol']} > 21EMA · {result['dist_to_ema21_pct']:+.1f}%)"
            result["recommended_exposure_str"] = "Full Offense (1.0%–2.0% Risk · 75%–100%+ Invested)"
        elif c_val >= s50_val or c_val >= e21_val * 0.99:
            result["market_regime"] = "YELLOW_PULLBACK"
            result["regime_badge"] = f"🟡 PULLBACK / DIGESTION ({result['symbol']} testing 21EMA/50SMA)"
            result["recommended_exposure_str"] = "Selective Pilots (0.5% Risk · 25%–50% Invested)"
        else:
            result["market_regime"] = "RED_DEFENSIVE"
            result["regime_badge"] = f"🔴 DEFENSIVE / CHOP ({result['symbol']} < 21EMA & 50SMA)"
            result["recommended_exposure_str"] = "Capital Preservation (0.25% Pilot or Cash)"

    save_sp500_benchmark(result)
    return result


def enrich_with_yfinance_history(
    df: pd.DataFrame,
    max_symbols_for_yf: int = 1800,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> pd.DataFrame:
    """
    Downloads 260+ trading days of split-adjusted daily Close prices via yfinance in fast batches
    to compute exact indicators not directly exposed in a single TradingView column:
    - SMA 150 (exact 150-day simple moving average)
    - SMA 200 lookback values (5, 10, 15, 20, 30, 40, 60 trading days ago) for Condition #3
    - 9-Month Performance (perf_9m, 189 trading days) for the 3/6/9/12M weighted RS score
    Falls back gracefully to approximated values from SMA100/SMA200 if a ticker fails in yfinance.
    """
    if df.empty:
        return df

    df = df.copy()
    df["sma_150"] = ((df["sma_100"] + df["sma_200"]) / 2.0).round(2)
    df["perf_9m"] = ((df["perf_6m"] + df["perf_12m"]) / 2.0).round(2)
    
    # Layer 3/4 VCP, Pre-Breakout Pivot & EMA Defaults (fallback if yfinance is limited)
    if "ema_21" not in df.columns:
        df["ema_21"] = df.get("ema_20", df.get("sma_20", df["close"])).round(2)
    if "ema_50" not in df.columns:
        df["ema_50"] = df.get("sma_50", df["close"]).round(2)
    if "adr_20_pct" not in df.columns:
        df["adr_20_pct"] = df.get("volatility_d", pd.Series(3.0, index=df.index)).fillna(3.0).clip(0.5, 25.0).round(2)
    if "last_contraction_pct" not in df.columns:
        df["last_contraction_pct"] = (df.get("volatility_d", 3.0) * 1.8).clip(2.0, 15.0).round(2)
    if "vol_dryup_pct" not in df.columns:
        # P0 Fix: Estimate pre-breakout 9D coil volume excluding today's breakout bar (vol_1d)
        v10 = df.get("vol_10d", df.get("vol_1d", 1)).fillna(1)
        v1 = df.get("vol_1d", v10).fillna(1)
        v60 = df.get("vol_60d", v10).replace(0, 1).fillna(1)
        prior_9d_vol = ((10.0 * v10 - v1) / 9.0).clip(lower=v10 * 0.25)
        df["vol_dryup_pct"] = ((prior_9d_vol / v60) * 100.0).clip(10.0, 200.0).round(1)
    if "coil_pivot_high" not in df.columns:
        df["coil_pivot_high"] = df.get("high_52w", df["close"]).round(2)
    if "prior_high_52w" not in df.columns:
        df["prior_high_52w"] = df.get("high_52w", df["close"]).round(2)
    if "bars_count" not in df.columns:
        df["bars_count"] = np.where(df["sma_200"].notna() & (df["sma_200"] > 0), 252, 120)

    for lb in [5, 10, 15, 20, 30, 40, 60]:
        df[f"sma_200_lag_{lb}"] = (
            df["sma_200"] - ((df["close"] - df["sma_200"]) / 200.0) * lb
        ).round(2)

    candidates = df.head(max_symbols_for_yf)["ticker"].tolist()
    batch_size = 150
    total_batches = max(1, (len(candidates) + batch_size - 1) // batch_size)

    sma150_map: Dict[str, float] = {}
    sma200_now_map: Dict[str, float] = {}
    ema21_map: Dict[str, float] = {}
    ema50_map: Dict[str, float] = {}
    contraction_map: Dict[str, float] = {}
    vol_dryup_map: Dict[str, float] = {}
    coil_pivot_map: Dict[str, float] = {}
    prior_52w_map: Dict[str, float] = {}
    adr20_map: Dict[str, float] = {}
    bars_count_map: Dict[str, int] = {}
    perf9m_map: Dict[str, float] = {}
    lag_maps: Dict[int, Dict[str, float]] = {lb: {} for lb in [5, 10, 15, 20, 30, 40, 60]}

    for b_idx in range(0, len(candidates), batch_size):
        batch_num = (b_idx // batch_size) + 1
        batch_syms = candidates[b_idx : b_idx + batch_size]
        if progress_callback:
            progress_callback(
                min(0.90, 0.15 + 0.75 * (batch_num / total_batches)),
                f"Computing 252-day SMAs, Pre-Breakout Pivots & ADR% (Batch {batch_num}/{total_batches}, {len(batch_syms)} stocks)...",
            )
        try:
            yf_syms = [s.replace(".", "-") for s in batch_syms]
            raw = yf.download(
                tickers=yf_syms,
                period="2y",
                interval="1d",
                auto_adjust=True,
                progress=False,
                threads=True,
                group_by="ticker",
            )
            if raw is None or raw.empty:
                continue

            for orig_sym, yf_sym in zip(batch_syms, yf_syms):
                try:
                    if len(yf_syms) == 1:
                        sub_df = raw.dropna(subset=["Close"])
                    else:
                        if yf_sym not in raw.columns.get_level_values(0):
                            continue
                        sub_df = raw[yf_sym].dropna(subset=["Close"])

                    closes = sub_df["Close"]
                    highs = sub_df["High"] if "High" in sub_df.columns else closes
                    lows = sub_df["Low"] if "Low" in sub_df.columns else closes
                    vols = sub_df["Volume"] if "Volume" in sub_df.columns else pd.Series(dtype=float)

                    n = len(closes)
                    if n < 50:
                        continue
                    bars_count_map[orig_sym] = int(n)

                    # Exact 21EMA and 50EMA for JLaw structure
                    ema21_series = closes.ewm(span=21, adjust=False).mean()
                    ema50_series = closes.ewm(span=50, adjust=False).mean()
                    ema21_map[orig_sym] = round(float(ema21_series.iloc[-1]), 2)
                    ema50_map[orig_sym] = round(float(ema50_series.iloc[-1]), 2)

                    # P1: 20-Day Average Daily Range % (ADR20)
                    if n >= 20:
                        daily_rng = ((highs.iloc[-20:] - lows.iloc[-20:]) / lows.iloc[-20:].replace(0, np.nan)) * 100.0
                        adr_val = float(daily_rng.mean())
                        if not np.isnan(adr_val) and adr_val > 0:
                            adr20_map[orig_sym] = round(float(np.clip(adr_val, 0.5, 25.0)), 2)

                    # P0 Fix: Pre-breakout 10-day contraction & resistance pivot over [T-10 : T-1] (excluding today T)
                    if n >= 11:
                        pre_highs = highs.iloc[-11:-1]
                        pre_lows = lows.iloc[-11:-1]
                        pre_closes = closes.iloc[-11:-1]
                        coil_h = float(pre_highs.max())
                        coil_l = float(pre_lows.min())
                        # Use close-to-close / high-low blend matching pre-breakout VCP tightness
                        c_high = float(pre_closes.max())
                        c_low = float(pre_closes.min())
                        if c_high > 0:
                            contraction_map[orig_sym] = round(((c_high - c_low) / c_high) * 100.0, 2)
                        if coil_h > 0:
                            coil_pivot_map[orig_sym] = round(coil_h, 2)

                        prior_252_h = float(highs.iloc[-min(n, 253):-1].max())
                        if prior_252_h > 0:
                            prior_52w_map[orig_sym] = round(prior_252_h, 2)

                    # P0 Fix: Pre-breakout 5-day coil volume dry-up over [T-5 : T-1] vs 60D avg
                    if len(vols) >= 25:
                        coil_v5 = float(vols.iloc[-6:-1].mean())
                        avg_v60 = float(vols.iloc[-min(len(vols), 61):-1].mean())
                        if avg_v60 > 0 and coil_v5 > 0:
                            vol_dryup_map[orig_sym] = round(float(np.clip((coil_v5 / avg_v60) * 100.0, 10.0, 200.0)), 1)

                    if n >= 150:
                        sma150_val = float(closes.iloc[-150:].mean())
                        sma150_map[orig_sym] = round(sma150_val, 2)

                    if n >= 190:
                        c_curr = float(closes.iloc[-1])
                        c_9m = float(closes.iloc[-190])
                        if c_9m > 0:
                            perf9m_map[orig_sym] = round(((c_curr / c_9m) - 1.0) * 100.0, 2)

                    if n >= 200:
                        sma200_series = closes.rolling(200).mean()
                        sma200_now = float(sma200_series.iloc[-1])
                        if not np.isnan(sma200_now):
                            sma200_now_map[orig_sym] = round(sma200_now, 2)
                        for lb in [5, 10, 15, 20, 30, 40, 60]:
                            if n >= 200 + lb:
                                val_lb = float(sma200_series.iloc[-1 - lb])
                                if not np.isnan(val_lb):
                                    lag_maps[lb][orig_sym] = round(val_lb, 2)
                except Exception:
                    continue
        except Exception:
            continue

    if sma150_map:
        df["sma_150"] = df["ticker"].map(sma150_map).fillna(df["sma_150"])
    if sma200_now_map:
        df["sma_200"] = df["ticker"].map(sma200_now_map).fillna(df["sma_200"])
    if ema21_map:
        df["ema_21"] = df["ticker"].map(ema21_map).fillna(df["ema_21"])
    if ema50_map:
        df["ema_50"] = df["ticker"].map(ema50_map).fillna(df["ema_50"])
    if adr20_map:
        df["adr_20_pct"] = df["ticker"].map(adr20_map).fillna(df["adr_20_pct"])
    if contraction_map:
        df["last_contraction_pct"] = df["ticker"].map(contraction_map).fillna(df["last_contraction_pct"])
    if vol_dryup_map:
        df["vol_dryup_pct"] = df["ticker"].map(vol_dryup_map).fillna(df["vol_dryup_pct"])
    if coil_pivot_map:
        df["coil_pivot_high"] = df["ticker"].map(coil_pivot_map).fillna(df["coil_pivot_high"])
    if prior_52w_map:
        df["prior_high_52w"] = df["ticker"].map(prior_52w_map).fillna(df["prior_high_52w"])
    if bars_count_map:
        df["bars_count"] = df["ticker"].map(bars_count_map).fillna(df["bars_count"]).astype(int)
    if perf9m_map:
        df["perf_9m"] = df["ticker"].map(perf9m_map).fillna(df["perf_9m"])
    for lb in [5, 10, 15, 20, 30, 40, 60]:
        if lag_maps[lb]:
            df[f"sma_200_lag_{lb}"] = df["ticker"].map(lag_maps[lb]).fillna(df[f"sma_200_lag_{lb}"])

    # Pre-compute Raw Weighted Relative Strength Score (Minervini / IBD style):
    # 40% * 3M Return + 20% * 6M Return + 20% * 9M Return + 20% * 12M Return
    df["rs_raw_score"] = (
        0.40 * df["perf_3m"].fillna(0.0)
        + 0.20 * df["perf_6m"].fillna(0.0)
        + 0.20 * df["perf_9m"].fillna(0.0)
        + 0.20 * df["perf_12m"].fillna(0.0)
    ).round(2)

    df["updated_at_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return df
