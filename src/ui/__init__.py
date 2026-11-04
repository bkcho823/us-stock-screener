"""
Presentation Layer (`src/ui/`) — Modular Streamlit Components for the US Stock Screener.
"""

from src.ui.theme import apply_custom_theme
from src.ui.state_manager import (
    init_session_state,
    apply_preset_to_state,
    ensure_market_data_loaded,
)
from src.ui.top_header import render_top_header
from src.ui.pills import render_layer0_pills, render_layer1_pills
from src.ui.bottleneck_strip import render_bottleneck_strip
from src.ui.watchlist_grid import render_watchlist_grid
from src.ui.tradingview_cockpit import render_tradingview_cockpit

__all__ = [
    "apply_custom_theme",
    "init_session_state",
    "apply_preset_to_state",
    "ensure_market_data_loaded",
    "render_top_header",
    "render_layer0_pills",
    "render_layer1_pills",
    "render_bottleneck_strip",
    "render_watchlist_grid",
    "render_tradingview_cockpit",
]
