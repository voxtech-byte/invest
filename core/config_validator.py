"""
Sovereign Quant V15 — Configuration Validator

Validates all config.json parameters at startup to prevent
silent failures from invalid or missing values.
"""

from logger import get_logger

logger = get_logger(__name__)


# Schema definition: { key_path: (type, min, max, required) }
CONFIG_SCHEMA = {
    # ── Indicators ──
    "indicators.rsi_length": (int, 5, 50, True),
    "indicators.ma_short": (int, 5, 100, True),
    "indicators.ma_long": (int, 50, 500, True),
    "indicators.macd_fast": (int, 5, 50, True),
    "indicators.macd_slow": (int, 10, 100, True),
    "indicators.macd_signal": (int, 3, 30, True),
    "indicators.bb_period": (int, 5, 50, True),
    "indicators.bb_std": (float, 0.5, 5.0, True),
    "indicators.atr_period": (int, 5, 50, True),
    "indicators.volume_avg_period": (int, 5, 60, True),
    "indicators.sr_lookback_days": (int, 10, 365, True),

    # ── Portfolio ──
    "portfolio.initial_equity": (int, 1_000_000, 100_000_000_000, True),
    "portfolio.max_sector_exposure_pct": (float, 5.0, 100.0, True),
    "portfolio.max_open_positions": (int, 1, 50, True),
    "portfolio.risk_per_trade_pct": (float, 0.1, 10.0, True),
    "portfolio.max_portfolio_heat_pct": (float, 1.0, 30.0, True),
    "portfolio.max_drawdown_pct": (float, 1.0, 50.0, True),

    # ── Execution ──
    "execution.auto_trade_threshold": (float, 1.0, 10.0, True),
    "execution.alert_only_threshold": (float, 1.0, 10.0, True),
    "execution.max_hold_days": (int, 1, 120, True),
    "execution.tp1_scale_out_pct": (int, 10, 100, True),
    "execution.trailing_stop_atr_multiplier": (float, 0.5, 5.0, True),

    # ── Safety ──
    "safety.daily_loss_limit_pct": (float, 0.5, 20.0, True),
    "safety.max_concurrent_positions": (int, 1, 50, True),
    "safety.circuit_breaker_ihsg_pct": (float, 0.5, 10.0, True),
    "safety.max_single_trade_equity_pct": (float, 1.0, 50.0, True),

    # ── Conviction Weights ──
    "conviction_weights.smart_money": (float, 0.0, 1.0, True),
    "conviction_weights.trend": (float, 0.0, 1.0, True),
    "conviction_weights.rsi_phase": (float, 0.0, 1.0, True),
    "conviction_weights.volatility": (float, 0.0, 1.0, True),
    "conviction_weights.macro": (float, 0.0, 1.0, True),
}


def _get_nested(config: dict, path: str):
    """Get a value from a nested dict using dot-notation path."""
    keys = path.split(".")
    val = config
    for k in keys:
        if isinstance(val, dict) and k in val:
            val = val[k]
        else:
            return None
    return val


def validate_config(config: dict) -> list:
    """
    Validate config.json against the schema.

    Returns:
        List of warning/error strings. Empty list = all valid.
    """
    issues = []

    # ── 1. Schema validation ──
    for path, (expected_type, min_val, max_val, required) in CONFIG_SCHEMA.items():
        val = _get_nested(config, path)

        if val is None:
            if required:
                issues.append(f"🔴 MISSING: `{path}` is required but not found in config.json")
            continue

        # Type check (allow int for float fields)
        if expected_type == float and isinstance(val, int):
            val = float(val)
        if not isinstance(val, expected_type):
            issues.append(f"🟡 TYPE: `{path}` should be {expected_type.__name__}, got {type(val).__name__}")
            continue

        # Range check
        if val < min_val:
            issues.append(f"🟡 RANGE: `{path}` = {val} is below minimum ({min_val})")
        if val > max_val:
            issues.append(f"🟡 RANGE: `{path}` = {val} is above maximum ({max_val})")

    # ── 2. Cross-field validations ──
    # ma_short should be < ma_long
    ma_short = _get_nested(config, "indicators.ma_short")
    ma_long = _get_nested(config, "indicators.ma_long")
    if ma_short and ma_long and ma_short >= ma_long:
        issues.append(f"🔴 LOGIC: ma_short ({ma_short}) must be < ma_long ({ma_long})")

    # Conviction weights should sum to ~1.0
    weights = config.get("conviction_weights", {})
    total = sum(weights.values())
    if abs(total - 1.0) > 0.05:
        issues.append(f"🟡 WEIGHTS: conviction_weights sum to {total:.2f}, expected ~1.0")

    # Threshold ordering
    auto = _get_nested(config, "execution.auto_trade_threshold") or 0
    alert = _get_nested(config, "execution.alert_only_threshold") or 0
    if alert >= auto:
        issues.append(f"🟡 LOGIC: alert_only_threshold ({alert}) should be < auto_trade_threshold ({auto})")

    # ── 3. Stock list check ──
    stocks = config.get("stocks", [])
    if not stocks:
        issues.append("🔴 MISSING: `stocks` list is empty — nothing to scan")
    elif len(stocks) < 3:
        issues.append(f"🟡 LOW: Only {len(stocks)} stocks in watchlist — consider adding more")

    # ── 4. Sector mapping coverage ──
    sectors = config.get("sectors", {})
    unmapped = [s for s in stocks if s not in sectors]
    if unmapped:
        issues.append(f"🟡 SECTORS: {len(unmapped)} stocks have no sector mapping: {unmapped[:5]}...")

    # Log results
    if issues:
        logger.warning(f"⚙️ Config Validator found {len(issues)} issue(s)")
        for issue in issues:
            logger.warning(f"  {issue}")
    else:
        logger.info("✅ Config Validator: All parameters valid")

    return issues
