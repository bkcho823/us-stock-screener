"""
Step 4: Preset Management & Run History Logger
- Manages Built-in + Custom User Presets (Layer 0 + Layer 1 configurations)
- Persists screening run logs (timestamp, S&P 500 1M/6M, candidate counts, passing tickers, settings)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Dict, Any, List

from src.config import PRESETS_FILE, RUN_HISTORY_FILE, BUILTIN_PRESETS


def load_all_presets() -> Dict[str, Dict[str, Any]]:
    """Returns built-in presets merged with any user-saved custom presets."""
    presets = {k: v for k, v in BUILTIN_PRESETS.items()}
    if PRESETS_FILE.exists():
        try:
            custom = json.loads(PRESETS_FILE.read_text(encoding="utf-8"))
            if isinstance(custom, dict):
                presets.update(custom)
        except Exception:
            pass
    return presets


def save_custom_preset(
    name: str,
    description: str,
    layer0_cfg: Dict[str, Any],
    layer1_cfg: Dict[str, Any],
) -> None:
    """Saves or updates a custom preset to data/presets.json."""
    custom: Dict[str, Any] = {}
    if PRESETS_FILE.exists():
        try:
            custom = json.loads(PRESETS_FILE.read_text(encoding="utf-8"))
        except Exception:
            custom = {}

    custom[name] = {
        "description": description or "Custom user preset",
        "layer0": layer0_cfg,
        "layer1": layer1_cfg,
        "saved_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    }
    PRESETS_FILE.write_text(json.dumps(custom, indent=2), encoding="utf-8")


def delete_custom_preset(name: str) -> bool:
    """Deletes a custom preset if it is not a built-in preset."""
    if name in BUILTIN_PRESETS or not PRESETS_FILE.exists():
        return False
    try:
        custom = json.loads(PRESETS_FILE.read_text(encoding="utf-8"))
        if name in custom:
            del custom[name]
            PRESETS_FILE.write_text(json.dumps(custom, indent=2), encoding="utf-8")
            return True
    except Exception:
        pass
    return False


def load_run_history() -> List[Dict[str, Any]]:
    """Loads saved screening run history logs (newest first)."""
    if not RUN_HISTORY_FILE.exists():
        return []
    try:
        history = json.loads(RUN_HISTORY_FILE.read_text(encoding="utf-8"))
        if isinstance(history, list):
            return history
    except Exception:
        pass
    return []


def log_screening_run(
    preset_name: str,
    layer0_cfg: Dict[str, Any],
    layer1_cfg: Dict[str, Any],
    summary_meta: Dict[str, Any],
    qualifying_tickers: List[str],
    elapsed_ms: float,
) -> Dict[str, Any]:
    """Appends a new screening run record to data/run_history.json."""
    history = load_run_history()
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
    history.insert(0, entry)
    history = history[:200]  # Keep most recent 200 runs
    RUN_HISTORY_FILE.write_text(json.dumps(history, indent=2), encoding="utf-8")
    return entry
