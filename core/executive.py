import pandas as pd
import numpy as np
from datetime import datetime
from typing import Any, Dict
from logger import get_logger
from core.utils import TIMEZONE, format_rp

logger = get_logger(__name__)


# ══════════════════════════════════════════════════════════════
# POSITION SIZING (ATR-Based Dynamic)
# ══════════════════════════════════════════════════════════════

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
        stop_loss = price * 0.95

    # ── ADAPTIVE ATR MULTIPLIER (IHSG volatility regime) ──
    regime = classify_ihsg_volatility(ihsg_data)
    if regime == "HIGH":
        atr_multiplier = 2.5
    elif regime == "LOW":
        atr_multiplier = 1.5
    else:
        atr_multiplier = 2.0

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
        risk_per_share = price * 0.05

    shares = int(risk_amount / risk_per_share)
    lot = (shares // 100) * 100

    # ── CAP: Max single-trade equity exposure ──
    max_position = initial_equity * (max_single_pct / 100)
    position_value = lot * price
    if position_value > max_position:
        lot = int(max_position / price)
        lot = (lot // 100) * 100
        position_value = lot * price

    if lot <= 0:
        logger.info(
            f"Position size too small "
            f"(risk={risk_amount:.0f}, risk/share={risk_per_share:.0f})"
        )
        return 0, 0.0, risk_pct

    return lot, position_value, risk_pct


# ══════════════════════════════════════════════════════════════
# IHSG VOLATILITY REGIME CLASSIFIER
# ══════════════════════════════════════════════════════════════

def classify_ihsg_volatility(ihsg_data: dict = None) -> str:
    """
    Classify IHSG volatility regime based on recent data.
    Uses rolling ATR comparison (short vs long period).

    Returns: 'HIGH', 'NORMAL', or 'LOW'
    """
    if ihsg_data is None:
        return "NORMAL"

    # If we have a pre-computed regime label, use it
    if 'volatility_regime' in ihsg_data:
        return ihsg_data['volatility_regime']

    # Fallback: use daily percent change as proxy
    pct = abs(ihsg_data.get('percent', 0))
    if pct > 1.5:
        return "HIGH"
    elif pct < 0.5:
        return "LOW"
    else:
        return "NORMAL"


# ══════════════════════════════════════════════════════════════
# SECTOR EXPOSURE CHECK
# ══════════════════════════════════════════════════════════════

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


# ══════════════════════════════════════════════════════════════
# SAFETY CIRCUIT BREAKERS
# ══════════════════════════════════════════════════════════════

def check_safety_gates(broker, ihsg_data, config):
    """
    V14 Pro Safety Circuit Breakers.
    Includes daily loss limit, max positions, macro crash,
    and max drawdown from peak equity.
    """
    safety = config.get('safety', {})
    portfolio = config.get('portfolio', {})
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

    # 4. Max Drawdown from Peak Equity
    max_dd_pct = portfolio.get('max_drawdown_pct', 15.0)
    peak_equity = broker.initial_equity  # In a full implementation, track peak from equity_snapshots
    current_equity = broker.get_balance()
    drawdown_pct = ((peak_equity - current_equity) / peak_equity) * 100 if peak_equity > 0 else 0
    if drawdown_pct >= max_dd_pct:
        is_safe = False
        warnings.append(f"MAX DRAWDOWN: {drawdown_pct:.1f}% from peak (limit: {max_dd_pct}%)")

    return is_safe, warnings


# ══════════════════════════════════════════════════════════════
# PORTFOLIO HEAT TRACKING
# ══════════════════════════════════════════════════════════════

def check_portfolio_heat(
    broker,
    new_risk_amount: float,
    config: dict
) -> tuple[bool, float, str]:
    """
    Calculate total portfolio heat (aggregate open risk as % of equity).
    Heat = sum of (position_qty × |entry_price - stop_loss|) for all positions.

    Args:
        broker: MockBroker instance
        new_risk_amount: Risk amount of the proposed new trade
        config: System configuration

    Returns:
        (is_within_limit, current_heat_pct, message)
    """
    portfolio = config.get('portfolio', {})
    max_heat_pct = portfolio.get('max_portfolio_heat_pct', 6.0)
    equity = broker.get_balance()

    if equity <= 0:
        return False, 100.0, "Zero equity"

    # Estimate risk of existing positions
    # Each position: risk = quantity × (avg_price × 0.05) as proxy
    # In production, each position would store its own stop_loss
    total_risk = 0.0
    for sym, pos in broker.get_open_positions().items():
        qty = pos.get('quantity', 0)
        avg_price = pos.get('avg_price', 0)
        # Default risk per share ~5% of entry if no stop stored
        pos_stop = pos.get('stop_loss', avg_price * 0.95)
        risk_per_share = abs(avg_price - pos_stop)
        total_risk += qty * risk_per_share

    # Add proposed new trade risk
    projected_risk = total_risk + new_risk_amount
    heat_pct = (projected_risk / equity) * 100

    if heat_pct > max_heat_pct:
        return False, heat_pct, f"Portfolio heat {heat_pct:.1f}% exceeds {max_heat_pct}% limit"

    return True, heat_pct, "OK"


# ══════════════════════════════════════════════════════════════
# CORRELATION CHECK
# ══════════════════════════════════════════════════════════════

def check_correlation(
    symbol: str,
    df_new: pd.DataFrame,
    open_positions: dict,
    config: dict,
    fetch_data_fn=None
) -> list[str]:
    """
    Check 30-day correlation of candidate stock vs existing positions.
    Warns if correlation > 0.75 to prevent over-concentration.

    Args:
        symbol: New candidate ticker
        df_new: DataFrame of the candidate stock
        open_positions: Currently open positions dict
        config: System config
        fetch_data_fn: Function to fetch historical data for existing positions

    Returns:
        List of warning strings (empty = no issues)
    """
    portfolio = config.get('portfolio', {})
    max_corr = portfolio.get('max_correlation_threshold', 0.75)
    lookback = portfolio.get('correlation_lookback_days', 30)
    warnings = []

    if not open_positions or fetch_data_fn is None:
        return warnings

    # Get the new stock's returns
    if len(df_new) < lookback:
        return warnings

    new_returns = df_new['Close'].pct_change().tail(lookback).dropna()
    if len(new_returns) < 15:
        return warnings

    for existing_sym in open_positions:
        if existing_sym == symbol:
            continue
        try:
            df_existing = fetch_data_fn(existing_sym, config)
            if df_existing is None or len(df_existing) < lookback:
                continue

            existing_returns = df_existing['Close'].pct_change().tail(lookback).dropna()
            if len(existing_returns) < 15:
                continue

            # Align indexes and compute correlation
            aligned = pd.concat([new_returns, existing_returns], axis=1, join='inner')
            if len(aligned) < 15:
                continue

            corr = aligned.iloc[:, 0].corr(aligned.iloc[:, 1])
            if not np.isnan(corr) and abs(corr) > max_corr:
                warnings.append(
                    f"High correlation with {existing_sym}: {corr:.2f} "
                    f"(threshold: {max_corr})"
                )
        except Exception as e:
            logger.debug(f"Correlation check error ({symbol} vs {existing_sym}): {e}")
            continue

    return warnings


# ══════════════════════════════════════════════════════════════
# LIQUIDITY FILTER
# ══════════════════════════════════════════════════════════════

def check_liquidity(last_row: dict, config: dict) -> tuple[bool, str]:
    """
    Verify minimum average daily trading value.
    Prevent entering illiquid stocks that are hard to exit.

    Returns:
        (is_liquid, reason)
    """
    health = config.get('health', {})
    min_avg_value = health.get('min_avg_value_rp', 5_000_000_000)

    avg_vol = last_row.get('Vol_Avg', 0)
    close = last_row.get('Close', 0)

    if avg_vol <= 0 or close <= 0:
        return False, "Missing volume/price data"

    avg_daily_value = avg_vol * close
    if avg_daily_value < min_avg_value:
        return False, f"Liquidity below threshold: Rp {avg_daily_value:,.0f} < Rp {min_avg_value:,.0f}"

    return True, "OK"
