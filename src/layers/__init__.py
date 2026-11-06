"""
Domain / Screening Layers Package — Exports Layer 0, Layer 1, Layer 2, Layer 3, and the Pipeline.
"""

from src.layers.base import ScreeningPipelineResult, ScreeningLayer
from src.layers.layer0_universe import apply_layer0_filter
from src.layers.layer1_trend import (
    SHORT_DIAGNOSTIC_LABELS,
    evaluate_layer1_conditions,
    build_stock_condition_breakdown,
)
from src.layers.layer2_sector import (
    compute_group_momentum_rankings,
    evaluate_layer2_momentum_and_sector,
)
from src.layers.layer3_vcp import evaluate_layer3_vcp_and_structure
from src.layers.layer4_entry import evaluate_layer4_entry_signals
from src.layers.pipeline import run_screening_pipeline

__all__ = [
    "ScreeningPipelineResult",
    "ScreeningLayer",
    "SHORT_DIAGNOSTIC_LABELS",
    "apply_layer0_filter",
    "evaluate_layer1_conditions",
    "build_stock_condition_breakdown",
    "compute_group_momentum_rankings",
    "evaluate_layer2_momentum_and_sector",
    "evaluate_layer3_vcp_and_structure",
    "evaluate_layer4_entry_signals",
    "run_screening_pipeline",
]
