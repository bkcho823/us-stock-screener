"""
2024 Historical Backtest & UAT Evaluation Engine (`src/backtest/`).
Decoupled from the live Streamlit UI (`app.py` / `src/ui/`) so historical
walk-forward simulations and UAT diagnostics can run cleanly via CLI or tests.
"""

from src.backtest.pit_feature_engine import build_pit_panel, extract_day_universe
from src.backtest.portfolio_simulator import (
    run_monster_winner_recall_audit,
    run_walk_forward_simulation,
)

__all__ = [
    "build_pit_panel",
    "extract_day_universe",
    "run_monster_winner_recall_audit",
    "run_walk_forward_simulation",
]
