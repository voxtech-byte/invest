import pandas as pd
from logger import get_logger

logger = get_logger(__name__)

def detect_black_swan_event(df: pd.DataFrame, threshold_multiplier: float = 3.0) -> dict:
    """
    Sovereign 'Black Swan' Alarm.
    Triggers if current Volatility (ATR) is significantly higher than the rolling average.
    """
    if len(df) < 30:
        return {"alert": False, "factor": 1.0}
    
    # Use the ATR column calculated in indicators.py
    atr_col = [c for c in df.columns if c.startswith('ATR')]
    if not atr_col:
        return {"alert": False, "factor": 1.0}
    
    current_atr = df[atr_col[0]].iloc[-1]
    avg_atr = df[atr_col[0]].tail(30).mean()
    
    volsurf_factor = current_atr / avg_atr if avg_atr > 0 else 1.0
    
    if volsurf_factor >= threshold_multiplier:
        logger.critical(f"🚨 BLACK SWAN DETECTED: Volatility Spike {volsurf_factor:.1f}x above average!")
        return {
            "alert": True,
            "factor": volsurf_factor,
            "severity": "CRITICAL" if volsurf_factor > 4.0 else "WARNING",
            "message": f"Market Volatility Expansion ({volsurf_factor:.1f}x ATR). Liquidity risk high."
        }
    
    return {"alert": False, "factor": volsurf_factor}
