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

                result["symbol"] = ticker_sym
                result["last_close"] = round(curr, 2)
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
                "columns": ["close", "Perf.1M", "Perf.3M", "Perf.6M", "Perf.Y"],
            }
            resp = requests.post(TV_SCAN_URL, json=payload, timeout=15)
            resp.raise_for_status()
            rows = resp.json().get("data", [])
            if rows:
                d = rows[0]["d"]
                result["symbol"] = "SPY"
                result["last_close"] = round(float(d[0] or 0.0), 2)
                result["perf_1m_pct"] = round(float(d[1] or 0.0), 2)
                result["perf_3m_pct"] = round(float(d[2] or 0.0), 2)
                result["perf_6m_pct"] = round(float(d[3] or 0.0), 2)
                result["perf_12m_pct"] = round(float(d[4] or 0.0), 2)
        except Exception:
            pass

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
    for lb in [5, 10, 15, 20, 30, 40, 60]:
        df[f"sma_200_lag_{lb}"] = (
            df["sma_200"] - ((df["close"] - df["sma_200"]) / 200.0) * lb
        ).round(2)

    candidates = df.head(max_symbols_for_yf)["ticker"].tolist()
    batch_size = 150
    total_batches = max(1, (len(candidates) + batch_size - 1) // batch_size)

    sma150_map: Dict[str, float] = {}
    sma200_now_map: Dict[str, float] = {}
    perf9m_map: Dict[str, float] = {}
    lag_maps: Dict[int, Dict[str, float]] = {lb: {} for lb in [5, 10, 15, 20, 30, 40, 60]}

    for b_idx in range(0, len(candidates), batch_size):
        batch_num = (b_idx // batch_size) + 1
        batch_syms = candidates[b_idx : b_idx + batch_size]
        if progress_callback:
            progress_callback(
                min(0.90, 0.15 + 0.75 * (batch_num / total_batches)),
                f"Computing 252-day SMAs & RS history (Batch {batch_num}/{total_batches}, {len(batch_syms)} stocks)...",
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
                        closes = raw["Close"].dropna()
                    else:
                        if yf_sym not in raw.columns.get_level_values(0):
                            continue
                        closes = raw[yf_sym]["Close"].dropna()

                    n = len(closes)
                    if n < 155:
                        continue

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
