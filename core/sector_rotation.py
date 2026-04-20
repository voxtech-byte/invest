import pandas as pd
from typing import Dict, List, Any
from logger import get_logger

logger = get_logger(__name__)

def analyze_sector_rotation(all_stocks_data: Dict[str, pd.DataFrame], config: Dict) -> List[Dict[str, Any]]:
    """
    Ranks sectors based on 20-day momentum to detect sector rotation.
    Returns a sorted list of dictionaries with sector stats.
    
    Args:
        all_stocks_data: Dictionary mapping ticker to its DataFrame.
        config: System config containing 'sectors' map.
    """
    sectors_map = config.get('sectors', {})
    if not sectors_map:
        return []
        
    sector_performance = {}
    
    for symbol, df in all_stocks_data.items():
        if df is None or df.empty or len(df) < 20:
            continue
            
        sector = sectors_map.get(symbol)
        if not sector:
            continue
            
        if sector not in sector_performance:
            sector_performance[sector] = []
            
        # 20-day momentum
        try:
            current_price = df['Close'].iloc[-1]
            price_20d_ago = df['Close'].iloc[-20]
            momentum_20d = ((current_price - price_20d_ago) / price_20d_ago) * 100
            
            # Additional metrics: vol surge
            vol_avg_20 = df['Volume'].tail(20).mean()
            vol_current = df['Volume'].iloc[-1]
            vol_ratio = vol_current / vol_avg_20 if vol_avg_20 > 0 else 1.0
            
            sector_performance[sector].append({
                "symbol": symbol,
                "momentum_20d": float(momentum_20d),
                "vol_ratio": float(vol_ratio),
                "trend": "BULLISH" if df['Close'].iloc[-1] > df.get('SMA_50', pd.Series([0])).iloc[-1] else "BEARISH"
            })
        except Exception as e:
            continue
            
    # Aggregate by sector
    results = []
    for sector, members in sector_performance.items():
        if not members:
            continue
            
        avg_momentum = sum(m["momentum_20d"] for m in members) / len(members)
        avg_vol_ratio = sum(m["vol_ratio"] for m in members) / len(members)
        bullish_count = sum(1 for m in members if m["trend"] == "BULLISH")
        breadth = (bullish_count / len(members)) * 100
        
        rating = "HOT" if avg_momentum > 5 and breadth > 50 else \
                 "WARMING" if avg_momentum > 0 and avg_momentum <= 5 else \
                 "COOLING" if avg_momentum > -5 and avg_momentum <= 0 else "COLD"
                 
        results.append({
            "sector": sector,
            "avg_momentum_20d": round(avg_momentum, 2),
            "avg_vol_ratio": round(avg_vol_ratio, 2),
            "breadth_pct": round(breadth, 2),
            "member_count": len(members),
            "rating": rating
        })
        
    # Sort by momentum descending
    results.sort(key=lambda x: x["avg_momentum_20d"], reverse=True)
    return results
