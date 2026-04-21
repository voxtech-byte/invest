import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from logger import get_logger
from core.utils import TIMEZONE
from core.monte_carlo import run_monte_carlo
from core.institutional import calculate_institutional_footprint, calculate_volume_weighted_conviction
from core.dark_pool import detect_hidden_flows

logger = get_logger(__name__)


# ══════════════════════════════════════════════════════════════
# WYCKOFF PHASE DETECTION (VSA + Standard Phases)
# ══════════════════════════════════════════════════════════════

def detect_wyckoff_phase(df: pd.DataFrame) -> tuple[str, dict]:
    """
    Detect market cycle phase based on Wyckoff theory proxies + VSA.
    Returns (phase_label, metadata_dict) with conviction modifiers.
    """
    meta = {"conviction_modifier": 0.0, "block_entry": False, "trigger_exit": False, "wyckoff_target": None}

    if len(df) < 50:
        return "UNKNOWN", meta

    last = df.iloc[-1]
    prev_20 = df.iloc[-20]
    ma50 = last.get('SMA_50', 0)
    ma200 = last.get('SMA_200', 0)
    close = last['Close']
    low = last['Low']
    high = last['High']
    volume = last['Volume']
    vol_avg = last.get('Vol_Avg', volume) if last.get('Vol_Avg', 0) > 0 else volume
    support = last.get('Support_Level', 0)
    resistance = last.get('Resistance_Level', float('inf'))

    # ── 1. SPRING DETECTION (High Priority) ──
    # Low breaks below support AND close recovers above support in same candle
    # Volume > 1.5x average confirms institutional shakeout
    if support > 0 and low < support and close > support and volume > 1.5 * vol_avg:
        # Cause & Effect: projected target = entry + accumulation range width
        accum_range = resistance - support if resistance < float('inf') else close * 0.10
        meta["conviction_modifier"] = +1.5
        meta["wyckoff_target"] = round(close + accum_range, 0)
        return "SPRING — High Probability Reversal", meta

    # ── 2. UPTHRUST DETECTION (High Priority) ──
    # High breaks above resistance AND close falls back below resistance
    # Volume spike > 2x average confirms institutional distribution
    if resistance < float('inf') and high > resistance and close < resistance and volume > 2.0 * vol_avg:
        meta["conviction_modifier"] = -2.0
        meta["block_entry"] = True
        meta["trigger_exit"] = True
        return "UPTHRUST — Distribusi Institusi", meta

    # ── 3. STANDARD PHASES ──
    if close > ma50 > ma200 and ma50 > prev_20.get('SMA_50', 0):
        return "MARKUP (Strong Trend)", meta
    if close < ma50 < ma200:
        meta["trigger_exit"] = True
        return "MARKDOWN (Stay Away)", meta
    if ma50 < ma200 and ma50 > 0 and abs(close - ma50)/ma50 < 0.05:
        # Cause & Effect for accumulation
        accum_range = resistance - support if resistance < float('inf') and support > 0 else close * 0.08
        meta["wyckoff_target"] = round(close + accum_range, 0)
        return "ACCUMULATION (Smart Money Buying)", meta
    if close > ma200 and ma50 > 0 and abs(close - ma50)/ma50 < 0.05 and last.get('Pct_Change_5D', 0) < 0:
        meta["conviction_modifier"] = -0.5
        return "DISTRIBUTION (Institutions Selling)", meta

    return "CONSOLIDATION (Neutral)", meta


def detect_wyckoff_phase_simple(df: pd.DataFrame) -> str:
    """Backward-compatible wrapper returning just the label string."""
    label, _ = detect_wyckoff_phase(df)
    return label


# ══════════════════════════════════════════════════════════════
# BEE-FLOW ENGINE (Broker Intelligence via VPA Proxies)
# ══════════════════════════════════════════════════════════════

def calculate_bee_flow(df: pd.DataFrame) -> tuple[float, str]:
    """
    Simulate 'Broker Intelligence' (BEE-FLOW) using VPA proxies.
    """
    if len(df) < 20: return 0.0, "NEUTRAL"
    last = df.iloc[-1]
    pvt = last.get('PVT', 0)
    cmf = last.get('CMF_20', 0)
    vol_avg = last.get('Vol_Avg', 0)
    vol_ratio = last['Volume'] / vol_avg if vol_avg > 0 else 1.0

    score = 0.0
    if cmf > 0.2: score += 4
    elif cmf > 0: score += 2

    pvt_mean = df['PVT'].iloc[-5:].mean() if 'PVT' in df.columns else 0
    if pvt > pvt_mean: score += 3

    if last.get('Pct_Change_1D', 0) > 0 and vol_ratio > 1.5:
        score += 3 # Professional Accumulation
    elif last.get('Pct_Change_1D', 0) < 0 and vol_ratio > 1.5:
        score -= 4 # Institutional Dumping

    final_score = float(max(0, min(10, score)))
    if final_score >= 8: label = "HIGH ACCUMULATION (BIG BEE)"
    elif final_score >= 6: label = "MILD ACCUMULATION"
    elif final_score <= 3: label = "DISTRIBUTION (EXITING)"
    else: label = "NEUTRAL"
    return final_score, label


# ══════════════════════════════════════════════════════════════
# MULTI-TIMEFRAME CONFIRMATION
# ══════════════════════════════════════════════════════════════

def get_weekly_trend(df: pd.DataFrame) -> str:
    """
    Derive weekly trend from daily data by resampling.
    Returns: 'BULLISH', 'BEARISH', or 'NEUTRAL'
    """
    if len(df) < 60:
        return "NEUTRAL"

    try:
        weekly = df['Close'].resample('W').last().dropna()
        if len(weekly) < 12:
            return "NEUTRAL"

        sma_10w = weekly.rolling(10).mean().iloc[-1]
        sma_40w = weekly.rolling(40).mean().iloc[-1] if len(weekly) >= 40 else weekly.rolling(len(weekly)).mean().iloc[-1]
        last_close = weekly.iloc[-1]

        if last_close > sma_10w > sma_40w:
            return "BULLISH"
        elif last_close < sma_10w < sma_40w:
            return "BEARISH"
        else:
            return "NEUTRAL"
    except Exception:
        return "NEUTRAL"


# ══════════════════════════════════════════════════════════════
# EXIT SIGNAL EVALUATION (with Trailing Stop + Momentum Exit)
# ══════════════════════════════════════════════════════════════

def evaluate_exit_conditions(
    symbol: str,
    df: pd.DataFrame,
    config: dict,
    position: dict = None,
    ihsg_data: dict = None
) -> tuple[Optional[str], str]:
    """
    Dedicated exit signal evaluator for open positions.
    Includes: stop loss, trailing stop, momentum exit, VWAP rejection,
    Wyckoff phase exit, time-based exit, partial TP.

    Returns:
        (exit_type, reason) — e.g. ("AUTO_TRADE_SELL", "Stop Loss Breach")
        or (None, "") if no exit needed.
    """
    if position is None:
        return None, ""

    last = df.iloc[-1]
    close = last['Close']
    ind_cfg = config.get('indicators', {})
    exec_cfg = config.get('execution', {})
    entry_price = position.get('avg_price', close)
    entry_date_str = position.get('entry_date', '')
    tp1_hit = position.get('tp1_hit', False)
    highest_price = position.get('highest_price', entry_price)

    # ── Parse holding duration ──
    holding_days = 0
    if entry_date_str:
        try:
            entry_dt = datetime.fromisoformat(entry_date_str)
            holding_days = (datetime.now(TIMEZONE) - entry_dt).days
        except Exception:
            holding_days = 0

    # ── ATR & levels ──
    atr_period = ind_cfg.get('atr_period', 14)
    atr = last.get(f'ATRr_{atr_period}', last.get('ATR_14', close * 0.02))
    if atr <= 0:
        atr = close * 0.02
    support = last.get('Support_Level', close - atr * 2)

    # ── Compute base stop loss ──
    base_stop = max(support, entry_price - atr * 2)

    # ══ TRAILING STOP LOGIC ══
    # Activation: price has risen at least trailing_activation_atr × ATR from entry
    trail_activation = exec_cfg.get('trailing_activation_atr', 1.0)
    trail_multiplier = exec_cfg.get('trailing_stop_atr_multiplier', 1.5)

    # Update highest price tracker
    if close > highest_price:
        highest_price = close

    # Calculate trailing stop level
    if highest_price >= entry_price + (trail_activation * atr):
        # Trailing is active: stop follows highest_price minus trail distance
        trailing_stop = highest_price - (trail_multiplier * atr)
        stop_loss = max(base_stop, trailing_stop)
    else:
        stop_loss = base_stop

    # If TP1 was hit, ensure stop is at least at break-even (entry price)
    if tp1_hit:
        stop_loss = max(stop_loss, entry_price)

    target_1 = last.get('Resistance_Level', close + atr * 2)
    target_2 = close + atr * 4

    rsi_col = f"RSI_{ind_cfg.get('rsi_length', 14)}"
    rsi = last.get(rsi_col, 50)
    vol_avg = last.get('Vol_Avg', 0)
    vol_ratio = last['Volume'] / vol_avg if vol_avg > 0 else 1.0
    sma50 = last.get(f"SMA_{ind_cfg.get('ma_short', 50)}", 0)
    vwap = last.get('VWAP_D', 0)

    # Wyckoff phase with metadata
    phase, wyckoff_meta = detect_wyckoff_phase(df)

    # ══ EXIT 1: Price breaches Stop Loss ══
    if close <= stop_loss:
        trail_label = " (Trailing)" if highest_price >= entry_price + (trail_activation * atr) else ""
        return "AUTO_TRADE_SELL", f"Stop Loss{trail_label} Breach ({close:.0f} <= {stop_loss:.0f})"

    # ══ EXIT 2: Momentum Exit — RSI overbought + volume spike ══
    # Thresholds: RSI > 75 and Vol > 2.0x (Distribution)
    momentum_rsi = exec_cfg.get('momentum_exit_rsi', 75)
    momentum_vol = exec_cfg.get('momentum_exit_vol_ratio', 2.0)
    if rsi > momentum_rsi and vol_ratio > momentum_vol:
        return "AUTO_TRADE_SELL", f"Momentum Distribution (RSI={rsi:.1f}, Vol={vol_ratio:.1f}x)"


    # ══ EXIT 3: Close < SMA50 after holding > 3 days ══
    if sma50 > 0 and close < sma50 and holding_days >= 3:
        return "AUTO_TRADE_SELL", f"Below SMA50 after {holding_days}d ({close:.0f} < {sma50:.0f})"

    # ══ EXIT 4: VWAP Rejection — close drops below VWAP ══
    if vwap > 0 and close < vwap and holding_days >= 2:
        pnl_pct = ((close - entry_price) / entry_price * 100) if entry_price > 0 else 0
        if pnl_pct < -1.0:  # Only if also losing money
            return "AUTO_TRADE_SELL", f"VWAP Rejection ({close:.0f} < VWAP={vwap:.0f}, P&L={pnl_pct:+.1f}%)"

    # ══ EXIT 5: Wyckoff MARKDOWN or UPTHRUST ══
    if wyckoff_meta.get('trigger_exit', False):
        return "AUTO_TRADE_SELL", f"Wyckoff Exit: {phase}"
    if "DISTRIBUTION" in phase and holding_days >= 2:
        return "AUTO_TRADE_SELL", f"Wyckoff: {phase} (held {holding_days}d)"

    # ══ EXIT 6: Time-based forced exit ══
    force_exit_days = exec_cfg.get('force_exit_days', 21)
    if holding_days >= force_exit_days:
        return "AUTO_TRADE_SELL", f"Time Exit: {holding_days}d >= {force_exit_days}d"

    # ══ EXIT 7: Stale position (no profit after max_hold_days) ══
    max_hold_days = exec_cfg.get('max_hold_days', 14)
    pnl_pct = ((close - entry_price) / entry_price * 100) if entry_price > 0 else 0
    if holding_days >= max_hold_days and pnl_pct <= 0:
        return "AUTO_TRADE_SELL", f"Stale: {holding_days}d, P&L={pnl_pct:+.1f}%"

    # ══ PARTIAL TP: TP1 hit → signal 50% sell ══
    if not tp1_hit and close >= target_1:
        return "PARTIAL_TP1", f"TP1 ({close:.0f} >= {target_1:.0f}) — Sell 50%"

    # ══ FULL EXIT: TP2 hit ══
    if close >= target_2:
        return "AUTO_TRADE_SELL", f"TP2 ({close:.0f} >= {target_2:.0f}) — Full Exit"

    return None, ""


# ══════════════════════════════════════════════════════════════
# MAIN CONVICTION SCORING ENGINE
# ══════════════════════════════════════════════════════════════

def evaluate_signals(
    symbol: str,
    df: pd.DataFrame,
    config: dict,
    ihsg_data: dict = None,
    open_position: dict = None,
    sector_rotation: list = None
):
    """
    Weighted Conviction Scoring Engine V14 Phase 2.
    Includes Wyckoff conviction modifiers, VWAP gate, multi-timeframe gate,
    and Spring/Upthrust detection.

    Returns:
        (signal_dict, status_summary, reason_string)
    """
    valid_df = df.dropna(subset=['Close'])
    if valid_df.empty:
        return {'type': None, 'score': 0, 'data': {}}, None, "No valid price data"

    last = valid_df.iloc[-1]
    close = last['Close']
    exec_cfg = config.get('execution', {})

    # ── Guard clause: ensure Vol_Avg is valid ──
    if last.get('Vol_Avg', 0) <= 0:
        logger.warning(f"[{symbol}] Vol_Avg is 0 or missing — using raw volume as proxy")

    # ── Scoring Weights ──
    weights = config.get('conviction_weights', {})
    sm_score = _score_smart_money(df, last, config) * weights.get('smart_money', 0.35) / 0.35
    trend_score = _score_trend(last, config) * weights.get('trend', 0.25) / 0.25
    rsi_score = _score_rsi_phase(df, last, config) * weights.get('rsi_phase', 0.20) / 0.20
    vol_score = _score_volatility(last, config) * weights.get('volatility', 0.15) / 0.15
    macro_score = _score_macro(ihsg_data) * weights.get('macro', 0.05) / 0.05

    final_conviction = sm_score + trend_score + rsi_score + vol_score + macro_score

    # ── VWAP Bonus ──
    vwap = last.get('VWAP_D', 0)
    if vwap > 0 and close > vwap:
        final_conviction += 0.3

    # ── Sector Rotation Bonus ──
    if sector_rotation:
        sectors = config.get('sectors', {})
        my_sector = sectors.get(symbol)
        # Check if my sector is 'HOT'
        if my_sector:
            is_hot = any(s['sector'] == my_sector and s['rating'] == 'HOT' for s in sector_rotation)
            if is_hot:
                final_conviction += 0.5
                logger.debug(f"[{symbol}] Sector Rotation Bonus (+0.5) applied for {my_sector}")

    # ── Multi-Timeframe Confirmation ──
    weekly_trend = get_weekly_trend(df)

    # ── Wyckoff Phase + Conviction Modifier ──
    wyckoff_phase, wyckoff_meta = detect_wyckoff_phase(df)
    final_conviction += wyckoff_meta.get('conviction_modifier', 0.0)

    # ── V15: Institutional Behavior Modifiers ──
    dark_pool_result = detect_hidden_flows(df, config)
    inst_footprint = calculate_institutional_footprint(
        df, dark_pool_score=dark_pool_result.get('score', 0.0), config=config
    )
    vw_conviction_mod = calculate_volume_weighted_conviction(df)
    final_conviction += vw_conviction_mod

    # Institutional Footprint bonus: score >= 60 → +0.3, >= 80 → +0.5
    fp_score = inst_footprint.get('footprint_score', 0)
    if fp_score >= 80:
        final_conviction += 0.5
    elif fp_score >= 60:
        final_conviction += 0.3

    # ── V15: Squeeze + Accumulation Bonus ──
    is_squeeze = bool(last.get('Is_Squeeze', False))
    accum_days = last.get('Accum_Days', 0)
    if is_squeeze and accum_days >= 3:
        final_conviction += 0.4  # Compression + hidden accumulation = explosive potential
        logger.debug(f"[{symbol}] Squeeze+Accum bonus (+0.4): Squeeze={is_squeeze}, Accum={accum_days}d")

    # ── V15: Relative Strength vs IHSG Bonus ──
    rs_vs_ihsg = last.get('RS_vs_IHSG', 0.0)
    if rs_vs_ihsg > 5.0:  # Outperforming IHSG by 5%+ over 20d
        final_conviction += 0.3
        logger.debug(f"[{symbol}] RS vs IHSG bonus (+0.3): Alpha={rs_vs_ihsg:.1f}%")

    # ── V15: Spread Liquidity Warning (penalty) ──
    if bool(last.get('Spread_Flag', False)):
        final_conviction -= 0.3
        logger.debug(f"[{symbol}] Wide spread penalty (-0.3): Spread={last.get('Spread_Proxy', 0):.3f}")

    # Clamp conviction to 0-10 range
    final_conviction = max(0.0, min(10.0, final_conviction))

    # ── ATR-based Risk Management Targets ──
    ind_cfg = config.get('indicators', {})
    atr = last.get(f"ATRr_{ind_cfg.get('atr_period', 14)}", last.get('ATR_14', close * 0.02))
    support = last.get('Support_Level', close - atr * 2)
    resistance = last.get('Resistance_Level', close + atr * 2)

    stop_loss = round(max(support, close - atr * 2), 0)
    target_1 = round(min(resistance, close + atr * 2), 0)
    target_2 = round(close + atr * 4, 0)

    bee_score, bee_label = calculate_bee_flow(df)
    
    # ── Monte Carlo Risk Integration ──
    mc_data = {}
    if final_conviction >= exec_cfg.get('alert_only_threshold', 4.5):
        try:
            mc_data = run_monte_carlo(df, days=10, iterations=1000)
            if "error" not in mc_data:
                risk_rating = mc_data.get('risk_rating', 'MODERATE')
                if risk_rating == 'HIGH':
                    final_conviction -= 0.5
                    logger.debug(f"[{symbol}] Conviction payload reduced (-0.5) due to HIGH Monte Carlo Risk")
                # Clamp again
                final_conviction = max(0.0, min(10.0, final_conviction))
        except Exception as e:
            logger.warning(f"[{symbol}] Monte Carlo error: {e}")

    status_summary = {
        'symbol': symbol,
        'close': close,
        'conviction': round(final_conviction, 1),
        'wyckoff_phase': wyckoff_phase,
        'wyckoff_target': wyckoff_meta.get('wyckoff_target'),
        'bee_score': bee_score,
        'bee_label': bee_label,
        'stop_loss': stop_loss,
        'target_1': target_1,
        'target_2': target_2,
        'atr': atr,
        'weekly_trend': weekly_trend,
        'vwap': vwap,
        'mc_risk_rating': mc_data.get('risk_rating'),
        'mc_prob_profit': mc_data.get('prob_profit'),
        'mc_var_pct': mc_data.get('var_pct'),
        # V15 Alpha Fields
        'smi_10': round(float(last.get('SMI_10', 0)), 3),
        'accum_days': int(accum_days),
        'is_squeeze': is_squeeze,
        'squeeze_days': int(last.get('Squeeze_Days', 0)),
        'rs_vs_ihsg': round(float(rs_vs_ihsg), 2),
        'spread_proxy': round(float(last.get('Spread_Proxy', 0)), 4),
        'spread_flag': bool(last.get('Spread_Flag', False)),
        'inst_footprint': fp_score,
        'inst_label': inst_footprint.get('label', 'N/A'),
        'vw_conviction_mod': vw_conviction_mod
    }

    # ══════════════════════════════════════════════════════════
    # EXIT EVALUATION (if we hold a position)
    # ══════════════════════════════════════════════════════════
    if open_position is not None:
        exit_type, exit_reason = evaluate_exit_conditions(
            symbol, df, config, position=open_position, ihsg_data=ihsg_data
        )
        if exit_type:
            return {
                'type': exit_type,
                'score': final_conviction,
                'data': status_summary,
                'exit_reason': exit_reason
            }, status_summary, f"EXIT: {exit_reason}"

    # ══════════════════════════════════════════════════════════
    # ENTRY SIGNAL DETECTION
    # ══════════════════════════════════════════════════════════
    signal_type = None

    # ── Upthrust blocks entry ──
    if wyckoff_meta.get('block_entry', False):
        logger.info(f"[{symbol}] Entry BLOCKED by Wyckoff: {wyckoff_phase}")
        return {
            'type': None,
            'score': final_conviction,
            'data': status_summary
        }, status_summary, f"Blocked ({wyckoff_phase})"

    # Buy Signals — with multi-timeframe gate
    if final_conviction >= exec_cfg.get('auto_trade_threshold', 6.5):
        if weekly_trend != "BEARISH":
            signal_type = "AUTO_TRADE_BUY"
        else:
            logger.info(f"[{symbol}] AUTO_BUY blocked: Weekly BEARISH (score={final_conviction:.1f})")
            signal_type = "ALERT_ONLY_BUY"
    elif final_conviction >= exec_cfg.get('alert_only_threshold', 4.5):
        signal_type = "ALERT_ONLY_BUY"

    # Sell Signals (for stocks NOT in portfolio)
    if signal_type is None:
        if final_conviction <= exec_cfg.get('exit_threshold', 3.0):
            signal_type = "AUTO_TRADE_SELL"

        if "DISTRIBUTION" in wyckoff_phase or "UPTHRUST" in wyckoff_phase:
            if final_conviction < 5.0:
                signal_type = "AUTO_TRADE_SELL"

    if not signal_type:
        return {
            'type': None,
            'score': final_conviction,
            'data': status_summary
        }, status_summary, f"Neutral ({final_conviction:.1f})"

    return {
        'type': signal_type,
        'score': final_conviction,
        'data': status_summary
    }, status_summary, "SIGNAL_DETECTED"


# ══════════════════════════════════════════════════════════════
# SCORING SUB-FUNCTIONS (with safe guards)
# ══════════════════════════════════════════════════════════════

def _score_smart_money(df, last, config):
    vol_avg = last.get('Vol_Avg', 0)
    vol_ratio = last['Volume'] / vol_avg if vol_avg > 0 else 1.0
    cmf_col = [c for c in df.columns if c.startswith('CMF_')]
    cmf = last[cmf_col[0]] if cmf_col else 0.0
    score = (0.4 if vol_ratio > 2.0 else 0.2 if vol_ratio > 1.2 else 0) + (0.3 if cmf > 0 else 0)
    return 0.35 * min(1.0, score) * 10


def _score_trend(last, config):
    ma200 = last.get(f"SMA_{config['indicators']['ma_long']}", 0)
    score = (0.5 if last['Close'] > ma200 else 0) + (0.5 if last.get('ADX_14', 0) > 25 else 0)
    return 0.25 * min(1.0, score) * 10


def _score_rsi_phase(df, last, config):
    rsi = last.get(f"RSI_{config['indicators']['rsi_length']}", 50)
    phase = detect_wyckoff_phase_simple(df)
    score = (0.5 if 40 < rsi < 70 else 0) + (0.5 if "MARKUP" in phase or "ACCUMULATION" in phase else 0)
    return 0.20 * min(1.0, score) * 10


def _score_volatility(last, config):
    atr_pct = (last.get('ATR_14', 0) / last['Close']) * 100 if last['Close'] > 0 else 5.0
    score = 1.0 if atr_pct < 4.0 else 0.5 if atr_pct < 6.0 else 0.0
    return 0.15 * min(1.0, score) * 10


def _score_macro(ihsg):
    if ihsg is None:
        return 0.0
    trend = ihsg.get('trend', '')
    if trend == 'BULLISH':
        return 0.05 * 10
    pct = ihsg.get('percent', 0)
    if pct > 0.3:
        return 0.05 * 7
    return 0.0
