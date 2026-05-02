import pandas as pd
from logger import get_logger

logger = get_logger(__name__)

def detect_hidden_flows(df: pd.DataFrame, config: dict) -> dict:
    """
    Institutional Anomaly Detection: 
    Sudden spikes in volume without significant price movement.
    (Potential Dark Pool / Hidden Institutional Accumulation)
    """
    if len(df) < 5: return {"detected": False, "score": 0.0}
    
    # Get thresholds from config with defaults
    dark_pool_cfg = config.get('dark_pool', {})
    vol_threshold = dark_pool_cfg.get('volume_ratio_threshold', 2.5)
    price_change_max = dark_pool_cfg.get('max_price_change_pct', 0.5)
    lookback_days = dark_pool_cfg.get('volume_lookback_days', 20)
    
    last = df.iloc[-1]
    vol_avg = last.get('Vol_Avg', df['Volume'].tail(lookback_days).mean())
    vol_ratio = last['Volume'] / vol_avg if vol_avg > 0 else 1.0
    price_change_pct = abs(last.get('Pct_Change_1D', 0.0))
    
    # Logic: Volume > threshold x Avg AND Price Change < threshold%
    is_anomaly = (vol_ratio > vol_threshold) and (price_change_pct < price_change_max)
    
    if is_anomaly:
        logger.warning(f"⚠️ DARK POOL ANOMALY DETECTED: Vol Ratio {vol_ratio:.1f}x with Price Change {price_change_pct:.2f}%")
        return {
            "detected": True,
            "vol_ratio": vol_ratio,
            "label": "HIDDEN FLOW (Institutional Accumulation)",
            "score": round(vol_ratio * 2, 1) # Bonus conviction
        }
    
    return {"detected": False, "score": 0.0}
