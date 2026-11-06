"""
Base Contracts & Data Structures for the Pluggable Multi-Layer Screening Engine (Layers 0 through 5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Any, Protocol, Tuple

import pandas as pd


@dataclass
class ScreeningPipelineResult:
    """Standard output container produced by `run_screening_pipeline`."""
    df_l0: pd.DataFrame
    df_scored: pd.DataFrame
    summary_meta: Dict[str, Any] = field(default_factory=dict)
    l2_meta: Dict[str, Any] = field(default_factory=dict)
    l3_meta: Dict[str, Any] = field(default_factory=dict)
    l4_meta: Dict[str, Any] = field(default_factory=dict)
    l5_meta: Dict[str, Any] = field(default_factory=dict)
    elapsed_ms: float = 0.0


class ScreeningLayer(Protocol):
    """
    Standard interface contract for pluggable screening layers (Layer 0 .. Layer 5).
    Each layer accepts a DataFrame + layer config + context and returns an enriched/filtered DataFrame
    and layer metadata without mutating upstream state or importing Streamlit.
    """
    layer_id: str
    layer_name: str

    def evaluate(
        self,
        df: pd.DataFrame,
        config: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        ...
