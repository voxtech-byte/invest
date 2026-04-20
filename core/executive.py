from datetime import datetime
from typing import Any, Dict
from logger import get_logger
from core.utils import TIMEZONE, format_rp

logger = get_logger(__name__)


def calculate_position_size(
    price: float,
    stop_loss: float,
    conviction_score: float,
    config: dict,
    ihsg_data: dict = None
) -> tuple[int, float, float]:
    """
    Calculate lot size based on tiered risk-per-trade.
    Uses ATR-derived stop_loss for dynamic risk calculation.
    
    Args:
        price: Current stock price
        stop_loss: ATR-based stop loss level (MUST be < price for longs)
        conviction_score: Signal conviction (0-10)
        config: System configuration
        ihsg_data: IHSG macro data for adaptive multiplier
        
    Returns:
        (lot_size, position_value, risk_pct)
    """
    portfolio = config.get('portfolio', {})
    initial_equity = portfolio.get('initial_equity', 50_000_000)
    safety = config.get('safety', {})
    max_single_pct = safety.get('max_single_trade_equity_pct', 20)

    # ── VALIDATION: Stop Loss must be below price ──
    if stop_loss >= price:
        logger.warning(
            f"Invalid risk profile: stop_loss ({stop_loss:.0f}) >= price ({price:.0f}). "
            f"Falling back to 5% below price."
        )
        stop_loss = price * 0.95  # Emergency fallback only

    # ── ADAPTIVE ATR MULTIPLIER (IHSG volatility regime) ──
    atr_multiplier = 2.0
    if ihsg_data:
        ihsg_pct = abs(ihsg_data.get('percent', 0))
        if ihsg_pct > 1.5:
            atr_multiplier = 2.5  # High Volatility — wider stops
        elif ihsg_pct < 0.5:
            atr_multiplier = 1.5  # Low Volatility — tighter stops

    # ── TIERED RISK-PER-TRADE ──
    if conviction_score >= 9.0:
        risk_pct = 2.0
    elif conviction_score >= 7.5:
        risk_pct = 1.25
    elif conviction_score >= 6.5:
        risk_pct = 0.75
    elif conviction_score >= 4.5:
        risk_pct = 0.3
    else:
        return 0, 0.0, 0.0

    risk_amount = initial_equity * (risk_pct / 100)

    # ── RISK PER SHARE from actual stop loss distance ──
    risk_per_share = abs(price - stop_loss)
    if risk_per_share <= 0:
        risk_per_share = price * 0.05  # Emergency guard

    shares = int(risk_amount / risk_per_share)
    lot = (shares // 100) * 100  # Round to IDX lot size

    # ── CAP: Max single-trade equity exposure ──
    max_position = initial_equity * (max_single_pct / 100)
    position_value = lot * price
    if position_value > max_position:
        lot = int(max_position / price)
        lot = (lot // 100) * 100
        position_value = lot * price

    if lot <= 0:
        logger.info(
            f"Position size too small after calculations "
            f"(risk={risk_amount:.0f}, risk/share={risk_per_share:.0f})"
        )
        return 0, 0.0, risk_pct

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
    V14 Pro Safety Circuit Breakers.
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
    if ihsg_data and ihsg_data.get('pct_1d', ihsg_data.get('percent', 0.0)) < -safety.get('circuit_breaker_ihsg_pct', 2.0):
        is_safe = False
        warnings.append(f"MACRO CRASH: IHSG dropped {ihsg_data.get('pct_1d', ihsg_data.get('percent', 0.0)):.1f}%")

    return is_safe, warnings


def check_liquidity(last_row: dict, config: dict) -> tuple[bool, str]:
    """
    Verify minimum average daily trading value.
    Prevent entering illiquid stocks that are hard to exit.
    
    Returns:
        (is_liquid, reason)
    """
    health = config.get('health', {})
    min_avg_value = health.get('min_avg_value_rp', 5_000_000_000)  # 5B default

    avg_vol = last_row.get('Vol_Avg', 0)
    close = last_row.get('Close', 0)

    if avg_vol <= 0 or close <= 0:
        return False, "Missing volume/price data"

    avg_daily_value = avg_vol * close
    if avg_daily_value < min_avg_value:
        return False, f"Liquidity below threshold: Rp {avg_daily_value:,.0f} < Rp {min_avg_value:,.0f}"

    return True, "OK"
