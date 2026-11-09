"""
Historical Market Data Loader for the 2024 USIC Benchmark Backtest.
- Fetches US stock metadata (exchange, sector, industry, implied shares) via TradingView Scanner.
- Guarantees inclusion of signature 2024 US momentum leaders (anti-survivorship check for stocks
  like SMCI or CELH whose market caps later declined in 2025/2026).
- Downloads split-adjusted daily OHLCV from 2022-11-01 to 2025-01-10 via Yahoo Finance in batches,
  ensuring full 252-day warm-up prior to 2024-01-02.
- Caches strictly outside the workspace root (never creates a local `data/` folder).
"""

from __future__ import annotations

import os
import pickle
import tempfile
from pathlib import Path
from typing import Dict, Any, List, Tuple

import numpy as np
import pandas as pd
import yfinance as yf

from src.providers.tradingview_scanner import fetch_tradingview_baseline_universe

# 28 Signature 2024 US Momentum Winners across Wave 1 (AI Semis), Wave 2 (Power/Consumer),
# and Wave 3 (AI Software, Crypto, Space, Fintech) for UAT Recall & Bottleneck Auditing.
SIGNATURE_2024_WINNERS: List[Dict[str, str]] = [
    {"ticker": "NVDA", "wave": "Q1 AI Semis", "company_name": "NVIDIA Corp.", "exchange": "NASDAQ", "sector": "Electronic Technology", "industry": "Semiconductors"},
    {"ticker": "SMCI", "wave": "Q1 AI Hardware", "company_name": "Super Micro Computer", "exchange": "NASDAQ", "sector": "Electronic Technology", "industry": "Computer Processing Hardware"},
    {"ticker": "ARM", "wave": "Q1 AI Semis (IPO)", "company_name": "Arm Holdings plc", "exchange": "NASDAQ", "sector": "Electronic Technology", "industry": "Semiconductors"},
    {"ticker": "ANET", "wave": "Q1 AI Networking", "company_name": "Arista Networks", "exchange": "NYSE", "sector": "Electronic Technology", "industry": "Computer Communications"},
    {"ticker": "AVGO", "wave": "Q1/Q2 AI Semis", "company_name": "Broadcom Inc.", "exchange": "NASDAQ", "sector": "Electronic Technology", "industry": "Semiconductors"},
    {"ticker": "VRT", "wave": "Q1/Q2 AI Cooling", "company_name": "Vertiv Holdings", "exchange": "NYSE", "sector": "Producer Manufacturing", "industry": "Electrical Products"},
    {"ticker": "DELL", "wave": "Q1/Q2 AI Servers", "company_name": "Dell Technologies", "exchange": "NYSE", "sector": "Electronic Technology", "industry": "Computer Processing Hardware"},
    {"ticker": "CELH", "wave": "Q1 Consumer Growth", "company_name": "Celsius Holdings", "exchange": "NASDAQ", "sector": "Consumer Non-Durables", "industry": "Beverages: Non-Alcoholic"},
    {"ticker": "DECK", "wave": "Q1 Retail Leader", "company_name": "Deckers Outdoor", "exchange": "NYSE", "sector": "Consumer Non-Durables", "industry": "Apparel/Footwear"},
    {"ticker": "WING", "wave": "Q1/Q2 Restaurant", "company_name": "Wingstop Inc.", "exchange": "NASDAQ", "sector": "Consumer Services", "industry": "Restaurants"},
    {"ticker": "VST", "wave": "Q2/Q3 AI Power", "company_name": "Vistra Corp.", "exchange": "NYSE", "sector": "Utilities", "industry": "Electric Utilities"},
    {"ticker": "CEG", "wave": "Q2 Nuclear Power", "company_name": "Constellation Energy", "exchange": "NASDAQ", "sector": "Utilities", "industry": "Electric Utilities"},
    {"ticker": "GEV", "wave": "Q2/Q3 Power Spin-Off", "company_name": "GE Vernova Inc.", "exchange": "NYSE", "sector": "Producer Manufacturing", "industry": "Electrical Products"},
    {"ticker": "POWL", "wave": "Q2/Q3 Grid Equip", "company_name": "Powell Industries", "exchange": "NASDAQ", "sector": "Producer Manufacturing", "industry": "Electrical Products"},
    {"ticker": "MOD", "wave": "Q1/Q2 Thermal Mgmt", "company_name": "Modine Manufacturing", "exchange": "NYSE", "sector": "Producer Manufacturing", "industry": "Auto Parts: OEM"},
    {"ticker": "CAVA", "wave": "Q2/Q3 Fast Casual", "company_name": "CAVA Group Inc.", "exchange": "NYSE", "sector": "Consumer Services", "industry": "Restaurants"},
    {"ticker": "HIMS", "wave": "Q2/Q4 Telehealth", "company_name": "Hims & Hers Health", "exchange": "NYSE", "sector": "Health Services", "industry": "Medical/Nursing Services"},
    {"ticker": "ONON", "wave": "Q2/Q3 Footwear", "company_name": "On Holding AG", "exchange": "NYSE", "sector": "Consumer Non-Durables", "industry": "Apparel/Footwear"},
    {"ticker": "APP", "wave": "Q3/Q4 AI AdTech", "company_name": "AppLovin Corp.", "exchange": "NASDAQ", "sector": "Technology Services", "industry": "Packaged Software"},
    {"ticker": "PLTR", "wave": "Q3/Q4 AI Software", "company_name": "Palantir Technologies", "exchange": "NASDAQ", "sector": "Technology Services", "industry": "Packaged Software"},
    {"ticker": "MSTR", "wave": "Q1 & Q4 Bitcoin Proxy", "company_name": "MicroStrategy Inc.", "exchange": "NASDAQ", "sector": "Technology Services", "industry": "Packaged Software"},
    {"ticker": "CVNA", "wave": "Q1–Q4 Turnaround", "company_name": "Carvana Co.", "exchange": "NYSE", "sector": "Retail Trade", "industry": "Specialty Stores"},
    {"ticker": "RDDT", "wave": "Q3/Q4 AI Data IPO", "company_name": "Reddit Inc.", "exchange": "NYSE", "sector": "Technology Services", "industry": "Internet Software/Services"},
    {"ticker": "RKLB", "wave": "Q3/Q4 Space Leader", "company_name": "Rocket Lab USA", "exchange": "NASDAQ", "sector": "Electronic Technology", "industry": "Aerospace & Defense"},
    {"ticker": "ASTS", "wave": "Q2/Q3 Space Telecom", "company_name": "AST SpaceMobile", "exchange": "NASDAQ", "sector": "Communications", "industry": "Wireless Telecommunications"},
    {"ticker": "HOOD", "wave": "Q1 & Q4 Fintech", "company_name": "Robinhood Markets", "exchange": "NASDAQ", "sector": "Finance", "industry": "Investment Banks/Brokers"},
    {"ticker": "CLS", "wave": "Q1–Q4 AI EMS", "company_name": "Celestica Inc.", "exchange": "NYSE", "sector": "Electronic Technology", "industry": "Electronic Production Equipment"},
    {"ticker": "AXON", "wave": "Q3/Q4 GovTech Leader", "company_name": "Axon Enterprise", "exchange": "NASDAQ", "sector": "Electronic Technology", "industry": "Aerospace & Defense"},
]


def get_default_cache_dir() -> Path:
    """Returns a safe external cache directory (never inside the workspace root)."""
    env_dir = os.environ.get("BACKTEST_CACHE_DIR", "").strip()
    if env_dir:
        p = Path(env_dir)
    else:
        p = Path(tempfile.gettempdir()) / "us_stock_vcp_backtest_2024_cache"
    p.mkdir(parents=True, exist_ok=True)
    return p


def load_or_fetch_2024_historical_dataset(
    cache_dir: Path | None = None,
    target_pool_size: int = 1050,
    start_date: str = "2022-11-01",
    end_date: str = "2025-01-10",
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """
    Loads cached 2023-2024 OHLCV + metadata bundle or fetches from TradingView + Yahoo Finance.
    Returns dict with keys:
      - `metadata_df`: DataFrame of candidate tickers, sector, industry, exchange, shares_est
      - `ohlcv_map`: Dict[ticker, DataFrame(Open, High, Low, Close, Volume)]
      - `sp500_df`: DataFrame(Open, High, Low, Close, Volume) for S&P 500 (^GSPC / SPY)
    """
    if cache_dir is None:
        cache_dir = get_default_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"dataset_2024_pool{target_pool_size}.pkl"

    if cache_file.exists() and not force_refresh:
        with open(cache_file, "rb") as fh:
            return pickle.load(fh)

    print(f"[1/3] Fetching US equity metadata from TradingView Scanner...")
    tv_df = fetch_tradingview_baseline_universe(min_mkt_cap_b=0.25, min_price=2.0)
    if tv_df.empty:
        raise RuntimeError("TradingView Scanner returned empty universe.")

    # Exclude ETFs / closed-end funds
    eq_df = tv_df[~tv_df["is_etf_or_fund"].fillna(False)].copy()
    eq_df["shares_est"] = np.where(
        (eq_df["close"] > 0) & (eq_df["market_cap"] > 0),
        eq_df["market_cap"] / eq_df["close"],
        0.0,
    )

    # Score candidates by blend of Market Cap and Dollar Volume so liquid mid-caps & mega-caps are both well represented
    eq_df["_liq_rank"] = (
        0.55 * eq_df["dollar_vol_m"].fillna(0.0).rank(pct=True)
        + 0.45 * eq_df["market_cap_b"].fillna(0.0).rank(pct=True)
    )
    eq_df = eq_df.sort_values("_liq_rank", ascending=False).reset_index(drop=True)

    selected_df = eq_df.head(target_pool_size).copy()
    existing_syms = set(selected_df["ticker"].tolist())

    # Force-include all 28 Signature 2024 Monster Winners (anti-survivorship check)
    extra_rows = []
    for item in SIGNATURE_2024_WINNERS:
        sym = item["ticker"]
        if sym in existing_syms:
            continue
        match = eq_df[eq_df["ticker"] == sym]
        if not match.empty:
            extra_rows.append(match.iloc[0].to_dict())
            existing_syms.add(sym)
        else:
            # Fallback metadata if ticker dropped below $250M or changed status later
            extra_rows.append(
                {
                    "ticker": sym,
                    "company_name": item["company_name"],
                    "exchange": item["exchange"],
                    "sector": item["sector"],
                    "industry": item["industry"],
                    "is_etf_or_fund": False,
                    "is_adr": False,
                    "shares_est": 0.0,
                }
            )
            existing_syms.add(sym)

    if extra_rows:
        selected_df = pd.concat([selected_df, pd.DataFrame(extra_rows)], ignore_index=True)

    # Backfill shares_est via yfinance fast_info if any forced ticker had 0 shares_est
    zero_share_mask = selected_df["shares_est"].fillna(0.0) <= 0
    for idx in selected_df[zero_share_mask].index:
        sym = str(selected_df.loc[idx, "ticker"])
        try:
            fi = yf.Ticker(sym).fast_info
            sh = float(getattr(fi, "shares", 0) or 0)
            if sh <= 0:
                mc = float(getattr(fi, "market_cap", 0) or 0)
                lp = float(getattr(fi, "last_price", 0) or 0)
                if mc > 0 and lp > 0:
                    sh = mc / lp
            if sh > 0:
                selected_df.loc[idx, "shares_est"] = sh
        except Exception:
            pass

    meta_cols = [
        "ticker",
        "company_name",
        "exchange",
        "sector",
        "industry",
        "is_etf_or_fund",
        "is_adr",
        "shares_est",
    ]
    metadata_df = selected_df[meta_cols].drop_duplicates(subset=["ticker"]).reset_index(drop=True)

    print(f"[2/3] Fetching S&P 500 (^GSPC / SPY) history ({start_date} -> {end_date})...")
    sp500_df = pd.DataFrame()
    for bm_sym in ["^GSPC", "SPY"]:
        try:
            raw_bm = yf.download(
                bm_sym,
                start=start_date,
                end=end_date,
                interval="1d",
                auto_adjust=True,
                progress=False,
            )
            if raw_bm is not None and not raw_bm.empty:
                if isinstance(raw_bm.columns, pd.MultiIndex):
                    raw_bm.columns = raw_bm.columns.get_level_values(0)
                sp500_df = raw_bm[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"]).copy()
                sp500_df.index = pd.to_datetime(sp500_df.index).tz_localize(None)
                if len(sp500_df) >= 400:
                    break
        except Exception:
            continue

    if sp500_df.empty:
        raise RuntimeError("Failed to download S&P 500 historical benchmark data.")

    tickers = metadata_df["ticker"].tolist()
    batch_size = 150
    total_batches = (len(tickers) + batch_size - 1) // batch_size
    ohlcv_map: Dict[str, pd.DataFrame] = {}

    print(f"[3/3] Downloading {len(tickers)} US stocks OHLCV ({start_date} -> {end_date}) in {total_batches} batches...")
    for b_idx in range(0, len(tickers), batch_size):
        batch_num = (b_idx // batch_size) + 1
        batch_syms = tickers[b_idx : b_idx + batch_size]
        yf_syms = [s.replace(".", "-") for s in batch_syms]
        print(f"      Batch {batch_num}/{total_batches} ({len(batch_syms)} tickers)...")
        try:
            raw = yf.download(
                tickers=yf_syms,
                start=start_date,
                end=end_date,
                interval="1d",
                auto_adjust=True,
                progress=False,
                threads=True,
                group_by="ticker",
            )
            if raw is None or raw.empty:
                continue

            is_multi = isinstance(raw.columns, pd.MultiIndex)
            top_levels = set(raw.columns.get_level_values(0)) if is_multi else set()

            for orig_sym, yf_sym in zip(batch_syms, yf_syms):
                try:
                    if not is_multi and len(yf_syms) == 1:
                        sub = raw
                    else:
                        if yf_sym not in top_levels:
                            continue
                        sub = raw[yf_sym]

                    cols_needed = ["Open", "High", "Low", "Close", "Volume"]
                    if not all(c in sub.columns for c in cols_needed):
                        continue
                    sub_clean = sub[cols_needed].dropna(subset=["Open", "High", "Low", "Close"]).copy()
                    if len(sub_clean) < 30:
                        continue
                    sub_clean.index = pd.to_datetime(sub_clean.index).tz_localize(None)
                    sub_clean["Volume"] = sub_clean["Volume"].fillna(0.0)
                    ohlcv_map[orig_sym] = sub_clean
                except Exception:
                    continue
        except Exception as exc:
            print(f"      [Warn] Batch {batch_num} error: {exc}")
            continue

    # Retry individually for any Signature 2024 Winner that missed batch download
    for item in SIGNATURE_2024_WINNERS:
        sym = item["ticker"]
        if sym not in ohlcv_map:
            try:
                sub = yf.download(
                    sym,
                    start=start_date,
                    end=end_date,
                    interval="1d",
                    auto_adjust=True,
                    progress=False,
                )
                if sub is not None and not sub.empty:
                    if isinstance(sub.columns, pd.MultiIndex):
                        sub.columns = sub.columns.get_level_values(0)
                    sub_clean = sub[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"]).copy()
                    sub_clean.index = pd.to_datetime(sub_clean.index).tz_localize(None)
                    ohlcv_map[sym] = sub_clean
            except Exception:
                pass

    metadata_df = metadata_df[metadata_df["ticker"].isin(ohlcv_map.keys())].reset_index(drop=True)
    print(f"[Done] Cached {len(ohlcv_map)} valid stock histories to {cache_file}")

    bundle = {
        "metadata_df": metadata_df,
        "ohlcv_map": ohlcv_map,
        "sp500_df": sp500_df,
    }
    with open(cache_file, "wb") as fh:
        pickle.dump(bundle, fh, protocol=pickle.HIGHEST_PROTOCOL)

    return bundle
