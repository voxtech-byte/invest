import os
import json
import asyncio
import time
from datetime import datetime, timedelta
from typing import Any

import pytz
import yfinance as yf
import pandas as pd
import pandas_ta as ta
from telegram import Bot
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import mplfinance as mpf
import requests

from mock_broker import MockBroker
from google_sheets_logger import GoogleSheetsLogger
from dotenv import load_dotenv
from logger import get_logger

# ============================================================
# INITIALIZATION
# ============================================================

load_dotenv()
logger = get_logger(__name__)

TIMEZONE = pytz.timezone('Asia/Jakarta')
STATE_FILE = "last_signals.json"
FORWARD_LOG_FILE = "forward_test.csv"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ============================================================
# UTILITIES
# ============================================================

def load_config() -> dict[str, Any]:
    with open("config.json", "r") as f:
        return json.load(f)

def get_last_state() -> dict[str, Any]:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load state file: {e}")
            pass
    return {}

def save_state(state: dict[str, Any]) -> None:
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=4)
    except Exception as e:
        logger.error(f"Failed to save state: {e}", exc_info=True)

def format_rp(n: float) -> str:
    return f"Rp {n:,.0f}".replace(',', '.')

def format_vol(n: float) -> str:
    return f"{n/1_000_000:.1f}M" if n >= 1e6 else f"{n/1_000:.1f}K"

# ============================================================
# CINEMATIC UI HELPERS
# ============================================================

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

# ============================================================
# DATA FETCHING
# ============================================================

# ============================================================
# DATA FETCHING (V11 PRO: MULTI-SOURCE FALLBACK)
# ============================================================

def _fetch_yfinance(symbol: str, config: dict[str, Any], period: str = "1y") -> pd.DataFrame | None:
    """Primary data source: Yahoo Finance"""
    try:
        stock = yf.Ticker(symbol)
        df = stock.history(period=period, interval="1d")
        if df.empty:
            return None
        
        # Standardize columns
        df = df[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
        
        # Carry over fundamentals if available
        try:
            info = stock.info
            df.attrs['pe_ratio'] = info.get('trailingPE')
            df.attrs['pbv'] = info.get('priceToBook')
            df.attrs['market_cap'] = info.get('marketCap')
        except:
            pass
            
        return df
    except Exception as e:
        logger.debug(f"[{symbol}] yfinance error: {e}")
        return None

def _fetch_alphavantage(symbol: str, config: dict[str, Any]) -> pd.DataFrame | None:
    """Fallback 1: Alpha Vantage"""
    api_keys = config.get('api_keys', {})
    key = api_keys.get('alpha_vantage')
    if not key or key == "YOUR_KEY":
        return None
        
    try:
        url = f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol={symbol}&apikey={key}&outputsize=compact"
        response = requests.get(url, timeout=10)
        data = response.json()
        
        time_series = data.get("Time Series (Daily)")
        if not time_series:
            logger.debug(f"[{symbol}] Alpha Vantage returned no time series: {data.get('Note', 'Unknown error')}")
            return None
            
        df = pd.DataFrame.from_dict(time_series, orient='index')
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()
        
        # Map columns
        df = df.rename(columns={
            "1. open": "Open",
            "2. high": "High",
            "3. low": "Low",
            "4. close": "Close",
            "5. volume": "Volume"
        })
        
        # Convert to float
        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            
        return df.tail(250) # Approx 1 year
    except Exception as e:
        logger.debug(f"[{symbol}] Alpha Vantage error: {e}")
        return None

def _fetch_fcsapi(symbol: str, config: dict[str, Any]) -> pd.DataFrame | None:
    """Fallback 2: FCS API"""
    api_keys = config.get('api_keys', {})
    key = api_keys.get('fcs_api')
    if not key or key == "YOUR_KEY":
        return None
        
    try:
        # FCS API ticker for IDX usually uses the same .JK or just ticker
        # We try the provided symbol
        url = f"https://fcsapi.com/api-v3/stock/history?symbol={symbol}&period=1d&access_key={key}"
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if not data.get('status'):
            logger.debug(f"[{symbol}] FCS API error: {data.get('msg')}")
            return None
            
        history = data.get('response', [])
        if not history:
            return None
            
        df = pd.DataFrame(history)
        # Map: o, h, l, c, v, t (unix)
        df = df.rename(columns={
            'o': 'Open', 'h': 'High', 'l': 'Low', 'c': 'Close', 'v': 'Volume', 't': 'Date'
        })
        
        df['Date'] = pd.to_datetime(df['Date'], unit='s')
        df.set_index('Date', inplace=True)
        df = df.sort_index()
        
        # Convert to float
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            
        return df
    except Exception as e:
        logger.debug(f"[{symbol}] FCS API error: {e}")
        return None

def fetch_data(symbol: str, config: dict[str, Any]) -> pd.DataFrame | None:
    """Multi-source data fetch with fallback prioritization."""
    logger.debug(f"[{symbol}] Fetching data...")
    
    # 1. Primary: yfinance
    df = _fetch_yfinance(symbol, config)
    source = "yfinance"
    
    # 2. Fallback 1: Alpha Vantage
    if df is None or df.empty:
        logger.warning(f"[{symbol}] yfinance failed. Switching to Alpha Vantage...")
        df = _fetch_alphavantage(symbol, config)
        source = "Alpha Vantage"
        
    # 3. Fallback 2: FCS API
    if df is None or df.empty:
        logger.warning(f"[{symbol}] Alpha Vantage failed. Switching to FCS API...")
        df = _fetch_fcsapi(symbol, config)
        source = "FCS API"
        
    if df is None or df.empty:
        logger.error(f"[{symbol}] All data sources failed!")
        return None
        
    logger.info(f"[{symbol}] Data successfully fetched via {source}")
    
    # Post-processing: Add Peak Price and attrs
    try:
        lookback = config['signals']['price_peak_lookback_days']
        if len(df) >= lookback:
            df['Peak_Price'] = df['High'].rolling(window=lookback, min_periods=1).max()
        else:
            df['Peak_Price'] = df['High'].rolling(window=len(df), min_periods=1).max()
        
        # Ensure metadata attributes exist
        if not hasattr(df, 'attrs'): df.attrs = {}
        for attr in ['pe_ratio', 'pbv', 'market_cap']:
            if attr not in df.attrs: df.attrs[attr] = None
            
        return df
    except Exception as e:
        logger.error(f"[{symbol}] Post-fetch processing error: {e}")
        return None

def fetch_ihsg(config: dict[str, Any]) -> dict[str, Any] | None:
    """Fetch IHSG index data with fallback support."""
    idx_symbol = config.get('macro', {}).get('index_symbol', '^JKSE')
    
    df = fetch_data(idx_symbol, config)
    if df is None or len(df) < 2:
        return None
        
    try:
        # Clean NaN rows
        df = df.dropna(subset=['Close'])
        
        last = df.iloc[-1]
        prev = df.iloc[-2]
        pct = ((last['Close'] - prev['Close']) / prev['Close']) * 100
        
        # Regime Detection
        ma200_val = df['Close'].rolling(200).mean().iloc[-1] if len(df) >= 200 else df['Close'].mean()
        ma50_val = df['Close'].rolling(50).mean().iloc[-1] if len(df) >= 50 else df['Close'].mean()
        
        # ADX approximation
        df.ta.adx(length=14, append=True)
        adx_col = [c for c in df.columns if c.startswith('ADX_')]
        adx_val = float(df[adx_col[0]].iloc[-1]) if adx_col and not pd.isna(df[adx_col[0]].iloc[-1]) else 15.0
        
        above_ma200 = last['Close'] > ma200_val
        regime_cfg = config.get('regime', {})
        adx_threshold = regime_cfg.get('min_adx_trending', 20)
        
        if above_ma200 and adx_val > adx_threshold:
            regime = "TRENDING_BULL"
            regime_label = "Trending/Bullish — Trend-follow setups ON"
        elif above_ma200 and adx_val <= adx_threshold:
            regime = "RANGE_BULL"
            regime_label = "Range-bound/Bullish — Reduce size, mean-revert setups"
        elif not above_ma200 and adx_val > adx_threshold:
            regime = "TRENDING_BEAR"
            regime_label = "Trending/Bearish — Defensive, short bias"
        else:
            regime = "CHOPPY"
            regime_label = f"Choppy — Reduce position size by {regime_cfg.get('choppy_reduce_pct', 30)}%"
        
        trend = "BULLISH" if above_ma200 else "BEARISH"
        
        return {
            'close': last['Close'],
            'pct_1d': pct,
            'trend': trend,
            'ma200': ma200_val,
            'ma50': ma50_val,
            'adx': adx_val,
            'regime': regime,
            'regime_label': regime_label
        }
    except Exception as e:
        logger.error(f"[IHSG] Process error: {e}")
        return None

def fetch_weekly_trend(symbol: str) -> dict[str, Any] | None:
    """Fetch weekly timeframe to validate daily signals (multi-TF confirmation)"""
    try:
        stock = yf.Ticker(symbol)
        df_w = stock.history(period="2y", interval="1wk")
        if df_w.empty or len(df_w) < 50:
            return None
        
        df_w.ta.sma(length=40, append=True)  # ~200 daily MA equivalent
        ma_col = [c for c in df_w.columns if c.startswith('SMA_40')]
        if not ma_col:
            return None
        
        last = df_w.iloc[-1]
        weekly_ma = last[ma_col[0]]
        
        return {
            'weekly_close': last['Close'],
            'weekly_ma200eq': weekly_ma,
            'weekly_bullish': last['Close'] > weekly_ma if not pd.isna(weekly_ma) else None
        }
    except Exception as e:
        logger.debug(f"[{symbol}] Weekly fetch error: {e}")
        return None

# ============================================================
# TECHNICAL INDICATORS
# ============================================================

def calculate_indicators(df: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    ind_cfg = config['indicators']
    df = df.sort_index()
    
    # RSI
    df.ta.rsi(length=ind_cfg['rsi_length'], append=True)
    df['Pct_Change_1D'] = df['Close'].pct_change() * 100
    df['Pct_Change_5D'] = df['Close'].pct_change(periods=5) * 100
    
    # Drop from Peak
    df['Drop_From_Peak_Pct'] = ((df['Peak_Price'] - df['Close']) / df['Peak_Price']) * 100
    
    # Moving Averages
    df.ta.sma(length=ind_cfg['ma_short'], append=True)
    df.ta.sma(length=ind_cfg['ma_long'], append=True)
    
    # MACD
    df.ta.macd(fast=ind_cfg['macd_fast'], slow=ind_cfg['macd_slow'], signal=ind_cfg['macd_signal'], append=True)
    
    # Bollinger Bands & Squeeze Logic
    df.ta.bbands(length=ind_cfg['bb_period'], std=ind_cfg['bb_std'], append=True)
    
    # Robust column discovery for BB (handles 2.0 vs 2 naming issues)
    bbu_col = [c for c in df.columns if c.startswith(f"BBU_{ind_cfg['bb_period']}")]
    bbl_col = [c for c in df.columns if c.startswith(f"BBL_{ind_cfg['bb_period']}")]
    bbm_col = [c for c in df.columns if c.startswith(f"BBM_{ind_cfg['bb_period']}")]
    
    if bbu_col and bbl_col and bbm_col:
        bb_upper = df[bbu_col[0]]
        bb_lower = df[bbl_col[0]]
        bb_mid = df[bbm_col[0]]
        df['BB_Width'] = (bb_upper - bb_lower) / bb_mid
    else:
        df['BB_Width'] = 0.0 # Fallback
    
    # Advanced Intelligence Indicators (BEE-FLOW Proxy)
    df.ta.pvt(append=True) # Price Volume Trend (Alternative to VPT)
    df.ta.obv(append=True) # On-Balance Volume
    df.ta.cmf(length=20, append=True) # Chaikin Money Flow
    
    # ATR (Average True Range) — for SL/TP calculation
    df.ta.atr(length=ind_cfg['atr_period'], append=True)
    
    # Volume Average
    df['Vol_Avg'] = df['Volume'].rolling(window=ind_cfg['volume_avg_period']).mean()
    
    # ADX (Average Directional Index) - for trend strength
    df.ta.adx(length=14, append=True)
    
    # Support & Resistance (High/Low dari N hari terakhir)
    sr_days = ind_cfg['sr_lookback_days']
    df['Support_Level'] = df['Low'].rolling(window=sr_days, min_periods=1).min()
    df['Resistance_Level'] = df['High'].rolling(window=sr_days, min_periods=1).max()
    
    return df

def is_downtrend(df: pd.DataFrame, config: dict[str, Any]) -> bool:
    days = config['signals']['ignore_downtrend_days']
    if len(df) < days: return False
    
    ma200_col = f"SMA_{config['indicators']['ma_long']}"
    for i in range(1, days + 1):
        row = df.iloc[-i]
        if row['Close'] >= row[ma200_col]:
            return False
    return True

def check_cooldown(symbol: str, signal_type: str, state: dict[str, Any], config: dict[str, Any]) -> bool:
    now = datetime.now(TIMEZONE)
    if symbol in state:
        last_sig = state[symbol].get('signal')
        last_time_str = state[symbol].get('time')
        if last_sig == signal_type and last_time_str:
            last_time = datetime.fromisoformat(last_time_str)
            if now - last_time < timedelta(hours=config['signals']['signal_cooldown_hours']):
                return True
    return False

def detect_candles(df: pd.DataFrame) -> str:
    if len(df) < 2: return ""
    
    last = df.iloc[-1]
    prev = df.iloc[-2]
    
    body = abs(last['Close'] - last['Open'])
    upper_shade = last['High'] - max(last['Close'], last['Open'])
    lower_shade = min(last['Close'], last['Open']) - last['Low']
    total_range = last['High'] - last['Low']
    
    patterns = []
    
    if total_range > 0 and body / total_range < 0.1:
        patterns.append("Doji")
    if lower_shade > (2 * body) and upper_shade < (0.5 * body) and total_range > 0:
        patterns.append("Hammer")
    
    prev_body = prev['Close'] - prev['Open']
    if prev_body < 0 and (last['Close'] > prev['Open']) and (last['Open'] < prev['Close']):
        patterns.append("Bullish Engulfing")
        
    return ", ".join(patterns) if patterns else ""

# ============================================================
# MARKET INTELLIGENCE ENGINE
# ============================================================

def detect_wyckoff_phase(df: pd.DataFrame) -> str:
    """
    Detect the market cycle phase based on Wyckoff theory proxies.
    Accumulation, Markup, Distribution, Markdown.
    """
    if len(df) < 50: return "UNKNOWN"
    
    last = df.iloc[-1]
    prev_20 = df.iloc[-20]
    
    ma50 = last.get('SMA_50', 0)
    ma200 = last.get('SMA_200', 0)
    close = last['Close']
    
    # 1. MARKUP (Uptrend)
    if close > ma50 > ma200 and ma50 > prev_20.get('SMA_50', 0):
        return "MARKUP (Strong Trend)"
    
    # 2. MARKDOWN (Downtrend)
    if close < ma50 < ma200:
        return "MARKDOWN (Stay Away)"
        
    # 3. ACCUMULATION (Sideways at bottom)
    if ma50 < ma200 and abs(close - ma50)/ma50 < 0.05:
        return "ACCUMULATION (Smart Money Buying)"
        
    # 4. DISTRIBUTION (Sideways at top)
    if close > ma200 and abs(close - ma50)/ma50 < 0.05 and last['Pct_Change_5D'] < 0:
        return "DISTRIBUTION (Institutions Selling)"
        
    return "CONSOLIDATION (Neutral)"

def calculate_bee_flow(df: pd.DataFrame) -> tuple[float, str]:
    """
    Simulate 'Broker Intelligence' (BEE-FLOW) using VPA.
    Returns Score (0-10) and Label.
    """
    if len(df) < 20: return 0.0, "NEUTRAL"
    
    last = df.iloc[-1]
    pvt = last.get('PVT', 0)
    cmf = last.get('CMF_20', 0)
    vol_ratio = last.get('Vol_Avg', 1) 
    vol_ratio = last['Volume'] / vol_ratio if vol_ratio > 0 else 1
    
    score = 0
    
    # CMF: Institutional pressure (Positive is good)
    if cmf > 0.2: score += 4
    elif cmf > 0: score += 2
    
    # PVT: Trend strength corroborated by volume
    if pvt > df['PVT'].iloc[-5:].mean(): score += 3
    
    # Volume/Price divergence check
    if last['Pct_Change_1D'] > 0 and vol_ratio > 1.5:
        score += 3 # Professional Accumulation
    elif last['Pct_Change_1D'] < 0 and vol_ratio > 1.5:
        score -= 4 # Institutional Dumping
        
    # Normalize score 0-10
    final_score = float(max(0, min(10, score)))
    
    if final_score >= 8: label = "HIGH ACCUMULATION (BIG BEE)"
    elif final_score >= 6: label = "MILD ACCUMULATION"
    elif final_score <= 3: label = "DISTRIBUTION (EXITING)"
    else: label = "NEUTRAL"
    
    return final_score, label

def get_volume_context(pct_1d: float, vol_ratio: float) -> str:
    """Determine volume pattern meaning"""
    if pct_1d > 0 and vol_ratio >= 1.5:
        return "Strong Accumulation (Price ↑ + Volume ↑↑)"
    elif pct_1d > 0 and vol_ratio >= 1.0:
        return "Healthy Buying (Price ↑ + Normal Vol)"
    elif pct_1d > 0 and vol_ratio < 1.0:
        return "Weak Rally (Price ↑ + Low Vol) ⚠️"
    elif pct_1d < 0 and vol_ratio >= 1.5:
        return "Heavy Distribution (Price ↓ + Volume ↑↑) ⚠️"
    elif pct_1d < 0 and vol_ratio >= 1.0:
        return "Selling Pressure (Price ↓ + Normal Vol)"
    elif pct_1d < 0 and vol_ratio < 1.0:
        return "Quiet Pullback (Price ↓ + Low Vol)"
    else:
        return "Sideways / No Clear Pattern"

# ============================================================
# V9 PRO: POSITION SIZER & RISK CONTROLS
# ============================================================

def calculate_position_size(price: float, stop_loss: float, conviction_score: float, config: dict[str, Any]) -> tuple[int, float, float]:
    """
    Calculate lot size based on risk-per-trade tiers driven by conviction score.
    """
    portfolio = config.get('portfolio', {})
    initial_equity = portfolio.get('initial_equity', 50000000)
    
    if conviction_score >= 9.0:
        risk_pct = 4.0
    elif conviction_score >= 7.5:
        risk_pct = 2.5
    elif conviction_score >= 6.5:
        risk_pct = 1.5
    elif conviction_score >= 4.5:
        risk_pct = 0.75
    else:
        return 0, 0.0, 0.0
        
    risk_amount = initial_equity * (risk_pct / 100)
    
    risk_per_share = abs(price - stop_loss)
    if risk_per_share <= 0:
        risk_per_share = price * 0.05
        
    shares = int(risk_amount / risk_per_share)
    lot = (shares // 100) * 100
    position_value = lot * price
    
    return lot, position_value, risk_pct

def check_sector_exposure(symbol: str, active_signals: list[str], config: dict[str, Any]) -> list[str]:
    """Check if adding this symbol would breach sector exposure limits"""
    sectors = config.get('sectors', {})
    portfolio = config.get('portfolio', {})
    max_sector_pct = portfolio.get('max_sector_exposure_pct', 30)
    
    current_sector = sectors.get(symbol, 'Unknown')
    
    sector_count = {}
    for sig in active_signals:
        sig_sector = sectors.get(sig, 'Unknown')
        sector_count[sig_sector] = sector_count.get(sig_sector, 0) + 1
    
    same_sector_count = sector_count.get(current_sector, 0)
    total_active = len(active_signals)
    
    warnings = []
    
    if total_active > 0:
        sector_pct = (same_sector_count / max(total_active, 1)) * 100
        if sector_pct >= max_sector_pct:
            warnings.append(f"Sector {current_sector} exposure > {max_sector_pct}%")
    
    return warnings

def health_check(df: pd.DataFrame, config: dict[str, Any]) -> dict[str, Any]:
    """Pre-signal quality control: liquidity, volume, gap filtering"""
    health = config.get('health', {})
    min_avg_vol = health.get('min_avg_volume', 100000)
    min_avg_value = health.get('min_avg_value_rp', 10000000000)
    
    result = {'liquidity': 'OK', 'news_risk': 'LOW', 'warnings': []}
    
    if len(df) < 20:
        result['liquidity'] = 'INSUFFICIENT_DATA'
        result['warnings'].append("Less than 20 days data")
        return result
    
    avg_vol = df['Volume'].tail(20).mean()
    if avg_vol < min_avg_vol:
        result['liquidity'] = 'LOW'
        result['warnings'].append(f"Avg volume ({avg_vol:,.0f}) < {min_avg_vol:,.0f}")
    
    avg_value = (df['Close'] * df['Volume']).tail(20).mean()
    if avg_value < min_avg_value:
        result['liquidity'] = 'THIN'
        result['warnings'].append(f"Avg value Rp {avg_value:,.0f} < threshold")
    
    last_gap = abs(df['Open'].iloc[-1] - df['Close'].iloc[-2]) / df['Close'].iloc[-2] * 100
    if last_gap > 5:
        result['warnings'].append(f"Large gap detected ({last_gap:.1f}%)")
    
    return result

def run_backtest_stats(symbol: str, df: pd.DataFrame, config: dict[str, Any]) -> dict[str, Any] | None:
    bt_cfg = config.get('backtest', {})
    tp_mult = bt_cfg.get('tp_atr_multiplier', 2.0)
    sl_mult = bt_cfg.get('sl_atr_multiplier', 2.0)
    ind_cfg = config['indicators']
    
    if len(df) < 200:
        return None
    
    rsi_col = f"RSI_{ind_cfg['rsi_length']}"
    ma200_col = f"SMA_{ind_cfg['ma_long']}"
    atr_col_list = [c for c in df.columns if c.startswith('ATR')]
    atr_col = atr_col_list[0] if atr_col_list else None
    
    if rsi_col not in df.columns or ma200_col not in df.columns or not atr_col:
        return None
    
    wins = 0
    losses = 0
    total_r_won = 0.0
    total_r_lost = 0.0
    max_dd = 0.0
    equity_curve = [0.0]
    
    for i in range(200, len(df) - 10):
        row = df.iloc[i]
        
        rsi = row.get(rsi_col)
        ma200 = row.get(ma200_col)
        close = row['Close']
        atr = row.get(atr_col, close * 0.02)
        
        if pd.isna(rsi) or pd.isna(ma200) or pd.isna(atr) or atr <= 0:
            continue
        
        if rsi < 40 and close > ma200:
            entry = close
            sl = entry - atr * sl_mult
            tp = entry + atr * tp_mult
            
            for j in range(i + 1, min(i + 15, len(df))):
                future_row = df.iloc[j]
                high = future_row['High']
                low = future_row['Low']
                
                if low <= sl:
                    losses += 1
                    r_lost = abs(entry - sl) / atr
                    total_r_lost += r_lost
                    equity_curve.append(equity_curve[-1] - r_lost)
                    break
                elif high >= tp:
                    wins += 1
                    r_won = abs(tp - entry) / atr
                    total_r_won += r_won
                    equity_curve.append(equity_curve[-1] + r_won)
                    break
    
    total_trades = wins + losses
    if total_trades == 0:
        return None
    
    winrate = (wins / total_trades) * 100
    profit_factor = total_r_won / total_r_lost if total_r_lost > 0 else 999
    
    peak = 0.0
    for val in equity_curve:
        if val > peak:
            peak = val
        dd = peak - val
        if dd > max_dd:
            max_dd = dd
    
    return {
        'winrate': round(winrate, 1),
        'profit_factor': round(profit_factor, 2),
        'max_drawdown_r': round(max_dd, 1),
        'total_trades': total_trades,
        'wins': wins,
        'losses': losses
    }

def log_forward_test(symbol: str, signal_data: dict[str, Any], lot: int, position_value: float, health: dict[str, Any], regime: str) -> None:
    s = signal_data['data']
    try:
        file_exists = os.path.isfile(FORWARD_LOG_FILE)
        with open(FORWARD_LOG_FILE, 'a') as f:
            if not file_exists:
                f.write("Date,Symbol,Direction,Confidence,Score,Price,StopLoss,TP1,TP2,Lot,Value,PE,PBV,Phase,Regime,Liquidity\n")
            
            date_str = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M")
            pe = f"{s.get('pe_ratio', 0):.2f}" if s.get('pe_ratio') else "N/A"
            pbv = f"{s.get('pbv', 0):.2f}" if s.get('pbv') else "N/A"
            liq = health.get('liquidity', 'N/A') if health else 'N/A'
            reg = regime if regime else 'N/A'
            
            row = f"{date_str},{symbol},{signal_data['direction']},{signal_data['confidence']},{signal_data['score']:.1f},{s['close']},{s['stop_loss']},{s['target_1']},{s['target_2']},{lot},{position_value},{pe},{pbv},{s.get('wyckoff_phase', 'N/A')},{reg},{liq}\n"
            f.write(row)
    except Exception as e:
        logger.error(f"[{symbol}] Failed to log forward test: {e}")

# ============================================================
# V11 PRO: REFACTORED SCORING LOGIC
# ============================================================

def _score_smart_money(df: pd.DataFrame, last_row: pd.Series, config: dict[str, Any]) -> float:
    """Smart Money Proxy (35%)"""
    vol_ratio = last_row['Volume'] / last_row['Vol_Avg'] if last_row['Vol_Avg'] > 0 else 1.0
    cmf_cols = [c for c in df.columns if c.startswith('CMF_')]
    cmf = last_row[cmf_cols[0]] if cmf_cols else 0.0
    pvt_cols = [c for c in df.columns if c.startswith('PVT')]
    pvt = last_row[pvt_cols[0]] if pvt_cols else 0.0
    
    score = 0.0
    if vol_ratio > 2.5: score += 0.4
    elif vol_ratio > 1.5: score += 0.2
    if cmf > 0: score += 0.3
    if pvt_cols and pvt > df[pvt_cols[0]].tail(5).mean(): score += 0.3
    
    return 0.35 * min(1.0, score) * 10

def _score_trend(last_row: pd.Series, config: dict[str, Any]) -> float:
    """Trend Confirmation (25%)"""
    ma200_col = f"SMA_{config['indicators']['ma_long']}"
    adx_cols = [c for c in last_row.index if c.startswith('ADX_')]
    
    ma200 = last_row.get(ma200_col, 0.0)
    adx = last_row[adx_cols[0]] if adx_cols else 0.0
    
    score = 0.0
    if last_row['Close'] > ma200: score += 0.5
    if adx > 30: score += 0.5
    elif adx > 20: score += 0.2
    
    return 0.25 * min(1.0, score) * 10

def _score_rsi_phase(df: pd.DataFrame, last_row: pd.Series, config: dict[str, Any]) -> float:
    """RSI/Phase Alignment (20%)"""
    rsi_col = f"RSI_{config['indicators']['rsi_length']}"
    rsi = last_row.get(rsi_col, 50.0)
    wyckoff_phase = detect_wyckoff_phase(df)
    
    score = 0.0
    if 45 <= rsi <= 75: score += 0.5
    if "MARKUP" in wyckoff_phase or "ACCUMULATION" in wyckoff_phase: score += 0.5
    
    return 0.20 * min(1.0, score) * 10

def _score_volatility(last_row: pd.Series, atr: float, config: dict[str, Any]) -> float:
    """Volatility Check (15%)"""
    atr_pct = (atr / last_row['Close']) * 100 if last_row['Close'] > 0 else 5.0
    
    score = 0.0
    if atr_pct < 3.0: score = 1.0
    elif atr_pct < 5.0: score = 0.5
    
    return 0.15 * min(1.0, score) * 10

def _score_macro(ihsg_data: dict[str, Any] | None, config: dict[str, Any]) -> float:
    """Macro Regime Fit (5%)"""
    score = 0.0
    if ihsg_data and ihsg_data.get('trend') == 'BULLISH':
        score = 1.0
    return 0.05 * min(1.0, score) * 10

def evaluate_signals(symbol: str, df: pd.DataFrame, config: dict[str, Any], ihsg_data: dict[str, Any] | None = None) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str]:
    """V11 Pro: Refactored Weighted Conviction Scoring Engine"""
    valid_df = df.dropna(subset=['Close'])
    if valid_df.empty:
        return None, None, "No valid price data"
    
    last_row = valid_df.iloc[-1]
    close = last_row['Close']
    
    try:
        atr_col = f"ATRr_{config['indicators']['atr_period']}"
        atr = last_row.get(atr_col, close * 0.02)
        if pd.isna(atr): atr = close * 0.02
        
        # Scoring Modules
        sm_weight = _score_smart_money(df, last_row, config)
        trend_weight = _score_trend(last_row, config)
        rp_weight = _score_rsi_phase(df, last_row, config)
        vol_weight = _score_volatility(last_row, atr, config)
        macro_weight = _score_macro(ihsg_data, config)
        
        final_conviction = sm_weight + trend_weight + rp_weight + vol_weight + macro_weight
        
    except Exception as e:
        logger.error(f"[{symbol}] Error parsing indicators: {e}")
        return None, None, "Indicators error"
    
    signal_type = None
    confidence = "LOW"
    
    if final_conviction >= config.get('execution', {}).get('auto_trade_threshold', 6.5):
        signal_type = "AUTO_TRADE_BUY"
        confidence = "HIGH" if final_conviction >= config.get('execution', {}).get('aggressive_threshold', 8.5) else "MEDIUM"
    elif final_conviction >= config.get('execution', {}).get('alert_only_threshold', 4.5):
        signal_type = "ALERT_ONLY_BUY"
        confidence = "LOW"
        
    if not signal_type:
        return None, None, f"Conviction too low ({final_conviction:.1f})"

    # Support / Resistance & Targets
    support = last_row.get('Support_Level', close - atr * 2)
    resistance = last_row.get('Resistance_Level', close + atr * 2)
    
    entry_low = round(close - atr * 0.3, 0)
    entry_high = round(close + atr * 0.3, 0)
    stop_loss = round(max(support, close - atr * 2), 0)
    target_1 = round(min(resistance, close + atr * 2), 0)
    target_2 = round(close + atr * 4, 0)
    
    risk_amount = close - stop_loss
    rrr_1 = round((target_1 - close) / risk_amount, 1) if risk_amount > 0 else 0
    rrr_2 = round((target_2 - close) / risk_amount, 1) if risk_amount > 0 else 0

    bee_score, bee_label = calculate_bee_flow(df)
    is_squeeze = (last_row.get('BB_Width', 1.0) < (df['BB_Width'].tail(20).mean() * 0.8))
    
    rsi_col = f"RSI_{config['indicators']['rsi_length']}"
    ma200_col = f"SMA_{config['indicators']['ma_long']}"

    status_summary = {
        'symbol': symbol,
        'close': close,
        'conviction': round(final_conviction, 1),
        'rsi': last_row.get(rsi_col, 50.0),
        'vol': last_row['Volume'],
        'vol_ratio': last_row['Volume'] / last_row['Vol_Avg'] if last_row['Vol_Avg'] > 0 else 1.0,
        'pct_1d': last_row.get('Pct_Change_1D', 0.0),
        'wyckoff_phase': detect_wyckoff_phase(df),
        'bee_score': bee_score,
        'bee_label': bee_label,
        'is_squeeze': is_squeeze,
        'atr': atr,
        'support': support,
        'resistance': resistance,
        'entry_low': entry_low,
        'entry_high': entry_high,
        'stop_loss': stop_loss,
        'target_1': target_1,
        'target_2': target_2,
        'rrr_1': rrr_1,
        'rrr_2': rrr_2,
        'trend': 'BULLISH' if close > last_row.get(ma200_col, float('inf')) else 'BEARISH',
        'pattern': detect_candles(df),
        'vol_context': get_volume_context(last_row.get('Pct_Change_1D', 0.0), last_row['Volume'] / last_row['Vol_Avg'] if last_row['Vol_Avg'] > 0 else 1.0),
        'pe_ratio': df.attrs.get('pe_ratio'),
        'pbv': df.attrs.get('pbv'),
        'market_cap': df.attrs.get('market_cap'),
    }
    
    result = {
        'type': signal_type,
        'confidence': confidence,
        'desc': f"Weighted Conviction: {final_conviction:.1f}/10",
        'direction': "BUY",
        'score': final_conviction,
        'layers': {'SmartMoney': sm_weight, 'Trend': trend_weight, 'RSI/Phase': rp_weight, 'Volatility': vol_weight, 'Macro': macro_weight},
        'data': status_summary
    }
    
    return result, status_summary, "SIGNAL_DETECTED"

# ============================================================
# V11 PRO: SAFETY METRICS & CONVICTION DECAY
# ============================================================

def apply_conviction_decay(entry_date: str, original_conviction: float, config: dict[str, Any]) -> float:
    """Reduce conviction score over time for aging positions."""
    days_held = (datetime.now(TIMEZONE) - datetime.fromisoformat(entry_date)).days
    if days_held <= 7:
        return original_conviction
        
    decay_rate = config.get('safety', {}).get('conviction_decay_per_day', 0.3)
    decay = (days_held - 7) * decay_rate
    return max(0.0, original_conviction - decay)


def check_safety_gates(broker: MockBroker, ihsg_data: dict[str, Any] | None, config: dict[str, Any]) -> tuple[bool, list[str]]:
    """V11 Pro: Comprehensive Safety Circuit Breakers"""
    safety = config.get('safety', {})
    portfolio = config.get('portfolio', {})
    
    is_safe = True
    warnings = []
    
    # 1. Daily Loss Limit
    daily_realized_loss = min(0.0, broker.get_daily_realized_pnl())
    max_loss_allowed = broker.get_balance() * (safety.get('daily_loss_limit_pct', 5.0) / 100)
    if abs(daily_realized_loss) >= max_loss_allowed:
        is_safe = False
        warnings.append(f"CIRCUIT BREAKER: Daily loss limit exceeded "
                        f"(Lost: {abs(daily_realized_loss):,.0f}, Max: {max_loss_allowed:,.0f})")
    
    # 2. Max Concurrent Positions
    max_pos = safety.get('max_concurrent_positions', portfolio.get('max_open_positions', 5))
    if len(broker.get_open_positions()) >= max_pos:
        is_safe = False
        warnings.append(f"MAX POSITIONS: Hit maximum concurrent positions ({max_pos})")
        
    # 3. Macro Circuit Breaker
    if ihsg_data and ihsg_data.get('pct_1d', 0.0) < -safety.get('circuit_breaker_ihsg_pct', 2.0):
        is_safe = False
        warnings.append(f"MACRO CRASH: IHSG dropped {ihsg_data['pct_1d']:.1f}%")
        
    return is_safe, warnings

# ============================================================
# CHART GENERATOR
# ============================================================

def generate_chart(symbol: str, df: pd.DataFrame, config: dict[str, Any]) -> str:
    df_plot = df.tail(30).copy()
    
    ind_cfg = config['indicators']
    ma_s_col = f"SMA_{ind_cfg['ma_short']}"
    ma_l_col = f"SMA_{ind_cfg['ma_long']}"
    rsi_col = f"RSI_{ind_cfg['rsi_length']}"
    macd_hist_col = f"MACDh_{ind_cfg['macd_fast']}_{ind_cfg['macd_slow']}_{ind_cfg['macd_signal']}"
    bb_lower_col = f"BBL_{ind_cfg['bb_period']}_{ind_cfg['bb_std']}"
    bb_upper_col = f"BBU_{ind_cfg['bb_period']}_{ind_cfg['bb_std']}"
    
    apds = []
    
    if ma_s_col in df_plot.columns:
        apds.append(mpf.make_addplot(df_plot[ma_s_col], color='dodgerblue', width=1.0))
    if ma_l_col in df_plot.columns:
        apds.append(mpf.make_addplot(df_plot[ma_l_col], color='red', width=1.2))
    
    if bb_upper_col in df_plot.columns and bb_lower_col in df_plot.columns:
        apds.append(mpf.make_addplot(df_plot[bb_upper_col], color='gray', width=0.5, linestyle='dashed'))
        apds.append(mpf.make_addplot(df_plot[bb_lower_col], color='gray', width=0.5, linestyle='dashed'))
    
    if rsi_col in df_plot.columns:
        apds.append(mpf.make_addplot(df_plot[rsi_col], panel=1, color='purple', width=0.8, secondary_y=False))
    
    if macd_hist_col in df_plot.columns:
        colors = ['green' if v >= 0 else 'red' for v in df_plot[macd_hist_col].fillna(0)]
        apds.append(mpf.make_addplot(df_plot[macd_hist_col], panel=2, type='bar', color=colors, secondary_y=False))

    file_path = f"{symbol.split('.')[0]}_chart.png"
    s = mpf.make_mpf_style(base_mpf_style='charles', gridstyle='', facecolor='#f5f5f5')
    
    mpf.plot(df_plot, type='candle', style=s, 
             addplot=apds if apds else None,
             title=f"\n{symbol} — Technical Analysis",
             volume=True, 
             savefig=file_path,
             figratio=(14, 10),
             tight_layout=True)
             
    return file_path

# ============================================================
# FORMATTERS
# ============================================================

def format_alert(signal_data: dict[str, Any], extra: dict[str, Any] | None = None) -> str:
    s = signal_data['data']
    conf = signal_data['confidence']
    desc = signal_data['desc']
    direction = signal_data['direction']
    score = signal_data['score']
    layers = signal_data['layers']
    
    ext = extra or {}
    lot = ext.get('lot', 0)
    pos_value = ext.get('position_value', 0)
    health = ext.get('health', {})
    regime = ext.get('regime', 'N/A')
    regime_label = ext.get('regime_label', '')
    weekly_ok = ext.get('weekly_bullish')
    bt_stats = ext.get('backtest_stats')
    sector_warnings = ext.get('sector_warnings', [])
    
    sym_name = s['symbol'].split('.')[0]
    narrative = generate_narrative(s)
    
    sig_type = signal_data.get('type', '')
    exec_status = ext.get('exec_status', 'SIGNAL')
    
    if sig_type == "AUTO_TRADE_BUY":
        if exec_status == "EXECUTED":
            alert_title = "🤖 [AUTO-TRADE EXECUTED]"
        elif exec_status == "BLOCKED":
            alert_title = "🛡️ [AUTO-TRADE BLOCKED]"
        else:
            alert_title = "🚨 [QUANT BUY ALERT]"
    elif sig_type == "ALERT_ONLY_BUY":
        alert_title = "👀 [ALERT ONLY — Manual Review]"
    elif direction == "SELL":
        alert_title = "⚠️ [DISTRIBUTION WARNING]" if conf == "HIGH" else "📉 [EXIT PROTOCOL]"
    else:
        alert_title = "📊 [SIGNAL DETECTED]"
        
    msg = "┏━━━━━━━━━━━━━━━━━━━━┓\n"
    msg += f"*{alert_title}*\n"
    msg += f"Core: Quant Alpha Engine V11 Pro\n"
    msg += "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    msg += f"🌐 *[MARKET REGIME]*\n"
    msg += f"`{regime_label}`\n"
    tf_label = "✓ Weekly Bullish" if weekly_ok else ("✗ Weekly Bearish" if weekly_ok is False else "N/A")
    msg += f"Multi-TF: `{tf_label}`\n\n"
    
    pct_sign = "▲" if s['pct_1d'] > 0 else "▼"
    msg += f"🏢 *{sym_name}*\n"
    msg += f"💰 Price: `{format_rp(s['close'])}` ({pct_sign} {abs(s['pct_1d']):.1f}%)\n"
    msg += f"📊 Volume: `{format_vol(s['vol'])}` ({s['vol_ratio']*100:.0f}% vs Avg)\n\n"
    
    msg += f"🏛️ *[FUNDAMENTAL CONTEXT]*\n"
    pe = f"{s['pe_ratio']:.1f}x" if s.get('pe_ratio') else "N/A"
    pbv = f"{s['pbv']:.1f}x" if s.get('pbv') else "N/A"
    mcap = f"{s['market_cap']/1e12:.1f}T" if s.get('market_cap') else "N/A"
    msg += f"P/E: `{pe}` | PBV: `{pbv}` | MCap: `Rp{mcap}`\n\n"

    msg += f"📉 *[TECHNICAL PULSE]*\n"
    msg += f"Phase: `{s.get('wyckoff_phase', 'N/A')}`\n"
    msg += f"Vola: `{'SQUEEZE (Pending Expansion)' if s['is_squeeze'] else 'Normal'}`\n\n"
    
    bee_bar = draw_progress_bar(s.get('bee_score', 0))
    msg += f"🧠 *[SMART MONEY PROXY]*\n"
    msg += f"`{bee_bar}` {s.get('bee_score', 0)}/10\n"
    msg += f"_(PVT + CMF + Volume Anomaly)_\n\n"
    
    msg += f"💬 *[QUANT CONSENSUS]*\n"
    msg += f"_{narrative}_\n\n"
    
    msg += f"🎯 *[EXECUTION RULES]*\n"
    if direction == "BUY":
        msg += f"Entry Zone: `{format_rp(s['entry_low'])} — {format_rp(s['entry_high'])}`\n"
        msg += f"Invalidation: `Daily Close < {format_rp(s['stop_loss'])}`\n"
        msg += f"TP: `{format_rp(s['target_1'])}` | `{format_rp(s['target_2'])}`\n"
    else:
        msg += f"Exit: `{format_rp(s['close'])}` | Invalidation: `{format_rp(s['target_1'])}`\n"
    msg += f"Holding: `Swing (3-14 Trading Days)`\n"
    
    if lot > 0:
        msg += f"\n💵 *[POSITION SIZING]*\n"
        msg += f"Size: `{lot:,} lembar` (Rp {pos_value:,.0f})\n"
        msg += f"Risk: `{s.get('risk_pct', 1.5):.1f}% of Rp 50M`\n"
    
    if sector_warnings:
        msg += f"\n⚠️ *[EXPOSURE WARNING]*\n"
        for w in sector_warnings:
            msg += f"_{w}_\n"
            
    safety_warnings = ext.get('safety_warnings', [])
    if safety_warnings:
        msg += f"\n🛑 *[SAFETY BREACH]*\n"
        for w in safety_warnings:
            msg += f"_{w}_\n"
    
    liq = health.get('liquidity', 'N/A')
    news = health.get('news_risk', 'LOW')
    msg += f"\n🏥 *[HEALTH CHECK]*\n"
    msg += f"Liquidity: `{liq}` | News Risk: `{news}`\n"
    
    conv_bar = draw_progress_bar(score, max_val=10)
    msg += f"\n⚖️ *[CONVICTION METRIC]*\n"
    msg += f"`{conv_bar}` {score:.1f}/10\n"
    
    if isinstance(layers, dict) and 'SmartMoney' in layers:
        msg += f"SmartMoney(35%): `{layers.get('SmartMoney', 0):.1f}` | "
        msg += f"Trend(25%): `{layers.get('Trend', 0):.1f}` | "
        msg += f"RSI/Phase(20%): `{layers.get('RSI/Phase', 0):.1f}`\n"
        msg += f"Volatility(15%): `{layers.get('Volatility', 0):.1f}` | "
        msg += f"Macro(5%): `{layers.get('Macro', 0):.1f}`\n"
    
    if bt_stats:
        msg += f"\n📊 *[HISTORICAL STATS (2Y)]*\n"
        msg += f"Winrate: `{bt_stats['winrate']}%` | PF: `{bt_stats['profit_factor']}` | MaxDD: `{bt_stats['max_drawdown_r']}R` (N={bt_stats['total_trades']})\n"
    
    msg += f"\n📖 *[PLAYBOOK]*\n"
    if direction == "BUY":
        msg += "_Buy near lower bound of entry zone. Scale-out 50% at TP1, trail stop above swing low for remainder._\n"
    else:
        msg += "_Exit at market or scale-out. Re-enter only if price reclaims above invalidation level._\n"
    
    msg += f"\n⚠️ _Probabilistic edge, not a guarantee. False breakouts occur._\n"
    msg += "┗━━━━━━━━━━━━━━━━━━━━┛\n"
    
    return msg

def format_status_report(all_stocks_status: list[dict[str, Any]], ihsg_data: dict[str, Any] | None = None, broker: MockBroker | None = None) -> str:
    bullish_stocks = [s for s in all_stocks_status if s['trend'] == 'BULLISH']
    bearish_stocks = [s for s in all_stocks_status if s['trend'] == 'BEARISH']
    
    msg = "┏━━━━━━━━━━━━━━━━━━━━┓\n"
    msg += f"📊 *[QUANTITATIVE INTELLIGENCE REPORT]*\n"
    msg += f"📅 {datetime.now(TIMEZONE).strftime('%d %b %Y, %H:%M WIB')}\n"
    msg += f"📎 Core: Quant Alpha V11 Pro | Institutional Screener\n"
    msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    if ihsg_data:
        ihsg_pct = ihsg_data['pct_1d']
        ihsg_bar = draw_progress_bar((ihsg_pct + 2) * 2.5, max_val=10)
        msg += f"🌐 *[MARKET REGIME]*\n"
        msg += f"IHSG: `{format_rp(ihsg_data['close'])}` ({'↑' if ihsg_pct >= 0 else '↓'} {abs(ihsg_pct):.1f}%)\n"
        msg += f"`{ihsg_bar}` Sentiment: `{ihsg_data['trend']}`\n"
        regime_label = ihsg_data.get('regime_label', 'N/A')
        adx = ihsg_data.get('adx', 0)
        msg += f"Regime: `{regime_label}`\n"
        msg += f"ADX: `{adx:.1f}`\n\n"
    
    try:
        if os.path.isfile(FORWARD_LOG_FILE):
            import csv
            with open(FORWARD_LOG_FILE, 'r') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            if len(rows) >= 5:
                msg += f"📈 *[SYSTEM PERFORMANCE (Forward)]*\n"
                msg += f"Total signals logged: `{len(rows)}`\n"
                buy_count = sum(1 for r in rows if r.get('Direction') == 'BUY')
                sell_count = sum(1 for r in rows if r.get('Direction') == 'SELL')
                msg += f"BUY: `{buy_count}` | SELL: `{sell_count}`\n\n"
    except Exception as e:
        logger.debug(f"Could not read forward test log for report: {e}")
    
    msg += f"📈 *[BULLISH DYNAMICS]*\n"
    if not bullish_stocks:
        msg += "_No assets in markup phase._\n"
    else:
        for i, s in enumerate(bullish_stocks, 1):
            sym = s['symbol'].split('.')[0]
            bee_bar = draw_progress_bar(s.get('bee_score', 0), max_val=5)
            pattern = f" | {s.get('pattern', '')}" if s.get('pattern') else ""
            msg += f"{i}. {sym} | `{format_rp(s['close'])}` | RSI:{int(s.get('rsi', 0))}{pattern}\n"
            msg += f"   Strength: `{bee_bar}` {s.get('wyckoff_phase', 'N/A')}\n"
            msg += f"   S: `{format_rp(s.get('support', 0))}` | R: `{format_rp(s.get('resistance', 0))}`\n"
            
    msg += f"\n📉 *[BEARISH DYNAMICS (Top 5)]*\n"
    if not bearish_stocks:
        msg += "_No assets in markdown phase._\n"
    else:
        for i, s in enumerate(bearish_stocks[:5], 1):
            sym = s['symbol'].split('.')[0]
            msg += f"{i}. {sym} | `{format_rp(s['close'])}` | RSI:{int(s.get('rsi', 0))}\n"
            msg += f"   S: `{format_rp(s.get('support', 0))}` | R: `{format_rp(s.get('resistance', 0))}`\n"
            
    msg += f"\n🔍 *[SMART MONEY PROXY]*\n"
    all_sorted = sorted(all_stocks_status, key=lambda x: x.get('bee_score', 0), reverse=True)
    top = [s for s in all_sorted if s.get('bee_score', 0) >= 4][:5]
    if top:
        for s in top:
            sym = s['symbol'].split('.')[0]
            bee_bar = draw_progress_bar(s.get('bee_score', 0), max_val=10)
            msg += f"• *{sym}*: `{bee_bar}` {s.get('bee_score', 0)}/10\n"
    else:
        msg += "_Institutional flow is dormant._\n"
    
    if broker:
        balance = broker.get_balance()
        positions = broker.get_open_positions()
        
        msg += f"\n💰 *[MOCK PORTFOLIO STATUS]*\n"
        msg += f"Cash Balance: `{format_rp(balance)}`\n"
        msg += f"Open Positions: `{len(positions)}`\n"
        
        if positions:
            total_unrealized_pnl = 0.0
            for sym, pos in positions.items():
                current_price = pos.get('avg_price', 0)
                status = next((st for st in all_stocks_status if st['symbol'] == sym), None)
                if status:
                    current_price = status['close']
                
                pnl_pct = ((current_price - pos['avg_price']) / pos['avg_price']) * 100
                total_unrealized_pnl += (current_price - pos['avg_price']) * pos['quantity']
                
                msg += f"• *{sym.split('.')[0]}*: {format_rp(current_price)} ({'▲' if pnl_pct >=0 else '▼'} {abs(pnl_pct):.1f}%)\n"
            
            msg += f"Unrealized P/L: `{format_rp(total_unrealized_pnl)}`\n"
        else:
            msg += "_Portfolio is currently all cash._\n"

    msg += "\n🔬 *[QUANT CONSENSUS]*: Scan complete. Next check in 15 mins.\n"
    msg += "┗━━━━━━━━━━━━━━━━━━━━┛\n"
    
    return msg

# ============================================================
# TELEGRAM
# ============================================================

async def send_telegram(message: str, photo_path: str | None = None) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram Token/ChatID is missing! Notification skipped.")
        return
        
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        if photo_path and os.path.exists(photo_path):
            if len(message) > 1024:
                await bot.send_photo(chat_id=TELEGRAM_CHAT_ID, photo=open(photo_path, 'rb'))
                await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode='Markdown')
            else:
                await bot.send_photo(chat_id=TELEGRAM_CHAT_ID, photo=open(photo_path, 'rb'), caption=message, parse_mode='Markdown')
            os.remove(photo_path)
            logger.info("Sent Telegram alert with chart")
        else:
            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode='Markdown')
            logger.info("Sent Telegram text alert")
    except Exception as e:
        logger.error(f"Telegram error: {e}", exc_info=True)


# ============================================================
# MAIN
# ============================================================

async def main() -> None:
    logger.info(f"=== Quant Alpha Engine V11 Pro ({datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M')}) ===")
    config = load_config()
    state = get_last_state()
    
    gs_cfg = config.get('google_sheets', {})
    broker = MockBroker(initial_equity=config.get('portfolio', {}).get('initial_equity', 50000000))
    sheet_logger = GoogleSheetsLogger(
        sheet_id=gs_cfg.get('spreadsheet_id'), 
        credentials_file=gs_cfg.get('credentials_file', 'service_account.json')
    )
    
    # ── 1. Check Exits for Open Positions ────────────────────────────────
    logger.info("[EXECUTION] Checking Open Positions for Exit signals...")
    open_positions = broker.get_open_positions().copy()
    for sym, pos in open_positions.items():
        df = fetch_data(sym, config)
        if df is None: continue
        df = calculate_indicators(df, config)
        
        last_row = df.iloc[-1]
        close = last_row['Close']
        rsi = last_row.get(f"RSI_{config['indicators']['rsi_length']}", 50)
        atr = last_row.get(f"ATRr_{config['indicators']['atr_period']}", close * 0.02)
        
        entry_date = pos.get('entry_date', datetime.now(TIMEZONE).isoformat())
        days_held = (datetime.now(TIMEZONE) - datetime.fromisoformat(entry_date)).days
        
        swing_low = df['Low'].tail(5).min()
        trailing_sl = swing_low - (atr * 0.5)
        
        exit_reason = None
        sell_lot = None
        
        if days_held > config.get('execution', {}).get('force_exit_days', 21):
            exit_reason = "Time Decay (>21 days)"
        elif close <= trailing_sl and pos.get('tp1_hit', False):
            exit_reason = "Trailing SL Hit"
        elif close >= (pos['avg_price'] + atr * 2) and not pos.get('tp1_hit', False):
            exit_reason = "TP1 Hit (Scale Out 50%)"
            sell_lot = pos['quantity'] // 2
        elif rsi >= config.get('indicators', {}).get('rsi_overbought', 75):
            exit_reason = "Overbought"
        
        if exit_reason:
            logger.info(f"[{sym}] EXIT TRIGGERED: {exit_reason} at {format_rp(close)}")
            success, res = broker.execute_sell(sym, close, lot=sell_lot, reason=exit_reason)
            if success and isinstance(res, dict):
                sheet_logger.log_trade(sym, "SELL", close, res['qty'], reason=exit_reason, pnl=res['realized_pnl'])
                
    # ── 2. Fetch Macro Data ─────────────────────────────────────────────
    logger.info("[IHSG] Fetching macro data & regime...")
    ihsg_data = fetch_ihsg(config)
    
    regime = ihsg_data.get('regime', 'UNKNOWN') if ihsg_data else 'UNKNOWN'
    regime_label = ihsg_data.get('regime_label', 'N/A') if ihsg_data else 'N/A'
    logger.info(f"[REGIME] {regime_label}")
    
    # ── 3. Scan Universal Signals ───────────────────────────────────────
    signals_sent_today = []
    all_stocks_status = []
    
    # V11 Pro: Comprehensive Safety Circuit Breakers
    is_safe_to_trade, safety_warnings = check_safety_gates(broker, ihsg_data, config)
    if not is_safe_to_trade:
        logger.warning(f"CIRCUIT BREAKERS ACTIVE: {', '.join(safety_warnings)}. "
                       "Auto-trade execution is halted.")
    
    for symbol in config['stocks']:
        df = fetch_data(symbol, config)
        if df is not None:
            df = calculate_indicators(df, config)
            signal_data, status_summary, reason = evaluate_signals(symbol, df, config, ihsg_data=ihsg_data)
            
            if status_summary is not None:
                # Apply conviction decay for reporting if we already own it
                if symbol in broker.get_open_positions():
                    pos = broker.get_open_positions()[symbol]
                    entry_date = pos.get('entry_date', datetime.now(TIMEZONE).isoformat())
                    decayed_conviction = apply_conviction_decay(entry_date, status_summary['conviction'], config)
                    status_summary['conviction'] = decayed_conviction
                    if signal_data:
                        signal_data['score'] = decayed_conviction
                        signal_data['desc'] = f"Weighted Conviction (Decayed): {decayed_conviction:.1f}/10"

                all_stocks_status.append(status_summary)
            else:
                logger.debug(f"[{symbol}] {reason}")
                continue

            if signal_data:
                sig_type = signal_data['type']
                if check_cooldown(symbol, str(sig_type), state, config):
                    logger.debug(f"[{symbol}] Alert '{sig_type}' blocked (Cooldown)")
                    continue
                
                s = signal_data['data']
                hc = health_check(df, config)
                weekly = fetch_weekly_trend(symbol)
                weekly_bullish = weekly.get('weekly_bullish') if weekly else None
                
                lot, pos_value, risk_pct_tier = calculate_position_size(s['close'], s['stop_loss'], signal_data['score'], config)
                s['risk_pct'] = risk_pct_tier
                
                if regime == 'CHOPPY':
                    reduce_pct = config.get('regime', {}).get('choppy_reduce_pct', 30)
                    lot = int(lot * (1 - reduce_pct / 100))
                    lot = (lot // 100) * 100
                    pos_value = lot * s['close']
                
                sector_warnings = check_sector_exposure(symbol, signals_sent_today, config)
                
                # Check Single Trade Equity Cap
                max_single_eq = config.get('safety', {}).get('max_single_trade_equity_pct', 50)
                if pos_value > broker.get_balance() * (max_single_eq / 100):
                    safety_warnings.append(f"[{symbol}] Position size exceeds single trade equity cap ({max_single_eq}%)")
                    is_safe_to_trade = False
                
                exec_status = "PENDING"
                if sig_type == "AUTO_TRADE_BUY":
                    if is_safe_to_trade and not sector_warnings and hc['liquidity'] != 'LOW':
                        logger.info(f"[{symbol}] Executing AUTO-TRADE BUY...")
                        success, res = broker.execute_buy(symbol, s['close'], lot, reason=f"Conviction {signal_data['score']:.1f}")
                        if success and isinstance(res, dict):
                            sheet_logger.log_trade(symbol, "BUY", s['close'], lot, conviction=signal_data['score'], reason="Auto-Trade Signal")
                            exec_status = "EXECUTED"
                        else:
                            logger.error(f"[{symbol}] Execution Failed: {res}")
                            exec_status = "FAILED"
                    else:
                        logger.warning(f"[{symbol}] Auto-Trade Blocked by Safety Gates")
                        exec_status = "BLOCKED"
                
                bt_stats = run_backtest_stats(symbol, df, config)
                
                extra = {
                    'lot': lot,
                    'position_value': pos_value,
                    'health': hc,
                    'regime': regime,
                    'regime_label': regime_label,
                    'weekly_bullish': weekly_bullish,
                    'backtest_stats': bt_stats,
                    'sector_warnings': sector_warnings,
                    'safety_warnings': safety_warnings if not is_safe_to_trade else [],
                    'exec_status': exec_status
                }
                
                msg = format_alert(signal_data, extra=extra)
                
                photo_path = None
                if signal_data['confidence'] == 'HIGH':
                    try:
                        photo_path = generate_chart(symbol, df, config)
                    except Exception as e:
                        logger.error(f"[{symbol}] Chart error: {e}", exc_info=True)
                
                await send_telegram(msg, photo_path=photo_path)
                signals_sent_today.append(symbol)
                
                log_forward_test(symbol, signal_data, lot, pos_value, hc, regime)
                
                state[symbol] = {
                    'signal': sig_type,
                    'time': datetime.now(TIMEZONE).isoformat()
                }
                logger.info(f"[{symbol}] ⚡ {sig_type} (Score: {signal_data['score']:.0f}/10 | Lot: {lot:,})")
            else:
                logger.debug(f"[{symbol}] {reason}")
            
    # ── 4. End of Scan Procedures ───────────────────────────────────────
    now = datetime.now(TIMEZONE)
    if config['signals']['send_status_report_if_no_alerts']:
        if len(all_stocks_status) > 0:
            logger.info(f"Session {now.hour}:00 WIB. Sending Market Status Report...")
            report = format_status_report(all_stocks_status, ihsg_data=ihsg_data, broker=broker)
            if not signals_sent_today:
                report += "\n_Note: No new execution signals in this scan._"
            
            await send_telegram(report)
        else:
            logger.info("No stock data available to generate status report.")
    else:
        logger.info("Status report disabled in config.")
            
    total_unrealized_pnl = 0.0
    open_positions = broker.get_open_positions()
    for sym, pos in open_positions.items():
        status = next((s for s in all_stocks_status if s['symbol'] == sym), None)
        if status:
            total_unrealized_pnl += (status['close'] - pos['avg_price']) * pos['quantity']

    sheet_logger.log_portfolio(broker.get_balance(), len(open_positions), total_unrealized_pnl)
            
    save_state(state)
    logger.info("=== Scan Complete ===")

if __name__ == "__main__":
    asyncio.run(main())
