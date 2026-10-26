"""
Step 4: Preset Management & Run History Logger (Supabase Cloud DB Edition)
- Stores and retrieves Custom User Presets and Screening Run History in Supabase Online DB.
- Uses 0 MB of local disk storage.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Any, List

from src.config import BUILTIN_PRESETS
from src.supabase_client import (
    is_supabase_configured,
    sb_list_presets,
    sb_upsert_preset,
    sb_delete_preset,
    sb_insert_run_log,
    sb_list_run_logs,
)

# In-memory session fallback when running without Supabase credentials configured yet
_MEMORY_CUSTOM_PRESETS: Dict[str, Dict[str, Any]] = {}
_MEMORY_RUN_HISTORY: List[Dict[str, Any]] = []


def load_all_presets() -> Dict[str, Dict[str, Any]]:
    """Returns built-in presets merged with user-saved custom presets from Supabase."""
    presets = {k: v for k, v in BUILTIN_PRESETS.items()}
    if is_supabase_configured():
        try:
            custom = sb_list_presets()
            if isinstance(custom, dict):
                presets.update(custom)
        except Exception:
            presets.update(_MEMORY_CUSTOM_PRESETS)
    else:
        presets.update(_MEMORY_CUSTOM_PRESETS)
    return presets


def save_custom_preset(
    name: str,
    description: str,
    layer0_cfg: Dict[str, Any],
    layer1_cfg: Dict[str, Any],
) -> None:
    """Saves or updates a custom preset in Supabase `screener_presets` table."""
    saved_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    _MEMORY_CUSTOM_PRESETS[name] = {
        "description": description or "Custom user preset",
        "layer0": layer0_cfg,
        "layer1": layer1_cfg,
        "saved_at_utc": saved_at,
    }
    if is_supabase_configured():
        try:
            sb_upsert_preset(name, description or "Custom user preset", layer0_cfg, layer1_cfg, saved_at)
        except Exception:
            pass


def delete_custom_preset(name: str) -> bool:
    """Deletes a custom preset from Supabase if it is not a built-in preset."""
    if name in BUILTIN_PRESETS:
        return False
    _MEMORY_CUSTOM_PRESETS.pop(name, None)
    if is_supabase_configured():
        try:
            return sb_delete_preset(name)
        except Exception:
            return False
    return True


def load_run_history() -> List[Dict[str, Any]]:
    """Loads saved screening run history logs (newest first) from Supabase."""
    if is_supabase_configured():
        try:
            return sb_list_run_logs(limit=200)
        except Exception:
            return _MEMORY_RUN_HISTORY
    return _MEMORY_RUN_HISTORY


def log_screening_run(
    preset_name: str,
    layer0_cfg: Dict[str, Any],
    layer1_cfg: Dict[str, Any],
    summary_meta: Dict[str, Any],
    qualifying_tickers: List[str],
    elapsed_ms: float,
) -> Dict[str, Any]:
    """Saves a new screening run record to Supabase `screener_run_history`."""
    entry = {
        "run_id": datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"),
        "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "preset_name": preset_name,
        "layer0_candidates": int(summary_meta.get("layer0_count", 0)),
        "layer1_qualified": int(summary_meta.get("qualified_count", 0)),
        "active_conditions": int(summary_meta.get("active_condition_count", 11)),
        "sp500_1m_pct": float(summary_meta.get("sp500_1m_pct", 0.0)),
        "sp500_6m_pct": float(summary_meta.get("sp500_6m_pct", 0.0)),
        "y_1m_threshold_pct": float(summary_meta.get("y_1m_threshold_pct", 0.0)),
        "y_6m_threshold_pct": float(summary_meta.get("y_6m_threshold_pct", 0.0)),
        "min_market_cap_b": float(layer0_cfg.get("min_market_cap_b", 3.0)),
        "min_dollar_vol_m": float(layer0_cfg.get("min_dollar_vol_m", 50.0)),
        "elapsed_ms": round(float(elapsed_ms), 1),
        "top_tickers": qualifying_tickers[:30],
        "layer0_config": layer0_cfg,
        "layer1_config": layer1_cfg,
    }
    _MEMORY_RUN_HISTORY.insert(0, entry)
    if is_supabase_configured():
        try:
            sb_insert_run_log(entry)
        except Exception:
            pass
    return entry
