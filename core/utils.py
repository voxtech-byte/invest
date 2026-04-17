import os
import json
from datetime import datetime
from typing import Any
import pytz

TIMEZONE = pytz.timezone('Asia/Jakarta')

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
