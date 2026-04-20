import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from logger import get_logger
from core.utils import TIMEZONE

logger = get_logger(__name__)


# ══════════════════════════════════════════════════════════════
# WYCKOFF PHASE DETECTION (VSA + Standard Phases)
# ══════════════════════════════════════════════════════════════

def detect_wyckoff_phase(df: pd.DataFrame) -> str:
    """
    Detect market cycle phase based on Wyckoff theory proxies + VSA.
    Accumulation, Markup, Distribution, Markdown, Spring, Upthrust.
    """
    if len(df) < 50: return "UNKNOWN"
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

    # 1. VSA SPECIAL PHASES (Priority)
    if low < support < close and volume > 1.5 * vol_avg:
        return "SPRING (Potential Accumulation Shakeout)"
    if high > resistance > close and volume > 1.2 * vol_avg:
        return "UPTHRUST (Potential Distribution Test)"

    # 2. STANDARD PHASES
    if close > ma50 > ma200 and ma50 > prev_20.get('SMA_50', 0):
        return "MARKUP (Strong Trend)"
    if close < ma50 < ma200:
        return "MARKDOWN (Stay Away)"
    if ma50 < ma200 and ma50 > 0 and abs(close - ma50)/ma50 < 0.05:
        return "ACCUMULATION (Smart Money Buying)"
    if close > ma200 and ma50 > 0 and abs(close - ma50)/ma50 < 0.05 and last.get('Pct_Change_5D', 0) < 0:
        return "DISTRIBUTION (Institutions Selling)"

    return "CONSOLIDATION (Neutral)"


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
# EXIT SIGNAL EVALUATION
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
    Checks multiple exit conditions and returns the most urgent one.

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

    # ── Parse holding duration ──
    holding_days = 0
    if entry_date_str:
        try:
            entry_dt = datetime.fromisoformat(entry_date_str)
            holding_days = (datetime.now(TIMEZONE) - entry_dt).days
        except Exception:
            holding_days = 0

    # ── Compute dynamic stop/target from ATR ──
    atr_period = ind_cfg.get('atr_period', 14)
    atr = last.get(f'ATRr_{atr_period}', last.get('ATR_14', close * 0.02))
    support = last.get('Support_Level', close - atr * 2)
    stop_loss = max(support, close - atr * 2)

    # If TP1 was already hit, trail stop to entry (break-even)
    tp1_hit = position.get('tp1_hit', False)
    if tp1_hit:
        stop_loss = max(stop_loss, entry_price)

    target_1 = last.get('Resistance_Level', close + atr * 2)
    target_2 = close + atr * 4

    rsi_col = f"RSI_{ind_cfg.get('rsi_length', 14)}"
    rsi = last.get(rsi_col, 50)
    vol_avg = last.get('Vol_Avg', 0)
    vol_ratio = last['Volume'] / vol_avg if vol_avg > 0 else 1.0
    sma50 = last.get(f"SMA_{ind_cfg.get('ma_short', 50)}", 0)
    phase = detect_wyckoff_phase(df)

    # ══ EXIT CONDITION 1: Price breaches Stop Loss ══
    if close <= stop_loss:
        return "AUTO_TRADE_SELL", f"Stop Loss Breach ({close:.0f} <= {stop_loss:.0f})"

    # ══ EXIT CONDITION 2: RSI overbought + volume spike = distribution ══
    if rsi > 75 and vol_ratio > 1.5:
        return "AUTO_TRADE_SELL", f"Overbought Distribution (RSI={rsi:.0f}, VolRatio={vol_ratio:.1f}x)"

    # ══ EXIT CONDITION 3: Close < SMA50 after holding > 3 days ══
    if sma50 > 0 and close < sma50 and holding_days >= 3:
        return "AUTO_TRADE_SELL", f"Below SMA50 after {holding_days}d hold ({close:.0f} < SMA50={sma50:.0f})"

    # ══ EXIT CONDITION 4: Wyckoff MARKDOWN or DISTRIBUTION ══
    if "MARKDOWN" in phase:
        return "AUTO_TRADE_SELL", f"Wyckoff Phase: {phase}"
    if "DISTRIBUTION" in phase and holding_days >= 2:
        return "AUTO_TRADE_SELL", f"Wyckoff Phase: {phase} (held {holding_days}d)"

    # ══ EXIT CONDITION 5: Time-based forced exit ══
    force_exit_days = exec_cfg.get('force_exit_days', 21)
    if holding_days >= force_exit_days:
        return "AUTO_TRADE_SELL", f"Time-Based Exit: {holding_days}d >= {force_exit_days}d limit"

    # ══ EXIT CONDITION 6: Max hold without profit ══
    max_hold_days = exec_cfg.get('max_hold_days', 14)
    pnl_pct = ((close - entry_price) / entry_price * 100) if entry_price > 0 else 0
    if holding_days >= max_hold_days and pnl_pct <= 0:
        return "AUTO_TRADE_SELL", f"Stale Position: {holding_days}d held, P&L={pnl_pct:+.1f}%"

    # ══ PARTIAL TP CHECK: TP1 hit → signal partial sell ══
    if not tp1_hit and close >= target_1:
        return "PARTIAL_TP1", f"TP1 Hit ({close:.0f} >= {target_1:.0f}) — Sell 50%"

    # ══ FULL EXIT: TP2 hit ══
    if close >= target_2:
        return "AUTO_TRADE_SELL", f"TP2 Hit ({close:.0f} >= {target_2:.0f}) — Full Exit"

    return None, ""


# ══════════════════════════════════════════════════════════════
# MAIN CONVICTION SCORING ENGINE
# ══════════════════════════════════════════════════════════════

def evaluate_signals(
    symbol: str,
    df: pd.DataFrame,
    config: dict,
    ihsg_data: dict = None,
    open_position: dict = None
):
    """
    Weighted Conviction Scoring Engine with proper exit signal generation.

    Args:
        symbol: Ticker symbol
        df: DataFrame with indicators calculated
        config: System configuration
        ihsg_data: IHSG macro data
        open_position: Current position dict if held (for exit evaluation)

    Returns:
        (signal_dict, status_summary, reason_string)
    """
    valid_df = df.dropna(subset=['Close'])
    if valid_df.empty:
        return {'type': None, 'score': 0, 'data': {}}, None, "No valid price data"

    last = valid_df.iloc[-1]
    close = last['Close']

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
        final_conviction += 0.3  # Bonus for above VWAP

    # ── Multi-Timeframe Confirmation ──
    weekly_trend = get_weekly_trend(df)

    # ── ATR-based Risk Management Targets ──
    ind_cfg = config.get('indicators', {})
    atr = last.get(f"ATRr_{ind_cfg.get('atr_period', 14)}", last.get('ATR_14', close * 0.02))
    support = last.get('Support_Level', close - atr * 2)
    resistance = last.get('Resistance_Level', close + atr * 2)

    stop_loss = round(max(support, close - atr * 2), 0)
    target_1 = round(min(resistance, close + atr * 2), 0)
    target_2 = round(close + atr * 4, 0)

    bee_score, bee_label = calculate_bee_flow(df)

    status_summary = {
        'symbol': symbol,
        'close': close,
        'conviction': round(final_conviction, 1),
        'wyckoff_phase': detect_wyckoff_phase(df),
        'bee_score': bee_score,
        'bee_label': bee_label,
        'stop_loss': stop_loss,
        'target_1': target_1,
        'target_2': target_2,
        'atr': atr,
        'weekly_trend': weekly_trend,
        'vwap': vwap,
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
    exec_cfg = config.get('execution', {})
    signal_type = None

    # Buy Signals — with multi-timeframe gate
    if final_conviction >= exec_cfg.get('auto_trade_threshold', 6.5):
        if weekly_trend != "BEARISH":
            signal_type = "AUTO_TRADE_BUY"
        else:
            logger.info(f"[{symbol}] AUTO_BUY blocked: Weekly trend is BEARISH (score={final_conviction:.1f})")
            signal_type = "ALERT_ONLY_BUY"  # Downgrade to alert
    elif final_conviction >= exec_cfg.get('alert_only_threshold', 4.5):
        signal_type = "ALERT_ONLY_BUY"

    # Sell Signals (conviction-based for stocks NOT in portfolio)
    if signal_type is None:
        if final_conviction <= exec_cfg.get('exit_threshold', 3.0):
            signal_type = "AUTO_TRADE_SELL"

        # Wyckoff-based exit hint
        phase = detect_wyckoff_phase(df)
        if "DISTRIBUTION" in phase or "UPTHRUST" in phase:
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
    phase = detect_wyckoff_phase(df)
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
