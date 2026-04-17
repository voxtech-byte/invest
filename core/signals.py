import pandas as pd
import numpy as np
from datetime import datetime
from typing import Any, Dict
from logger import get_logger
from core.utils import TIMEZONE

logger = get_logger(__name__)

def detect_wyckoff_phase(df: pd.DataFrame) -> str:
    """
    Detect market cycle phase based on Wyckoff theory proxies.
    Accumulation, Markup, Distribution, Markdown.
    """
    if len(df) < 50: return "UNKNOWN"
    last = df.iloc[-1]
    prev_20 = df.iloc[-20]
    ma50 = last.get('SMA_50', last.get('SMA_50', 0)) # Fallback
    ma200 = last.get('SMA_200', 0)
    close = last['Close']
    
    if close > ma50 > ma200 and ma50 > prev_20.get('SMA_50', 0):
        return "MARKUP (Strong Trend)"
    if close < ma50 < ma200:
        return "MARKDOWN (Stay Away)"
    if ma50 < ma200 and abs(close - ma50)/ma50 < 0.05:
        return "ACCUMULATION (Smart Money Buying)"
    if close > ma200 and abs(close - ma50)/ma50 < 0.05 and last.get('Pct_Change_5D', 0) < 0:
        return "DISTRIBUTION (Institutions Selling)"
    return "CONSOLIDATION (Neutral)"

def calculate_bee_flow(df: pd.DataFrame) -> tuple[float, str]:
    """
    Simulate 'Broker Intelligence' (BEE-FLOW) using VPA proxies.
    """
    if len(df) < 20: return 0.0, "NEUTRAL"
    last = df.iloc[-1]
    pvt = last.get('PVT', 0)
    cmf = last.get('CMF_20', 0)
    vol_ratio = last['Volume'] / last['Vol_Avg'] if last.get('Vol_Avg', 0) > 0 else 1.0
    
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

def evaluate_signals(symbol: str, df: pd.DataFrame, config: dict, ihsg_data: dict = None):
    """
    Weighted Conviction Scoring Engine.
    """
    valid_df = df.dropna(subset=['Close'])
    if valid_df.empty: return None, None, "No valid price data"
    
    last = valid_df.iloc[-1]
    close = last['Close']
    
    # Scoring Weights
    sm_score = _score_smart_money(df, last, config)
    trend_score = _score_trend(last, config)
    rsi_score = _score_rsi_phase(df, last, config)
    vol_score = _score_volatility(last, config)
    macro_score = _score_macro(ihsg_data)
    
    final_conviction = sm_score + trend_score + rsi_score + vol_score + macro_score
    
    # Signal Detection
    exec_cfg = config.get('execution', {})
    signal_type = None
    if final_conviction >= exec_cfg.get('auto_trade_threshold', 6.5):
        signal_type = "AUTO_TRADE_BUY"
    elif final_conviction >= exec_cfg.get('alert_only_threshold', 4.5):
        signal_type = "ALERT_ONLY_BUY"
        
    if not signal_type:
        return None, None, f"Conviction too low ({final_conviction:.1f})"

    # Support / Resistance & Risk Management Targets
    atr = last.get(f"ATRr_{config['indicators']['atr_period']}", close * 0.02)
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
        'atr': atr
    }
    
    return {
        'type': signal_type,
        'score': final_conviction,
        'data': status_summary
    }, status_summary, "SIGNAL_DETECTED"

def _score_smart_money(df, last, config):
    vol_ratio = last['Volume'] / last['Vol_Avg'] if last['Vol_Avg'] > 0 else 1.0
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
    return 0.05 * 10 if ihsg and ihsg.get('trend') == 'BULLISH' else 0.0
