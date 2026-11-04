"""
Infrastructure Tier — Database & Cloud Persistence Repositories.
"""

from src.infrastructure.supabase_client import (
    get_supabase_credentials,
    is_supabase_configured,
    sb_upsert_kv,
    sb_get_kv,
    sb_list_presets,
    sb_upsert_preset,
    sb_delete_preset,
    sb_insert_run_log,
    sb_list_run_logs,
)
from src.infrastructure.market_repo import (
    save_eod_market_snapshot,
    save_sp500_benchmark,
    load_cached_market_data,
)
from src.infrastructure.user_prefs_repo import (
    load_all_presets,
    save_custom_preset,
    delete_custom_preset,
    load_run_history,
    log_screening_run,
    load_tv_layout_id,
    save_tv_layout_id,
)

__all__ = [
    "get_supabase_credentials",
    "is_supabase_configured",
    "sb_upsert_kv",
    "sb_get_kv",
    "sb_list_presets",
    "sb_upsert_preset",
    "sb_delete_preset",
    "sb_insert_run_log",
    "sb_list_run_logs",
    "save_eod_market_snapshot",
    "save_sp500_benchmark",
    "load_cached_market_data",
    "load_all_presets",
    "save_custom_preset",
    "delete_custom_preset",
    "load_run_history",
    "log_screening_run",
    "load_tv_layout_id",
    "save_tv_layout_id",
]
