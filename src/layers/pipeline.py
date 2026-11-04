"""
Sequential Multi-Layer Screening Pipeline Orchestrator.
Executes enabled layers in sequence:
  Layer 0 (Universe Pre-Filter)
  -> Layer 1 (Trend & Momentum Template + Dynamic RS)
  -> [Future Extension Hooks: Layer 2 Sector RS, Layer 3 VCP, Layer 4 Entry Pivot, Layer 5 Risk/Sizing]
"""

from __future__ import annotations

import time
from typing import Dict, Any

import pandas as pd

from src.layers.base import ScreeningPipelineResult
from src.layers.layer0_universe import apply_layer0_filter
from src.layers.layer1_trend import evaluate_layer1_conditions


def run_screening_pipeline(
    df_universe: pd.DataFrame,
    sp500_bm: Dict[str, Any],
    layer0_cfg: Dict[str, Any],
    layer1_cfg: Dict[str, Any],
) -> ScreeningPipelineResult:
    """
    Runs all active screening layers sequentially in <1 second and returns a structured
    `ScreeningPipelineResult` ready for presentation or CLI/API consumption.
    """
    t0 = time.perf_counter()

    # Step 1: Layer 0 — Candidate Universe Pre-Filter
    df_l0 = apply_layer0_filter(df_universe, layer0_cfg)

    # Step 2: Layer 1 — 11-Condition Trend & Momentum Evaluation + Pool-Wide RS Ranking
    df_scored, summary_meta = evaluate_layer1_conditions(df_l0, layer1_cfg, sp500_bm)

    # Future Extension Hooks (Layers 2–5):
    # - Layer 2: `evaluate_layer2_sector_strength(df_scored, layer2_cfg)`
    # - Layer 3: `evaluate_layer3_vcp_pattern(df_scored, layer3_cfg)`
    # - Layer 4: `evaluate_layer4_entry_signals(df_scored, layer4_cfg)`
    # - Layer 5: `evaluate_layer5_position_sizing(df_scored, layer5_cfg)`

    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    return ScreeningPipelineResult(
        df_l0=df_l0,
        df_scored=df_scored,
        summary_meta=summary_meta,
        elapsed_ms=elapsed_ms,
    )
