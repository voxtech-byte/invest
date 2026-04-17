from datetime import datetime
from typing import Any, Dict
from logger import get_logger
from core.utils import TIMEZONE, format_rp

logger = get_logger(__name__)

def calculate_position_size(price: float, stop_loss: float, conviction_score: float, config: dict) -> tuple[int, float, float]:
    """
    Calculate lot size based on tiered risk-per-trade.
    """
    portfolio = config.get('portfolio', {})
    initial_equity = portfolio.get('initial_equity', 50000000)
    
    if conviction_score >= 9.0: risk_pct = 2.0
    elif conviction_score >= 7.5: risk_pct = 1.25
    elif conviction_score >= 6.5: risk_pct = 0.75
    elif conviction_score >= 4.5: risk_pct = 0.3
    else: return 0, 0.0, 0.0
        
    risk_amount = initial_equity * (risk_pct / 100)
    risk_per_share = abs(price - stop_loss)
    if risk_per_share <= 0: risk_per_share = price * 0.05
        
    shares = int(risk_amount / risk_per_share)
    lot = (shares // 100) * 100
    position_value = lot * price
    
    return lot, position_value, risk_pct

def check_sector_exposure(symbol: str, open_positions: dict, config: dict) -> list[str]:
    """
    Check if addition would breach sector exposure limits.
    """
    sectors = config.get('sectors', {})
    portfolio = config.get('portfolio', {})
    max_sector_pct = portfolio.get('max_sector_exposure_pct', 25)
    max_pos = portfolio.get('max_open_positions', 5)
    
    current_sector = sectors.get(symbol, 'Unknown')
    sector_count = sum(1 for sym in open_positions if sectors.get(sym, 'Unknown') == current_sector)
    
    projected_count = sector_count + 1
    current_exposure_pct = (projected_count / max_pos) * 100
    
    warnings = []
    if current_exposure_pct > max_sector_pct:
        warnings.append(f"Sector {current_sector} exposure would reach {current_exposure_pct:.0f}% (Limit: {max_sector_pct}%)")
    
    return warnings

def check_safety_gates(broker, ihsg_data, config):
    """
    V11 Pro Safety Circuit Breakers.
    """
    safety = config.get('safety', {})
    is_safe = True
    warnings = []
    
    # 1. Daily Loss Limit
    daily_realized_loss = min(0.0, broker.get_daily_realized_pnl())
    max_loss_allowed = broker.get_balance() * (safety.get('daily_loss_limit_pct', 5.0) / 100)
    if abs(daily_realized_loss) >= max_loss_allowed:
        is_safe = False
        warnings.append(f"CIRCUIT BREAKER: Daily loss limit exceeded")
    
    # 2. Max Concurrent Positions
    if len(broker.get_open_positions()) >= safety.get('max_concurrent_positions', 5):
        is_safe = False
        warnings.append("MAX POSITIONS REACHED")
        
    # 3. Macro Crash
    if ihsg_data and ihsg_data.get('pct_1d', 0.0) < -safety.get('circuit_breaker_ihsg_pct', 2.0):
        is_safe = False
        warnings.append(f"MACRO CRASH: IHSG dropped {ihsg_data['pct_1d']:.1f}%")
        
    return is_safe, warnings
