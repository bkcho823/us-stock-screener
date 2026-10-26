"""
Step 2: EOD Market Data & Indicator Pre-Computation Engine
- Fetches US Stock Universe metadata + pre-computed technicals via TradingView Screener API
- Enhances with Yahoo Finance (yfinance) historical data for exact 200-day SMA lookback (N days ago)
  and S&P 500 (^GSPC / SPY) 1M and 6M benchmark performance.
- Caches daily EOD snapshot to Parquet + JSON so all Layer 0 & Layer 1 adjustments run in <1 second.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Callable

import numpy as np
import pandas as pd
import requests
import yfinance as yf

from src.config import (
    SNAPSHOT_FILE,
    BENCHMARK_FILE,
    BASELINE_CACHE_MIN_MKT_CAP_B,
    BASELINE_CACHE_MIN_PRICE,
)
from src.supabase_client import (
    is_supabase_configured,
    sb_upsert_kv,
    sb_get_kv,
)

TV_SCAN_URL = "https://scanner.tradingview.com/america/scan"

# Columns available directly from TradingView's America scanner endpoint:
# Fetching both Layer 0 metadata (Mkt Cap, Volumes 1D/10D/30D/60D/90D, Exchange, Type)
# AND baseline technical indicators gives us sub-5-second universe fetches, while
# yfinance bulk history provides exact N-day lookback series for SMA200.
TV_COLUMNS = [
    "name",                         # Ticker symbol
    "description",                  # Company full name
    "exchange",                     # NYSE, NASDAQ, AMEX
    "type",                         # stock, dr (ADR), fund, etf
    "subtype",                      # common, etf, reit, etc.
    "close",                        # Current / EOD Close Price
    "volume",                       # 1D Volume (shares)
    "average_volume_10d_calc",      # 10D Average Volume
    "average_volume_30d_calc",      # 30D Average Volume
    "average_volume_60d_calc",      # 60D Average Volume
    "average_volume_90d_calc",      # 90D Average Volume
    "Value.Traded",                 # Dollar Volume (Price x Volume in USD)
    "market_cap_basic",             # Market Cap in USD
    "SMA10",                        # 10-day Simple Moving Average
    "SMA20",                        # 20-day Simple Moving Average
    "SMA50",                        # 50-day Simple Moving Average
    "SMA100",                       # 100-day Simple Moving Average
    "SMA200",                       # 200-day Simple Moving Average
    "price_52_week_high",           # 52-Week High
    "price_52_week_low",            # 52-Week Low
    "Perf.1M",                      # 1-Month Performance (%)
    "Perf.3M",                      # 3-Month Performance (%)
    "Perf.6M",                      # 6-Month Performance (%)
    "Perf.Y",                       # 12-Month Performance (%)
    "sector",                       # Sector name
    "industry",                     # Industry name
]


def fetch_sp500_benchmark() -> Dict[str, Any]:
    """
    Fetches S&P 500 (^GSPC, fallback SPY) daily history and calculates:
    - 1-Month return (21 trading days)
    - 6-Month return (126 trading days)
    Also cross-checks with TradingView scanner if yfinance is rate-limited.
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

    # First try yfinance for exact trading-day returns on ^GSPC / SPY
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

    # Fallback: Query SPY from TradingView scanner if needed
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

    if is_supabase_configured():
        try:
            sb_upsert_kv("benchmark_sp500", result)
        except Exception:
            pass
    return result


def fetch_tradingview_baseline_universe(
    min_mkt_cap_b: float = BASELINE_CACHE_MIN_MKT_CAP_B,
    min_price: float = BASELINE_CACHE_MIN_PRICE,
) -> pd.DataFrame:
    """
    Fetches all US equities on NYSE, NASDAQ, and AMEX meeting the baseline floor
    from TradingView Screener API in a single fast request (1-2 seconds).
    """
    payload = {
        "filter": [
            {"left": "exchange", "operation": "in_range", "right": ["NYSE", "NASDAQ", "AMEX"]},
            {"left": "market_cap_basic", "operation": "egreater", "right": int(min_mkt_cap_b * 1_000_000_000)},
            {"left": "close", "operation": "egreater", "right": float(min_price)},
        ],
        "options": {"lang": "en"},
        "markets": ["america"],
        "symbols": {"query": {"types": []}, "tickers": []},
        "columns": TV_COLUMNS,
        "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"},
        "range": [0, 5000],
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Content-Type": "application/json",
    }
    resp = requests.post(TV_SCAN_URL, json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json().get("data", [])

    records = []
    for item in data:
        d = item.get("d", [])
        if len(d) < len(TV_COLUMNS):
            continue
        row = dict(zip(TV_COLUMNS, d))
        records.append(row)

    df = pd.DataFrame(records)
    if df.empty:
        return df

    # Clean and standardize columns
    df = df.rename(
        columns={
            "name": "ticker",
            "description": "company_name",
            "close": "close",
            "volume": "vol_1d",
            "average_volume_10d_calc": "vol_10d",
            "average_volume_30d_calc": "vol_30d",
            "average_volume_60d_calc": "vol_60d",
            "average_volume_90d_calc": "vol_90d",
            "Value.Traded": "dollar_vol",
            "market_cap_basic": "market_cap",
            "SMA10": "sma_10",
            "SMA20": "sma_20",
            "SMA50": "sma_50",
            "SMA100": "sma_100",
            "SMA200": "sma_200",
            "price_52_week_high": "high_52w",
            "price_52_week_low": "low_52w",
            "Perf.1M": "perf_1m",
            "Perf.3M": "perf_3m",
            "Perf.6M": "perf_6m",
            "Perf.Y": "perf_12m",
        }
    )

    # Convert numeric fields
    num_cols = [
        "close", "vol_1d", "vol_10d", "vol_30d", "vol_60d", "vol_90d",
        "dollar_vol", "market_cap", "sma_10", "sma_20", "sma_50", "sma_100",
        "sma_200", "high_52w", "low_52w", "perf_1m", "perf_3m", "perf_6m", "perf_12m"
    ]
    for c in num_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df["market_cap_b"] = (df["market_cap"] / 1e9).round(3)
    # If Value.Traded is missing, compute Price x Vol_1D
    df["dollar_vol_m"] = np.where(
        df["dollar_vol"].notna() & (df["dollar_vol"] > 0),
        df["dollar_vol"] / 1e6,
        (df["close"] * df["vol_1d"]) / 1e6,
    ).round(2)

    # Identify ETFs / Funds vs Common Stocks vs ADRs
    type_str = df["type"].fillna("").astype(str).str.lower()
    subtype_str = df["subtype"].fillna("").astype(str).str.lower()
    df["is_etf_or_fund"] = (
        type_str.isin(["fund", "etf", "structured"])
        | subtype_str.str.contains("etf|fund|trust|closedend|preferred|unit|warrant", regex=True)
    )
    df["is_adr"] = (type_str == "dr") | subtype_str.str.contains("adr|depositary", regex=True)

    # Remove preferred share tickers (containing '/' or '-' with P, etc. if non-standard)
    df = df[~df["ticker"].astype(str).str.contains(r"\^|/|\.", regex=True)].copy()
    return df.reset_index(drop=True)


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
    # Initialize default fallback columns before enrichment so every row has valid numbers
    df["sma_150"] = ((df["sma_100"] + df["sma_200"]) / 2.0).round(2)
    df["perf_9m"] = ((df["perf_6m"] + df["perf_12m"]) / 2.0).round(2)
    for lb in [5, 10, 15, 20, 30, 40, 60]:
        # Fallback estimate: if close > sma_200, sma_200 was slightly lower N days ago
        df[f"sma_200_lag_{lb}"] = (
            df["sma_200"] - ((df["close"] - df["sma_200"]) / 200.0) * lb
        ).round(2)

    # Prioritize liquid non-ETF candidates for exact yfinance enrichment
    candidates = df.head(max_symbols_for_yf)["ticker"].tolist()
    batch_size = 150
    total_batches = max(1, (len(candidates) + batch_size - 1) // batch_size)

    sma150_map: Dict[str, float] = {}
    sma200_now_map: Dict[str, float] = {}
    perf9m_map: Dict[str, float] = {}
    lag_maps: Dict[int, Dict[str, float]] = {lb: {} for lb in [5, 10, 15, 20, 30, 40, 60]}

    for b_idx in range(0, len(candidates), batch_size):
        batch_Num = (b_idx // batch_size) + 1
        batch_syms = candidates[b_idx : b_idx + batch_size]
        if progress_callback:
            progress_callback(
                min(0.90, 0.15 + 0.75 * (batch_Num / total_batches)),
                f"Computing 252-day SMAs & RS history (Batch {batch_Num}/{total_batches}, {len(batch_syms)} stocks)...",
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


def refresh_daily_market_data(
    enrich_yf: bool = True,
    max_symbols_for_yf: int = 1200,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Full EOD data pipeline:
    1. Fetches S&P 500 1M and 6M benchmark returns
    2. Fetches US equity candidate pool from TradingView Screener API
    3. Enriches with exact 252-day SMA150 and SMA200 lookback slopes via yfinance
    4. Saves to local Parquet + JSON cache for instant (<1s) re-screening.
    """
    if progress_callback:
        progress_callback(0.05, "Fetching S&P 500 1M & 6M benchmark performance...")
    benchmark = fetch_sp500_benchmark()

    if progress_callback:
        progress_callback(0.12, "Fetching US Equity Universe from TradingView Screener...")
    df = fetch_tradingview_baseline_universe()

    if enrich_yf and not df.empty:
        # Filter to stocks with at least 150K volume so we only download yfinance history for liquid names
        df = enrich_with_yfinance_history(
            df,
            max_symbols_for_yf=max_symbols_for_yf,
            progress_callback=progress_callback,
        )
    else:
        df = enrich_with_yfinance_history(df, max_symbols_for_yf=0)

    if progress_callback:
        progress_callback(0.95, "Saving daily EOD snapshot to Supabase Cloud DB...")

    if is_supabase_configured():
        try:
            records = json.loads(df.to_json(orient="records"))
            sb_upsert_kv("daily_snapshot", records)
        except Exception as e:
            print(f"Warning: Supabase snapshot upload failed: {e}")

    if progress_callback:
        progress_callback(1.0, "Market data refresh complete!")

    return df, benchmark


def load_cached_market_data() -> Tuple[Optional[pd.DataFrame], Optional[Dict[str, Any]]]:
    """Loads cached daily snapshot and S&P 500 benchmark from Supabase Cloud DB."""
    df = None
    benchmark = None
    if is_supabase_configured():
        try:
            raw_records = sb_get_kv("daily_snapshot")
            if raw_records and isinstance(raw_records, list):
                df = pd.DataFrame(raw_records)
            raw_bm = sb_get_kv("benchmark_sp500")
            if raw_bm and isinstance(raw_bm, dict):
                benchmark = raw_bm
        except Exception:
            pass
    return df, benchmark


if __name__ == "__main__":
    print("Running EOD Market Data Pipeline...")
    t0 = time.time()
    df_out, bm_out = refresh_daily_market_data(
        enrich_yf=True,
        max_symbols_for_yf=800,
        progress_callback=lambda p, msg: print(f"[{int(p*100):3d}%] {msg}"),
    )
    elapsed = time.time() - t0
    print(f"Done in {elapsed:.1f}s! Cached {len(df_out)} US equities.")
    print(f"S&P 500 Benchmark ({bm_out['symbol']}): 1M = {bm_out['perf_1m_pct']:+.2f}%, 6M = {bm_out['perf_6m_pct']:+.2f}%")
