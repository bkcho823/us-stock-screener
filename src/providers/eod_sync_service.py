"""
End-of-Day (EOD) Market Sync Service — Orchestrates TradingView + Yahoo Finance
data ingestion and saves the daily snapshot directly to Supabase Cloud DB.
Used both by the 'Refresh Data' UI button and the weekday GitHub Actions cron job:
    python -m src.providers.eod_sync_service
"""

from __future__ import annotations

import time
from typing import Dict, Any, Optional, Callable, Tuple

import pandas as pd

from src.infrastructure.market_repo import save_eod_market_snapshot
from src.providers.tradingview_scanner import fetch_tradingview_baseline_universe
from src.providers.yahoo_finance import (
    fetch_sp500_benchmark,
    enrich_with_yfinance_history,
)


def refresh_daily_market_data(
    enrich_yf: bool = True,
    max_symbols_for_yf: int = 1200,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Full EOD data sync pipeline:
    1. Fetches S&P 500 1M and 6M benchmark returns
    2. Fetches US equity candidate pool from TradingView Screener API
    3. Enriches with exact 252-day SMA150 and SMA200 lookback slopes via yfinance
    4. Saves snapshot to Supabase Cloud DB for instant (<1s) re-screening.
    """
    if progress_callback:
        progress_callback(0.05, "Fetching S&P 500 1M & 6M benchmark performance...")
    benchmark = fetch_sp500_benchmark()

    if progress_callback:
        progress_callback(0.12, "Fetching US Equity Universe from TradingView Screener...")
    df = fetch_tradingview_baseline_universe()

    if enrich_yf and not df.empty:
        df = enrich_with_yfinance_history(
            df,
            max_symbols_for_yf=max_symbols_for_yf,
            progress_callback=progress_callback,
        )
    else:
        df = enrich_with_yfinance_history(df, max_symbols_for_yf=0)

    if progress_callback:
        progress_callback(0.95, "Saving daily EOD snapshot to Supabase Cloud DB...")

    save_eod_market_snapshot(df)

    if progress_callback:
        progress_callback(1.0, "Market data refresh complete!")

    return df, benchmark


if __name__ == "__main__":
    print("Running EOD Market Data Sync Service...")
    t0 = time.time()
    df_out, bm_out = refresh_daily_market_data(
        enrich_yf=True,
        max_symbols_for_yf=800,
        progress_callback=lambda p, msg: print(f"[{int(p * 100):3d}%] {msg}"),
    )
    elapsed = time.time() - t0
    print(f"Done in {elapsed:.1f}s! Synced {len(df_out)} US equities.")
    print(
        f"S&P 500 Benchmark ({bm_out['symbol']}): "
        f"1M = {bm_out['perf_1m_pct']:+.2f}%, 6M = {bm_out['perf_6m_pct']:+.2f}%"
    )
