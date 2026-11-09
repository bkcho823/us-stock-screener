"""
Built-in strategy presets shipped out-of-the-box.
"""

from __future__ import annotations

from typing import Dict, Any
from src.config.settings import (
    get_default_layer0_config,
    get_default_layer1_config,
    get_default_layer2_config,
    get_default_layer3_config,
    get_default_layer4_config,
    get_default_layer5_config,
)

BUILTIN_PRESETS: Dict[str, Dict[str, Any]] = {
    "Bryan's Full Setup ($3B + 500K Vol + $50M DolVol + All 11 Rules)": {
        "description": "Combines your TradingView Layer 0 ($3B Mkt Cap, 500K 1D/10D/30D/60D/90D Vol, $50M Dollar Vol) with all 8 Minervini Trend Template rules + SMA10>=SMA20 + Dynamic S&P 500 1M/6M.",
        "layer0": get_default_layer0_config(),
        "layer1": get_default_layer1_config(),
        "layer2": get_default_layer2_config(),
        "layer3": get_default_layer3_config(),
        "layer4": get_default_layer4_config(),
        "layer5": get_default_layer5_config(),
    },
    "🏆 JLaw 2024 USIC Championship ($1B Cap + RS≥85 + ADR≥3.2% + Hybrid Exit)": {
        "description": "Empirically validated 2024 USIC setup: $1B Market Cap floor (unlocks mid-cap rockets like POWL, RKLB, ASTS), RS ≥ 85, ADR(20) ≥ 3.2% (eliminates sleepy low-beta crowding), IPO Lifecycle Mode (<200 bars), and JLaw 50% @ +2.5R + 21EMA Trail.",
        "layer0": {
            **get_default_layer0_config(),
            "min_market_cap_b": 1.0,
            "min_dollar_vol_m": 25.0,
            "min_vol_1d": 300_000,
            "min_vol_10d": 300_000,
            "min_vol_30d": 300_000,
            "min_vol_60d": 300_000,
            "min_vol_90d": 300_000,
        },
        "layer1": {
            **get_default_layer1_config(),
            "c8_min_rs_percentile": 85,
            "ipo_mode_enabled": True,
        },
        "layer2": get_default_layer2_config(),
        "layer3": {
            **get_default_layer3_config(),
            "min_adr_pct": 3.2,
            "max_contraction_pct": 8.5,
            "max_vol_dryup_pct": 70.0,
        },
        "layer4": {
            **get_default_layer4_config(),
            "min_vol_expansion_pct": 140.0,
            "max_buy_zone_pct": 5.0,
        },
        "layer5": {
            **get_default_layer5_config(),
            "max_stop_loss_pct": 8.0,
            "min_reward_risk_ratio": 2.5,
            "exit_model": "JLAW_HYBRID",
            "earnings_guard_days": 10,
        },
    },
    "Bryan's Current TradingView Filter ($3B + TV Rules Only)": {
        "description": "Matches your exact TradingView screenshot: Layer 0 ($3B, 500K Vol, $50M DolVol) + Price > SMA200, SMA10 >= SMA20, and 1M & 6M Outperformance (with other Minervini rules toggled off).",
        "layer0": get_default_layer0_config(),
        "layer1": {
            **get_default_layer1_config(),
            "c1_enabled": True,
            "c2_enabled": False,
            "c3_enabled": False,
            "c4_enabled": False,
            "c5_enabled": False,
            "c6_enabled": False,
            "c7_enabled": False,
            "c8_enabled": False,
            "c9_enabled": True,
            "c10_enabled": True,
            "c11_enabled": True,
        },
    },
    "BRD Classic Minervini ($2B Mkt Cap + 8 Core Trend Rules)": {
        "description": "Original BRD baseline: Market Cap >= $2B, 300K Volume, and the classic 8 Mark Minervini Trend Template conditions.",
        "layer0": {
            **get_default_layer0_config(),
            "min_market_cap_b": 2.0,
            "min_vol_1d": 300_000,
            "min_vol_10d": 300_000,
            "min_vol_30d": 300_000,
            "min_vol_60d": 300_000,
            "min_vol_90d": 300_000,
            "min_dollar_vol_m": 20.0,
        },
        "layer1": {
            **get_default_layer1_config(),
            "c9_enabled": False,
            "c10_enabled": False,
            "c11_enabled": False,
        },
    },
}
