"""
Sovereign Quant V15 — Corporate Actions Detection Module

Detects and handles stock splits, reverse splits, and other corporate actions
that may affect price continuity and position calculations.
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional
from logger import get_logger

logger = get_logger(__name__)


def detect_stock_split(
    df: pd.DataFrame, 
    symbol: str,
    price_change_threshold: float = 0.40,
    volume_spike_threshold: float = 2.0
) -> Tuple[bool, Optional[float], str]:
    """
    Detect potential stock split or reverse split in recent data.
    
    Args:
        df: DataFrame with OHLCV data
        symbol: Stock ticker
        price_change_threshold: Min % price change to flag (default 40%)
        volume_spike_threshold: Min volume ratio to confirm (default 2x)
        
    Returns:
        Tuple of (is_split_detected, split_ratio, reason)
        - split_ratio: > 1 means forward split (e.g., 2 = 2:1 split)
                        < 1 means reverse split (e.g., 0.5 = 1:2 reverse)
                        None if not detected
    """
    if len(df) < 3:
        return False, None, "Insufficient data"
    
    last = df.iloc[-1]
    prev = df.iloc[-2]
    
    # Calculate overnight price change
    price_change_pct = abs((last['Close'] - prev['Close']) / prev['Close'])
    
    # Check for massive price jump
    if price_change_pct >= price_change_threshold:
        # Calculate implied split ratio
        split_ratio = last['Close'] / prev['Close']
        
        # Check volume confirmation (splits usually have high volume)
        vol_avg = df['Volume'].tail(20).mean()
        vol_ratio = last['Volume'] / vol_avg if vol_avg > 0 else 1.0
        
        if vol_ratio >= volume_spike_threshold or price_change_pct >= 0.80:
            split_type = "FORWARD" if split_ratio < 1.0 else "REVERSE"
            actual_ratio = 1.0 / split_ratio if split_ratio < 1.0 else split_ratio
            
            logger.warning(
                f"🔄 {split_type} SPLIT DETECTED for {symbol}: "
                f"{prev['Close']:.0f} → {last['Close']:.0f} "
                f"(implied ratio: {actual_ratio:.2f}:1, vol: {vol_ratio:.1f}x)"
            )
            
            return True, actual_ratio, f"{split_type}_SPLIT"
    
    return False, None, "No split detected"


def adjust_for_splits(
    df: pd.DataFrame,
    split_ratio: float,
    split_idx: int
) -> pd.DataFrame:
    """
    Adjust historical prices for split (backward adjustment).
    
    Args:
        df: DataFrame to adjust
        split_ratio: Ratio to apply (e.g., 2.0 for 2:1 split means divide prices by 2)
        split_idx: Index where split occurred (adjust all data before this)
        
    Returns:
        Adjusted DataFrame
    """
    if split_ratio <= 0 or split_idx <= 0:
        return df
    
    # For forward split (ratio > 1), historical prices should be divided
    # For reverse split (ratio < 1), historical prices should be multiplied
    df_adjusted = df.copy()
    
    price_cols = ['Open', 'High', 'Low', 'Close']
    
    for col in price_cols:
        if col in df_adjusted.columns:
            # Adjust all rows BEFORE the split
            mask = df_adjusted.index < df_adjusted.index[split_idx]
            if split_ratio > 1.0:
                # Forward split: divide historical prices
                df_adjusted.loc[mask, col] = df_adjusted.loc[mask, col] / split_ratio
            else:
                # Reverse split: multiply historical prices
                df_adjusted.loc[mask, col] = df_adjusted.loc[mask, col] * (1.0 / split_ratio)
    
    # Volume adjustment (inverse of price adjustment)
    if 'Volume' in df_adjusted.columns:
        mask = df_adjusted.index < df_adjusted.index[split_idx]
        if split_ratio > 1.0:
            df_adjusted.loc[mask, 'Volume'] = df_adjusted.loc[mask, 'Volume'] * split_ratio
        else:
            df_adjusted.loc[mask, 'Volume'] = df_adjusted.loc[mask, 'Volume'] / (1.0 / split_ratio)
    
    logger.info(f"📊 Applied {split_ratio:.2f}:1 split adjustment to {len(df_adjusted[df_adjusted.index < df_adjusted.index[split_idx]])} rows")
    
    return df_adjusted


def validate_price_continuity(
    df: pd.DataFrame,
    max_gap_pct: float = 0.15,
    lookback: int = 5
) -> Tuple[bool, str]:
    """
    Validate that price movements are continuous (no unexplained gaps).
    
    Args:
        df: DataFrame with price data
        max_gap_pct: Maximum allowed overnight gap %
        lookback: Number of days to check
        
    Returns:
        Tuple of (is_valid, reason)
    """
    if len(df) < lookback + 1:
        return True, "Insufficient data"
    
    recent = df.tail(lookback)
    
    for i in range(1, len(recent)):
        prev_close = recent.iloc[i-1]['Close']
        curr_open = recent.iloc[i]['Open']
        
        gap_pct = abs((curr_open - prev_close) / prev_close)
        
        if gap_pct > max_gap_pct:
            # Check if this was already flagged as split
            return False, f"Price gap {gap_pct*100:.1f}% at {recent.index[i]} (threshold: {max_gap_pct*100:.1f}%)"
    
    return True, "Price continuity OK"


def apply_corporate_actions_filter(
    df: pd.DataFrame,
    symbol: str,
    config: dict = None
) -> pd.DataFrame:
    """
    Main entry point: detect and adjust for all corporate actions.
    
    Args:
        df: Raw price data
        symbol: Stock ticker
        config: Optional config dict with thresholds
        
    Returns:
        Adjusted DataFrame
    """
    if config is None:
        config = {}
    
    ca_cfg = config.get('corporate_actions', {})
    
    # Detection thresholds
    split_threshold = ca_cfg.get('split_detection_threshold', 0.40)
    volume_threshold = ca_cfg.get('split_volume_threshold', 2.0)
    
    # Detect split
    is_split, split_ratio, reason = detect_stock_split(
        df, symbol, split_threshold, volume_threshold
    )
    
    if is_split and split_ratio:
        # Find split index (most recent day)
        split_idx = len(df) - 1
        df = adjust_for_splits(df, split_ratio, split_idx)
    
    # Validate continuity
    max_gap = ca_cfg.get('max_price_gap_pct', 0.15)
    is_valid, validation_msg = validate_price_continuity(df, max_gap)
    
    if not is_valid:
        logger.warning(f"[{symbol}] {validation_msg}")
    
    return df
