"""
Configuration package — exports settings, threshold helpers, and built-in presets.
"""

from src.config.settings import (
    ALL_EXCHANGES,
    DEFAULT_TV_LAYOUT_ID,
    BASELINE_CACHE_MIN_MKT_CAP_B,
    BASELINE_CACHE_MIN_PRICE,
    BASELINE_CACHE_MIN_VOL,
    CONDITION_METADATA,
    get_default_layer0_config,
    get_default_layer1_config,
    get_default_layer2_config,
    get_default_layer3_config,
    get_default_layer4_config,
    get_default_layer5_config,
    compute_dynamic_sp500_threshold,
    extract_tv_layout_id,
    build_tv_chart_url,
)
from src.config.builtin_presets import BUILTIN_PRESETS

__all__ = [
    "ALL_EXCHANGES",
    "DEFAULT_TV_LAYOUT_ID",
    "BASELINE_CACHE_MIN_MKT_CAP_B",
    "BASELINE_CACHE_MIN_PRICE",
    "BASELINE_CACHE_MIN_VOL",
    "CONDITION_METADATA",
    "BUILTIN_PRESETS",
    "get_default_layer0_config",
    "get_default_layer1_config",
    "get_default_layer2_config",
    "get_default_layer3_config",
    "get_default_layer4_config",
    "get_default_layer5_config",
    "compute_dynamic_sp500_threshold",
    "extract_tv_layout_id",
    "build_tv_chart_url",
]
