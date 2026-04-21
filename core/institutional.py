"""
Sovereign Quant V15 — Institutional Behavior Module

Provides composite scores that estimate institutional presence and activity
in a given stock, using only daily OHLCV-derived factors.
"""

import pandas as pd
import numpy as np
from logger import get_logger

logger = get_logger(__name__)


def calculate_institutional_footprint(
    df: pd.DataFrame,
    dark_pool_score: float = 0.0,
    config: dict = None
) -> dict:
    """
    Composite Institutional Footprint Score (0-100).
    
    Combines 4 sub-scores:
      1. Dark Pool / Hidden Flow Score (external, from core/dark_pool.py)
      2. Accumulation Days streak
      3. Smart Money Index (SMI)
      4. Chaikin Money Flow (CMF)

    Returns:
        dict with 'footprint_score' (0-100), 'label', and sub-scores.
    """
    if df is None or df.empty or len(df) < 20:
        return {"footprint_score": 0, "label": "INSUFFICIENT DATA", "sub_scores": {}}

    last = df.iloc[-1]

    # ── Sub-Score 1: Dark Pool (0-25) ──
    # Already computed externally. Normalize to 0-25 range.
    dp_score = min(25.0, dark_pool_score * 2.5)

    # ── Sub-Score 2: Accumulation Days (0-25) ──
    # 0 days = 0, 3+ days = 15, 5+ days = 20, 7+ days = 25
    accum_days = last.get('Accum_Days', 0)
    if accum_days >= 7:
        accum_score = 25.0
    elif accum_days >= 5:
        accum_score = 20.0
    elif accum_days >= 3:
        accum_score = 15.0
    elif accum_days >= 1:
        accum_score = 8.0
    else:
        accum_score = 0.0

    # ── Sub-Score 3: Smart Money Index (0-25) ──
    # SMI_10 ranges roughly from -1 to +1.
    # > 0.3 = strong institutional buying at close.
    smi = last.get('SMI_10', 0.0)
    if smi > 0.5:
        smi_score = 25.0
    elif smi > 0.3:
        smi_score = 20.0
    elif smi > 0.1:
        smi_score = 12.0
    elif smi > 0:
        smi_score = 5.0
    else:
        smi_score = 0.0

    # ── Sub-Score 4: CMF (0-25) ──
    cmf_col = [c for c in df.columns if c.startswith('CMF_')]
    cmf = last[cmf_col[0]] if cmf_col else 0.0
    if cmf > 0.15:
        cmf_score = 25.0
    elif cmf > 0.05:
        cmf_score = 18.0
    elif cmf > 0:
        cmf_score = 8.0
    else:
        cmf_score = 0.0

    total = dp_score + accum_score + smi_score + cmf_score
    total = round(min(100.0, max(0.0, total)), 1)

    # Generate label
    if total >= 75:
        label = "HEAVY INSTITUTIONAL"
    elif total >= 50:
        label = "MODERATE INSTITUTIONAL"
    elif total >= 25:
        label = "LIGHT INSTITUTIONAL"
    else:
        label = "RETAIL DOMINANT"

    return {
        "footprint_score": total,
        "label": label,
        "sub_scores": {
            "dark_pool": round(dp_score, 1),
            "accumulation": round(accum_score, 1),
            "smi": round(smi_score, 1),
            "cmf": round(cmf_score, 1)
        }
    }


def calculate_volume_weighted_conviction(df: pd.DataFrame) -> float:
    """
    Volume-Weighted Conviction Modifier.
    
    Measures whether recent volume is occurring at the HIGH or LOW of the candle.
    If volume clusters near the highs → bullish conviction bonus.
    If volume clusters near the lows → bearish conviction penalty.

    Returns:
        Float modifier between -0.5 and +0.5 to be added to conviction score.
    """
    if df is None or df.empty or len(df) < 5:
        return 0.0

    try:
        recent = df.tail(5).copy()
        candle_range = recent['High'] - recent['Low']
        
        # Position of close within the candle (0 = at Low, 1 = at High)
        close_position = (recent['Close'] - recent['Low']) / candle_range.replace(0, float('nan'))
        close_position = close_position.fillna(0.5)

        # Weight by volume (normalized)
        vol_weights = recent['Volume'] / recent['Volume'].sum()
        
        # Weighted average position
        weighted_pos = (close_position * vol_weights).sum()

        # Map to modifier:
        # 0.0-0.3 → bearish (volume at lows): -0.5 to -0.2
        # 0.3-0.5 → neutral: -0.1 to 0
        # 0.5-0.7 → mildly bullish: 0 to 0.2
        # 0.7-1.0 → strongly bullish (volume at highs): 0.3 to 0.5
        if weighted_pos >= 0.7:
            modifier = 0.3 + (weighted_pos - 0.7) * (0.2 / 0.3)
        elif weighted_pos >= 0.5:
            modifier = (weighted_pos - 0.5) * (0.3 / 0.2)
        elif weighted_pos >= 0.3:
            modifier = -(0.5 - weighted_pos) * (0.1 / 0.2)
        else:
            modifier = -0.2 - (0.3 - weighted_pos) * (0.3 / 0.3)

        return round(max(-0.5, min(0.5, modifier)), 2)

    except Exception as e:
        logger.debug(f"Volume-Weighted Conviction error: {e}")
        return 0.0
