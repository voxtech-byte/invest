import os
import json
from datetime import datetime
from typing import Any
import pytz

TIMEZONE = pytz.timezone('Asia/Jakarta')

def is_market_open() -> bool:
    """
    Check if the IDX (Jakarta) market is currently open.
    Reflects standard IDX trading hours (Mon-Fri) with lunch breaks.
    """
    now = datetime.now(TIMEZONE)
    # 0 = Monday, 4 = Friday, 5 = Saturday, 6 = Sunday
    if now.weekday() >= 5:
        return False
        
    current_time = now.time()
    
    # Session 1: 09:00 - 12:00 (Fri 11:30)
    # Session 2: 13:30 - 15:50
    
    s1_start = datetime.strptime("09:00", "%H:%M").time()
    s1_end_fri = datetime.strptime("11:30", "%H:%M").time()
    s1_end_norm = datetime.strptime("12:00", "%H:%M").time()
    
    s2_start = datetime.strptime("13:30", "%H:%M").time()
    s2_end = datetime.strptime("15:50", "%H:%M").time()
    
    # Session 2 is same for all days
    if s2_start <= current_time <= s2_end:
        return True
        
    # Session 1
    if now.weekday() == 4: # Friday
        if s1_start <= current_time <= s1_end_fri:
            return True
    else: # Mon-Thu
        if s1_start <= current_time <= s1_end_norm:
            return True
            
    return False


def load_config() -> dict[str, Any]:
    with open("config.json", "r") as f:
        config = json.load(f)
    
    # Overlay sensitive environment variables if present
    # This enables secure public repo tracking where config.json is templated
    if os.getenv("ALPHA_VANTAGE_KEY"):
        config['api_keys']['alpha_vantage'] = os.getenv("ALPHA_VANTAGE_KEY")
    if os.getenv("FCS_API_KEY"):
        config['api_keys']['fcs_api'] = os.getenv("FCS_API_KEY")
    if os.getenv("SPREADSHEET_ID"):
        config['google_sheets']['spreadsheet_id'] = os.getenv("SPREADSHEET_ID")
        
    return config

def format_rp(n: float) -> str:
    return f"Rp {n:,.0f}".replace(',', '.')

def format_vol(n: float) -> str:
    return f"{n/1_000_000:.1f}M" if n >= 1e6 else f"{n/1_000:.1f}K"

def draw_progress_bar(value: float, max_val: int = 10) -> str:
    """Draws a visual bar like ██████░░░░"""
    try:
        val = int(round(value))
        filled = max(0, min(max_val, val))
        empty = max_val - filled
        return "█" * filled + "░" * empty
    except:
        return "░" * max_val

def generate_narrative(s: dict[str, Any]) -> str:
    """Generates Institutional Probabilistic Narrative"""
    bee = s.get('bee_score', 0)
    phase = s.get('wyckoff_phase', '')
    squeeze = s.get('is_squeeze', False)
    
    narratives = []
    
    if bee >= 8:
        narratives.append("Anomalous volume detection leans highly positive (Strong Bullish Edge).")
    elif bee >= 6:
        narratives.append("Moderate institutional footprint detected. Probable accumulation.")
    elif bee <= 3:
        narratives.append("Distribution markers present. Risk of downside liquidation.")
        
    if "MARKUP" in phase:
        narratives.append("Asset is currently in markup phase; trend alignment is optimal.")
    elif "ACCUMULATION" in phase:
        narratives.append("Price is consolidating at base. Favorable risk-to-reward if support holds.")
    elif "DISTRIBUTION" in phase:
        narratives.append("Price action suggests overhead supply. Defensive positioning recommended.")
        
    if squeeze:
        narratives.append("Volatility compression (Squeeze) indicates impending directional expansion.")
        
    if not narratives:
        narratives.append("Volume/Price consensus is neutral. Lacks clear probabilistic edge.")
        
    return " ".join(narratives)

def generate_chart(symbol: str, df, config: dict) -> str:
    """Generate candlestick chart with moving averages and volume, returns file path."""
    import mplfinance as mpf
    import os
    
    if df is None or df.empty:
        return ""
        
    # Ensure index is DatetimeIndex
    if not isinstance(df.index, pd.DatetimeIndex):
        import pandas as pd
        df.index = pd.to_datetime(df.index)
        
    os.makedirs("report_charts", exist_ok=True)
    file_path = f"report_charts/{symbol.replace('.JK', '')}_chart.png"
    
    # Extract config
    ind_cfg = config.get('indicators', {})
    ma_short = ind_cfg.get('ma_short', 50)
    ma_long = ind_cfg.get('ma_long', 200)
    
    # Setup addplots (MAs)
    addplots = []
    if f"SMA_{ma_short}" in df.columns:
        addplots.append(mpf.make_addplot(df[f"SMA_{ma_short}"], color='orange', width=1.5))
    if f"SMA_{ma_long}" in df.columns:
        addplots.append(mpf.make_addplot(df[f"SMA_{ma_long}"], color='blue', width=1.5))
        
    try:
        mpf.plot(
            df,
            type='candle',
            style='yahoo',
            volume=True,
            addplot=addplots,
            title=f"\n{symbol} - Sovereign Quant",
            savefig=file_path,
            warn_too_much_data=False,
            figratio=(12, 6)
        )
        return file_path
    except Exception as e:
        print(f"Chart generation failed for {symbol}: {e}")
        return ""
