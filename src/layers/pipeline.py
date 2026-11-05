"""
Sequential Multi-Layer Screening Pipeline Orchestrator.
Executes enabled layers in sequence:
  Layer 0 (Universe Pre-Filter)
  -> Layer 1 (Trend & Momentum Template + Dynamic RS)
  -> Layer 2 (Momentum & Industry Strength Composite Scoring & Leader Ranking)
  -> [Future Extension Hooks: Layer 3 VCP, Layer 4 Entry Pivot, Layer 5 Risk/Sizing]
"""

from __future__ import annotations

import time
from typing import Dict, Any

import pandas as pd

from src.layers.base import ScreeningPipelineResult
from src.layers.layer0_universe import apply_layer0_filter
from src.layers.layer1_trend import evaluate_layer1_conditions
from src.layers.layer2_sector import evaluate_layer2_momentum_and_sector


def run_screening_pipeline(
    df_universe: pd.DataFrame,
    sp500_bm: Dict[str, Any],
    layer0_cfg: Dict[str, Any],
    layer1_cfg: Dict[str, Any],
    layer2_cfg: Dict[str, Any] | None = None,
) -> ScreeningPipelineResult:
    """
    Runs active screening layers sequentially in <1 second and returns a structured
    `ScreeningPipelineResult` ready for presentation or CLI/API consumption.
    """
    t0 = time.perf_counter()

    if layer2_cfg is None:
        layer2_cfg = {}

    # Step 1: Layer 0 — Candidate Universe Pre-Filter
    df_l0 = apply_layer0_filter(df_universe, layer0_cfg)

    # Step 2: Layer 1 — 11-Condition Trend & Momentum Evaluation + Pool-Wide RS Ranking
    df_l1, summary_meta = evaluate_layer1_conditions(df_l0, layer1_cfg, sp500_bm)

    # Step 3: Layer 2 — Momentum & Industry Strength Composite Scoring & Leader Ranking
    df_final, l2_meta = evaluate_layer2_momentum_and_sector(df_l1, df_l0, layer2_cfg)

    # Merge Layer 2 high-level counts into summary_meta for easy display
    summary_meta["l2_meta"] = l2_meta
    summary_meta["l2_qualified_count"] = l2_meta.get("l2_qualified_count", summary_meta.get("qualified_count", 0))

    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    return ScreeningPipelineResult(
        df_l0=df_l0,
        df_scored=df_final,
        summary_meta=summary_meta,
        l2_meta=l2_meta,
        elapsed_ms=elapsed_ms,
    )
