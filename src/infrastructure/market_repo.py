"""
Repository for saving and loading EOD Stock Universe Snapshots and S&P 500 Benchmark data.
"""

from __future__ import annotations

import json
from typing import Dict, Any, Optional, Tuple
import pandas as pd

from src.infrastructure.supabase_client import (
    is_supabase_configured,
    sb_upsert_kv,
    sb_get_kv,
)


def save_sp500_benchmark(benchmark: Dict[str, Any]) -> None:
    """Persists the S&P 500 benchmark metrics to Supabase Cloud DB if configured."""
    if is_supabase_configured():
        try:
            sb_upsert_kv("benchmark_sp500", benchmark)
        except Exception:
            pass


def save_eod_market_snapshot(df: pd.DataFrame) -> None:
    """Persists the EOD US equity snapshot table to Supabase Cloud DB."""
    if is_supabase_configured():
        records = json.loads(df.to_json(orient="records"))
        sb_upsert_kv("daily_snapshot", records)
    else:
        print("Notice: SUPABASE_URL / SUPABASE_KEY not configured in environment.")


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
