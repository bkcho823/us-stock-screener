"""
TradingView America Scanner Provider — Fetches US Stock Universe metadata,
volumes (1D/10D/30D/60D/90D), Dollar Volume, Market Cap, and baseline technicals.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import requests

from src.config.settings import (
    BASELINE_CACHE_MIN_MKT_CAP_B,
    BASELINE_CACHE_MIN_PRICE,
)

TV_SCAN_URL = "https://scanner.tradingview.com/america/scan"

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

    num_cols = [
        "close", "vol_1d", "vol_10d", "vol_30d", "vol_60d", "vol_90d",
        "dollar_vol", "market_cap", "sma_10", "sma_20", "sma_50", "sma_100",
        "sma_200", "high_52w", "low_52w", "perf_1m", "perf_3m", "perf_6m", "perf_12m",
    ]
    for c in num_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df["market_cap_b"] = (df["market_cap"] / 1e9).round(3)
    df["dollar_vol_m"] = np.where(
        df["dollar_vol"].notna() & (df["dollar_vol"] > 0),
        df["dollar_vol"] / 1e6,
        (df["close"] * df["vol_1d"]) / 1e6,
    ).round(2)

    type_str = df["type"].fillna("").astype(str).str.lower()
    subtype_str = df["subtype"].fillna("").astype(str).str.lower()
    df["is_etf_or_fund"] = (
        type_str.isin(["fund", "etf", "structured"])
        | subtype_str.str.contains("etf|fund|trust|closedend|preferred|unit|warrant", regex=True)
    )
    df["is_adr"] = (type_str == "dr") | subtype_str.str.contains("adr|depositary", regex=True)

    df = df[~df["ticker"].astype(str).str.contains(r"\^|/|\.", regex=True)].copy()
    return df.reset_index(drop=True)
