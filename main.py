import os
import json
import asyncio
import math
import time
from datetime import datetime, timedelta
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

TIMEZONE = pytz.timezone('Asia/Jakarta')
STATE_FILE = "last_signals.json"
SIGNAL_LOG_FILE = "signal_logs.csv"
FORWARD_LOG_FILE = "forward_test.csv"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ============================================================
# UTILITIES
# ============================================================

def load_config():
    with open("config.json", "r") as f:
        return json.load(f)

def get_last_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {}

def save_state(state):
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f)
    except Exception as e:
        print(f"Failed to save state: {e}")

def format_rp(n):
    return f"Rp {n:,.0f}".replace(',', '.')

def format_vol(n):
    return f"{n/1_000_000:.1f}M" if n >= 1e6 else f"{n/1_000:.1f}K"

# ============================================================
# CINEMATIC UI HELPERS (V7)
# ============================================================

def draw_progress_bar(value, max_val=10):
    """Draws a visual bar like ██████░░░░"""
    try:
        val = int(round(value))
        filled = max(0, min(max_val, val))
        empty = max_val - filled
        return "█" * filled + "░" * empty
    except:
        return "░" * max_val

def generate_narrative(s):
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

def fetch_data(symbol, config):
    print(f"[{symbol}] Fetching data...")
    try:
        stock = yf.Ticker(symbol)
        df = stock.history(period="1y", interval="1d")
        if df.empty:
            print(f"[{symbol}] Empty data!")
            return None
            
        lookback = config['signals']['price_peak_lookback_days']
        if len(df) >= lookback:
            df['Peak_Price'] = df['High'].rolling(window=lookback, min_periods=1).max()
        else:
            df['Peak_Price'] = df['High'].rolling(window=len(df), min_periods=1).max()
            
        # V8: Fetch Fundamentals
        try:
            info = stock.info
            df.attrs['pe_ratio'] = info.get('trailingPE', None)
            df.attrs['pbv'] = info.get('priceToBook', None)
            df.attrs['market_cap'] = info.get('marketCap', None)
        except:
            df.attrs['pe_ratio'] = None
            df.attrs['pbv'] = None
            df.attrs['market_cap'] = None
            
        return df
    except Exception as e:
        print(f"[{symbol}] Fetch error: {e}")
        return None

def fetch_ihsg(config):
    """Fetch IHSG index data for macro context and regime detection"""
    try:
        idx_symbol = config.get('macro', {}).get('index_symbol', '^JKSE')
        stock = yf.Ticker(idx_symbol)
        df = stock.history(period="1y", interval="1d")
        if df.empty or len(df) < 2:
            return None
        
        last = df.iloc[-1]
        prev = df.iloc[-2]
        pct = ((last['Close'] - prev['Close']) / prev['Close']) * 100
        
        # Regime Detection
        ma200_val = df['Close'].rolling(200).mean().iloc[-1] if len(df) >= 200 else df['Close'].mean()
        ma50_val = df['Close'].rolling(50).mean().iloc[-1] if len(df) >= 50 else df['Close'].mean()
        
        # ADX approximation via directional movement
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
        print(f"[IHSG] Fetch error: {e}")
        return None

def fetch_weekly_trend(symbol):
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
        print(f"[{symbol}] Weekly fetch error: {e}")
        return None

# ============================================================
# TECHNICAL INDICATORS
# ============================================================

def calculate_indicators(df, config):
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

def is_downtrend(df, config):
    days = config['signals']['ignore_downtrend_days']
    if len(df) < days: return False
    
    ma200_col = f"SMA_{config['indicators']['ma_long']}"
    for i in range(1, days + 1):
        row = df.iloc[-i]
        if row['Close'] >= row[ma200_col]:
            return False
    return True

def check_cooldown(symbol, signal_type, state, config):
    now = datetime.now(TIMEZONE)
    if symbol in state:
        last_sig = state[symbol].get('signal')
        last_time_str = state[symbol].get('time')
        if last_sig == signal_type and last_time_str:
            last_time = datetime.fromisoformat(last_time_str)
            if now - last_time < timedelta(hours=config['signals']['signal_cooldown_hours']):
                return True
    return False

def detect_candles(df):
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
# MARKET INTELLIGENCE ENGINE (V6 — BEE-FLOW & WYCKOFF)
# ============================================================

def detect_wyckoff_phase(df):
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
        # Check volume trend (Low volume or starting to spike on green candles)
        return "ACCUMULATION (Smart Money Buying)"
        
    # 4. DISTRIBUTION (Sideways at top)
    if close > ma200 and abs(close - ma50)/ma50 < 0.05 and last['Pct_Change_5D'] < 0:
        return "DISTRIBUTION (Institutions Selling)"
        
    return "CONSOLIDATION (Neutral)"

def calculate_bee_flow(df):
    """
    Simulate 'Broker Intelligence' (BEE-FLOW) using VPA.
    Returns Score (0-10) and Label.
    """
    if len(df) < 20: return 0, "NEUTRAL"
    
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
    final_score = max(0, min(10, score))
    
    if final_score >= 8: label = "HIGH ACCUMULATION (BIG BEE)"
    elif final_score >= 6: label = "MILD ACCUMULATION"
    elif final_score <= 3: label = "DISTRIBUTION (EXITING)"
    else: label = "NEUTRAL"
    
    return final_score, label

def get_volume_context(pct_1d, vol_ratio):
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
# V9 PRO: POSITION SIZER
# ============================================================

def calculate_position_size(price, stop_loss, conviction_score, config):
    """
    V9 PRO: Position Sizer
    Calculate lot size based on risk-per-trade tiers driven by conviction score.
    
    Tiers:
    - 9.0–10.0: 4.0% risk (FULL)
    - 7.5–8.9: 2.5% risk
    - 6.5–7.4: 1.5% risk
    - 4.5–6.4: 0.75% risk (Alert only)
    - < 4.5: SKIP
    """
    portfolio = config.get('portfolio', {})
    initial_equity = portfolio.get('initial_equity', 50000000)
    
    # Determine risk % based on conviction score
    if conviction_score >= 9.0:
        risk_pct = 4.0
    elif conviction_score >= 7.5:
        risk_pct = 2.5
    elif conviction_score >= 6.5:
        risk_pct = 1.5
    elif conviction_score >= 4.5:
        risk_pct = 0.75
    else:
        return 0, 0, 0 # Skip
        
    risk_amount = initial_equity * (risk_pct / 100)
    
    # Stop loss distance
    risk_per_share = abs(price - stop_loss)
    if risk_per_share <= 0:
        # Fallback to 5% stop if data is weird
        risk_per_share = price * 0.05
        
    shares = int(risk_amount / risk_per_share)
    
    # Round down to nearest 100 (lot size for IDX)
    lot = (shares // 100) * 100
    position_value = lot * price
    
    return lot, position_value, risk_pct

# ============================================================
# V9 PRO: SECTOR EXPOSURE CONTROLLER
# ============================================================

def check_sector_exposure(symbol, active_signals, config):
    """Check if adding this symbol would breach sector exposure limits"""
    sectors = config.get('sectors', {})
    portfolio = config.get('portfolio', {})
    max_sector_pct = portfolio.get('max_sector_exposure_pct', 30)
    max_positions = portfolio.get('max_open_positions', 5)
    
    current_sector = sectors.get(symbol, 'Unknown')
    
    # Count active signals per sector
    sector_count = {}
    for sig in active_signals:
        sig_sector = sectors.get(sig, 'Unknown')
        sector_count[sig_sector] = sector_count.get(sig_sector, 0) + 1
    
    same_sector_count = sector_count.get(current_sector, 0)
    total_active = len(active_signals)
    
    warnings = []
    
    if total_active >= max_positions:
        warnings.append(f"Max open positions ({max_positions}) reached")
    
    if total_active > 0:
        sector_pct = (same_sector_count / max(total_active, 1)) * 100
        if sector_pct >= max_sector_pct:
            warnings.append(f"Sector {current_sector} exposure > {max_sector_pct}%")
    
    return warnings

# ============================================================
# V9 PRO: HEALTH CHECK
# ============================================================

def health_check(df, config):
    """Pre-signal quality control: liquidity, volume, gap filtering"""
    health = config.get('health', {})
    min_avg_vol = health.get('min_avg_volume', 100000)
    min_avg_value = health.get('min_avg_value_rp', 10000000000)
    
    result = {'liquidity': 'OK', 'news_risk': 'LOW', 'warnings': []}
    
    if len(df) < 20:
        result['liquidity'] = 'INSUFFICIENT_DATA'
        result['warnings'].append("Less than 20 days data")
        return result
    
    # Average daily volume
    avg_vol = df['Volume'].tail(20).mean()
    if avg_vol < min_avg_vol:
        result['liquidity'] = 'LOW'
        result['warnings'].append(f"Avg volume ({avg_vol:,.0f}) < {min_avg_vol:,.0f}")
    
    # Average daily value (proxy for institutional tradability)
    avg_value = (df['Close'] * df['Volume']).tail(20).mean()
    if avg_value < min_avg_value:
        result['liquidity'] = 'THIN'
        result['warnings'].append(f"Avg value Rp {avg_value:,.0f} < threshold")
    
    # Gap detection (> 5% gap is risky)
    last_gap = abs(df['Open'].iloc[-1] - df['Close'].iloc[-2]) / df['Close'].iloc[-2] * 100
    if last_gap > 5:
        result['warnings'].append(f"Large gap detected ({last_gap:.1f}%)")
    
    return result

# ============================================================
# V9 PRO: BACKTEST ENGINE (Historical Signal Statistics)
# ============================================================

def run_backtest_stats(symbol, df, config):
    """
    Simulate historical signals on past data and calculate performance stats.
    Uses the same scoring logic to find past setups, then checks if TP or SL was hit first.
    Returns: dict with winrate, profit_factor, max_drawdown, trade_count
    """
    bt_cfg = config.get('backtest', {})
    tp_mult = bt_cfg.get('tp_atr_multiplier', 2.0)
    sl_mult = bt_cfg.get('sl_atr_multiplier', 2.0)
    ind_cfg = config['indicators']
    
    if len(df) < 200:
        return None
    
    # Pre-compute columns needed
    rsi_col = f"RSI_{ind_cfg['rsi_length']}"
    ma200_col = f"SMA_{ind_cfg['ma_long']}"
    atr_col = [c for c in df.columns if c.startswith('ATR')]
    atr_col = atr_col[0] if atr_col else None
    
    if rsi_col not in df.columns or ma200_col not in df.columns or not atr_col:
        return None
    
    wins = 0
    losses = 0
    total_r_won = 0.0
    total_r_lost = 0.0
    max_dd = 0.0
    equity_curve = [0.0]
    
    # Scan historical data (skip first 200 for warm-up, scan remaining)
    for i in range(200, len(df) - 10):
        row = df.iloc[i]
        
        rsi = row.get(rsi_col)
        ma200 = row.get(ma200_col)
        close = row['Close']
        atr = row.get(atr_col, close * 0.02)
        
        if pd.isna(rsi) or pd.isna(ma200) or pd.isna(atr) or atr <= 0:
            continue
        
        # Simple buy setup: RSI < 40 AND Close > MA200 (same as our core logic)
        if rsi < 40 and close > ma200:
            entry = close
            sl = entry - atr * sl_mult
            tp = entry + atr * tp_mult
            
            # Walk forward to check outcome
            for j in range(i + 1, min(i + 15, len(df))):  # Max 14 days holding
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
            # If neither hit within 14 days, count as scratch (break-even)
    
    total_trades = wins + losses
    if total_trades == 0:
        return None
    
    winrate = (wins / total_trades) * 100
    profit_factor = total_r_won / total_r_lost if total_r_lost > 0 else 999
    
    # Max drawdown from equity curve
    peak = 0
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

# ============================================================
# V9 PRO: FORWARD TEST LOGGER
# ============================================================

def log_forward_test(symbol, signal_data, lot, position_value, health, regime):
    """Enhanced signal logging for forward test validation"""
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
        print(f"[{symbol}] Failed to log forward test: {e}")

# ============================================================
# V9 MULTI-CONFIRMATION SCORING ENGINE
# ============================================================

def evaluate_signals(symbol, df, config, ihsg_data=None):
    """
    V9 PRO: Weighted Conviction Scoring Engine
    Weighted Formula:
    - Smart Money Proxy: 35%
    - Trend Confirmation: 25%
    - RSI/Phase Alignment: 20%
    - Volatility Check: 15%
    - Macro Regime Fit: 5%
    """
    last_row = df.iloc[-1]
    
    ind_cfg = config['indicators']
    sig_cfg = config['signals']
    risk_cfg = config.get('risk', {})
    
    ma50_col = f"SMA_{ind_cfg['ma_short']}"
    ma200_col = f"SMA_{ind_cfg['ma_long']}"
    rsi_col = f"RSI_{ind_cfg['rsi_length']}"
    adx_col = [c for c in df.columns if c.startswith('ADX_14')]
    cmf_col = [c for c in df.columns if c.startswith('CMF_20')]
    pvt_col = [c for c in df.columns if c.startswith('PVT')]
    atr_col = f"ATRr_{ind_cfg['atr_period']}"
    
    try:
        close = last_row['Close']
        volume = last_row['Volume']
        vol_avg = last_row['Vol_Avg']
        rsi = last_row[rsi_col]
        ma50 = last_row[ma50_col]
        ma200 = last_row[ma200_col]
        pct_1d = last_row['Pct_Change_1D']
        support = last_row['Support_Level']
        resistance = last_row['Resistance_Level']
        
        adx = last_row[adx_col[0]] if adx_col else 0
        cmf = last_row[cmf_col[0]] if cmf_col else 0
        pvt = last_row[pvt_col[0]] if pvt_col else 0
    except KeyError:
        return None, None, "Indicators incomplete."
        
    # --- BUY CONVICTION COMPONENTS ---
    # 1. Smart Money Proxy (35%)
    sm_score = 0
    if vol_ratio > 2.5: sm_score += 0.4
    elif vol_ratio > 1.5: sm_score += 0.2
    if cmf > 0: sm_score += 0.3
    if pvt > df['PVT'].tail(5).mean(): sm_score += 0.3
    sm_weight = 0.35 * min(1.0, sm_score) * 10
    
    # 2. Trend Confirmation (25%)
    trend_score = 0
    if close > ma200: trend_score += 0.5
    if adx > 30: trend_score += 0.5
    elif adx > 20: trend_score += 0.2
    trend_weight = 0.25 * trend_score * 10
    
    # 3. RSI/Phase Alignment (20%)
    wyckoff_phase = detect_wyckoff_phase(df)
    rp_score = 0
    if 45 <= rsi <= 75: rp_score += 0.5
    if "MARKUP" in wyckoff_phase or "ACCUMULATION" in wyckoff_phase: rp_score += 0.5
    rp_weight = 0.20 * rp_score * 10
    
    # 4. Volatility Check (15%)
    atr = last_row.get(atr_col)
    if atr is None or pd.isna(atr): atr = close * 0.02
    atr_pct = (atr / close) * 100
    
    vol_check_score = 0
    if atr_pct < 3.0: vol_check_score = 1.0
    elif atr_pct < 5.0: vol_check_score = 0.5
    vol_weight = 0.15 * vol_check_score * 10
    
    # 5. Macro Regime Fit (5%)
    macro_score = 0
    if ihsg_data and ihsg_data.get('trend') == 'BULLISH': macro_score = 1.0
    macro_weight = 0.05 * macro_score * 10
    
    final_conviction = sm_weight + trend_weight + rp_weight + vol_weight + macro_weight
    
    signal_type = None
    confidence = "LOW"
    if final_conviction >= 6.5:
        signal_type = "AUTO_TRADE_BUY"
        confidence = "HIGH" if final_conviction >= 8.5 else "MEDIUM"
    elif final_conviction >= 4.5:
        signal_type = "ALERT_ONLY_BUY"
        confidence = "LOW"
        
    if not signal_type:
        return None, None, f"Conviction too low ({final_conviction:.1f})"

    # Entry Zones & Targets
    entry_low = round(close - atr * 0.3, 0)
    entry_high = round(close + atr * 0.3, 0)
    stop_loss = round(max(support, close - atr * 2), 0)
    target_1 = round(min(resistance, close + atr * 2), 0)
    target_2 = round(close + atr * 4, 0)
    
    # RRR calculation
    risk_amount = close - stop_loss
    rrr_1 = round((target_1 - close) / risk_amount, 1) if risk_amount > 0 else 0
    rrr_2 = round((target_2 - close) / risk_amount, 1) if risk_amount > 0 else 0

    bee_score, bee_label = calculate_bee_flow(df)
    is_squeeze = (last_row.get('BB_Width', 1.0) < (df['BB_Width'].tail(20).mean() * 0.8))

    status_summary = {
        'symbol': symbol,
        'close': close,
        'conviction': round(final_conviction, 1),
        'rsi': rsi,
        'adx': adx,
        'vol': volume,
        'vol_ratio': vol_ratio,
        'pct_1d': pct_1d,
        'phase': wyckoff_phase,
        'wyckoff_phase': wyckoff_phase,
        'bee_score': bee_score,
        'bee_label': bee_label,
        'is_squeeze': is_squeeze,
        'atr_pct': atr_pct,
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
        'direction': "BUY",
        'ma200': ma200,
        'trend': 'BULLISH' if close > ma200 else 'BEARISH',
        'pe_ratio': df.attrs.get('pe_ratio'),
        'pbv': df.attrs.get('pbv'),
        'market_cap': df.attrs.get('market_cap'),
        'pattern': detect_candles(df),
        'vol_context': get_volume_context(pct_1d, vol_ratio)
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
# CHART GENERATOR
# ============================================================

def generate_chart(symbol, df, config):
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

def format_alert(signal_data, extra=None):
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
    
    # Quant Header
    sig_type = signal_data.get('type', '')
    if sig_type == "AUTO_TRADE_BUY":
        alert_title = "🤖 [AUTO-TRADE EXECUTED]" if conf in ["HIGH", "MEDIUM"] else "🚨 [QUANT BUY ALERT]"
    elif sig_type == "ALERT_ONLY_BUY":
        alert_title = "👀 [ALERT ONLY — Manual Review]"
    elif direction == "SELL":
        alert_title = "⚠️ [DISTRIBUTION WARNING]" if conf == "HIGH" else "📉 [EXIT PROTOCOL]"
    else:
        alert_title = "📊 [SIGNAL DETECTED]"
        
    msg = "┏━━━━━━━━━━━━━━━━━━━━┓\n"
    msg += f"*{alert_title}*\n"
    msg += f"Core: Quant Alpha Engine V10 Auto-Trade\n"
    msg += "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    # MARKET REGIME
    msg += f"🌐 *[MARKET REGIME]*\n"
    msg += f"`{regime_label}`\n"
    tf_label = "✓ Weekly Bullish" if weekly_ok else ("✗ Weekly Bearish" if weekly_ok is False else "N/A")
    msg += f"Multi-TF: `{tf_label}`\n\n"
    
    # Asset Context
    pct_sign = "▲" if s['pct_1d'] > 0 else "▼"
    msg += f"🏢 *{sym_name}*\n"
    msg += f"💰 Price: `{format_rp(s['close'])}` ({pct_sign} {abs(s['pct_1d']):.1f}%)\n"
    msg += f"📊 Volume: `{format_vol(s['vol'])}` ({s['vol_ratio']*100:.0f}% vs Avg)\n\n"
    
    # FUNDAMENTAL CONTEXT
    msg += f"🏛️ *[FUNDAMENTAL CONTEXT]*\n"
    pe = f"{s['pe_ratio']:.1f}x" if s.get('pe_ratio') else "N/A"
    pbv = f"{s['pbv']:.1f}x" if s.get('pbv') else "N/A"
    mcap = f"{s['market_cap']/1e12:.1f}T" if s.get('market_cap') else "N/A"
    msg += f"P/E: `{pe}` | PBV: `{pbv}` | MCap: `Rp{mcap}`\n\n"

    # TECHNICAL PULSE
    msg += f"📉 *[TECHNICAL PULSE]*\n"
    msg += f"Phase: `{s['wyckoff_phase']}`\n"
    msg += f"Vola: `{'SQUEEZE (Pending Expansion)' if s['is_squeeze'] else 'Normal'}`\n\n"
    
    # SMART MONEY PROXY
    bee_bar = draw_progress_bar(s['bee_score'])
    msg += f"🧠 *[SMART MONEY PROXY]*\n"
    msg += f"`{bee_bar}` {s['bee_score']}/10\n"
    msg += f"_(PVT + CMF + Volume Anomaly)_\n\n"
    
    # QUANT CONSENSUS
    msg += f"💬 *[QUANT CONSENSUS]*\n"
    msg += f"_{narrative}_\n\n"
    
    # EXECUTION RULES + POSITION SIZING
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
    
    # SECTOR WARNING
    if sector_warnings:
        msg += f"\n⚠️ *[EXPOSURE WARNING]*\n"
        for w in sector_warnings:
            msg += f"_{w}_\n"
    
    # HEALTH CHECK
    liq = health.get('liquidity', 'N/A')
    news = health.get('news_risk', 'LOW')
    msg += f"\n🏥 *[HEALTH CHECK]*\n"
    msg += f"Liquidity: `{liq}` | News Risk: `{news}`\n"
    
    # CONVICTION METRIC (Weighted)
    conv_bar = draw_progress_bar(score, max_val=10)
    msg += f"\n⚖️ *[CONVICTION METRIC]*\n"
    msg += f"`{conv_bar}` {score:.1f}/10\n"
    
    # Show weighted component breakdown
    if isinstance(layers, dict) and 'SmartMoney' in layers:
        msg += f"SmartMoney(35%): `{layers.get('SmartMoney', 0):.1f}` | "
        msg += f"Trend(25%): `{layers.get('Trend', 0):.1f}` | "
        msg += f"RSI/Phase(20%): `{layers.get('RSI/Phase', 0):.1f}`\n"
        msg += f"Volatility(15%): `{layers.get('Volatility', 0):.1f}` | "
        msg += f"Macro(5%): `{layers.get('Macro', 0):.1f}`\n"
    else:
        layer_str = " ".join([f"✓{l}" if l in layers else f"✗{l}" for l in ['RSI', 'MACD', 'MA200', 'SmartMoney', 'Phase', 'Volatility']])
        msg += f"Triggers: {layer_str}\n"
    
    # BACKTEST STATS
    if bt_stats:
        msg += f"\n📊 *[HISTORICAL STATS (2Y)]*\n"
        msg += f"Winrate: `{bt_stats['winrate']}%` | PF: `{bt_stats['profit_factor']}` | MaxDD: `{bt_stats['max_drawdown_r']}R` (N={bt_stats['total_trades']})\n"
    
    # PLAYBOOK
    msg += f"\n📖 *[PLAYBOOK]*\n"
    if direction == "BUY":
        msg += "_Buy near lower bound of entry zone. Scale-out 50% at TP1, trail stop above swing low for remainder._\n"
    else:
        msg += "_Exit at market or scale-out. Re-enter only if price reclaims above invalidation level._\n"
    
    msg += f"\n⚠️ _Probabilistic edge, not a guarantee. False breakouts occur._\n"
    msg += "┗━━━━━━━━━━━━━━━━━━━━┛\n"
    
    return msg

def format_status_report(all_stocks_status, ihsg_data=None):
    bullish_stocks = [s for s in all_stocks_status if s['trend'] == 'BULLISH']
    bearish_stocks = [s for s in all_stocks_status if s['trend'] == 'BEARISH']
    
    msg = "┏━━━━━━━━━━━━━━━━━━━━┓\n"
    msg += f"📊 *[QUANTITATIVE INTELLIGENCE REPORT]*\n"
    msg += f"📅 {datetime.now(TIMEZONE).strftime('%d %b %Y, %H:%M WIB')}\n"
    msg += f"📎 Core: Quant Alpha V9 Pro | Institutional Screener\n"
    msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    # MARKET REGIME
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
    
    # FORWARD TEST STATS (if file exists)
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
    except:
        pass
    
    # BULLISH ZONE
    msg += f"📈 *[BULLISH DYNAMICS]*\n"
    if not bullish_stocks:
        msg += "_No assets in markup phase._\n"
    else:
        for i, s in enumerate(bullish_stocks, 1):
            sym = s['symbol'].split('.')[0]
            bee_bar = draw_progress_bar(s.get('bee_score', 0), max_val=5)
            pattern = f" | {s['pattern']}" if s.get('pattern') else ""
            msg += f"{i}. {sym} | `{format_rp(s['close'])}` | RSI:{int(s['rsi'])}{pattern}\n"
            msg += f"   Strength: `{bee_bar}` {s.get('wyckoff_phase', 'N/A')}\n"
            msg += f"   S: `{format_rp(s.get('support', 0))}` | R: `{format_rp(s.get('resistance', 0))}`\n"
            
    # BEARISH ZONE (Top 5)
    msg += f"\n📉 *[BEARISH DYNAMICS (Top 5)]*\n"
    if not bearish_stocks:
        msg += "_No assets in markdown phase._\n"
    else:
        for i, s in enumerate(bearish_stocks[:5], 1):
            sym = s['symbol'].split('.')[0]
            msg += f"{i}. {sym} | `{format_rp(s['close'])}` | RSI:{int(s['rsi'])}\n"
            msg += f"   S: `{format_rp(s.get('support', 0))}` | R: `{format_rp(s.get('resistance', 0))}`\n"
            
    # SMART MONEY RANKING
    msg += f"\n🔍 *[SMART MONEY PROXY]*\n"
    all_sorted = sorted(all_stocks_status, key=lambda x: x.get('bee_score', 0), reverse=True)
    top = [s for s in all_sorted if s.get('bee_score', 0) >= 4][:5]
    if top:
        for s in top:
            sym = s['symbol'].split('.')[0]
            bee_bar = draw_progress_bar(s.get('bee_score', 0), max_val=10)
            msg += f"• *{sym}*: `{bee_bar}` {s['bee_score']}/10\n"
    else:
        msg += "_Institutional flow is dormant._\n"
    
    # SYSTEM SUMMARY
    msg += f"\n⚙️ *[SYSTEM SUMMARY]*\n"
    msg += f"✓ Universe: {len(all_stocks_status)} | Bullish: {len(bullish_stocks)} | Bearish: {len(bearish_stocks)}\n"
    
    msg += "\n🔬 *[QUANT CONSENSUS]*: Scan complete. Next check in 2 hours.\n"
    msg += "┗━━━━━━━━━━━━━━━━━━━━┛\n"
    
    return msg

# ============================================================
# TELEGRAM
# ============================================================

async def send_telegram(message, photo_path=None):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram Token missing. Log:\n", message)
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
        else:
            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode='Markdown')
        print("Telegram sent!")
    except Exception as e:
        print(f"Telegram error: {e}")


# ============================================================
# MAIN
# ============================================================

async def main():
    print(f"=== Quant Alpha Engine V9 Pro ({datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M')}) ===")
    config = load_config()
    state = get_last_state()
    
    broker = MockBroker(initial_equity=config.get('portfolio', {}).get('initial_equity', 50000000))
    logger = GoogleSheetsLogger()
    
    # Check Exits for Open Positions first
    print("[EXECUTION] Checking Open Positions for Exit signals...")
    open_positions = broker.get_open_positions().copy()
    for sym, pos in open_positions.items():
        df = fetch_data(sym, config)
        if df is None: continue
        df = calculate_indicators(df, config)
        
        last_row = df.iloc[-1]
        close = last_row['Close']
        rsi = last_row.get(f"RSI_{config['indicators']['rsi_length']}", 50)
        atr = last_row.get(f"ATRr_{config['indicators']['atr_period']}", close * 0.02)
        
        entry_date = datetime.fromisoformat(pos['entry_date'])
        days_held = (datetime.now(TIMEZONE) - entry_date).days
        
        # Determine trailing stop based on recent swing low
        swing_low = df['Low'].tail(5).min()
        trailing_sl = swing_low - (atr * 0.5)
        
        exit_reason = None
        sell_lot = None
        
        # 1. Time decay
        if days_held > 21:
            exit_reason = "Time Decay (>21 days)"
        # 2. Hard Stop Loss / Trailing
        elif close <= trailing_sl and pos.get('tp1_hit', False):
            exit_reason = "Trailing SL Hit"
        # 3. Take Profit 1 (50%)
        elif close >= (pos['avg_price'] + atr * 2) and not pos.get('tp1_hit', False):
            exit_reason = "TP1 Hit (Scale Out 50%)"
            sell_lot = pos['quantity'] // 2
        # 4. Overbought / TP2
        elif rsi >= 75:
            exit_reason = "Overbought (RSI >= 75)"
        
        if exit_reason:
            print(f"[{sym}] EXIT TRIGGERED: {exit_reason} at {format_rp(close)}")
            success, res = broker.execute_sell(sym, close, lot=sell_lot, reason=exit_reason)
            if success:
                logger.log_trade(sym, "SELL", close, res['qty'], reason=exit_reason, pnl=res['realized_pnl'])
                
    # Fetch IHSG macro data + regime
    print("[IHSG] Fetching macro data & regime...")
    ihsg_data = fetch_ihsg(config)
    
    regime = ihsg_data.get('regime', 'UNKNOWN') if ihsg_data else 'UNKNOWN'
    regime_label = ihsg_data.get('regime_label', 'N/A') if ihsg_data else 'N/A'
    print(f"[REGIME] {regime_label}")
    
    signals_sent_today = []
    all_stocks_status = []
    
    for symbol in config['stocks']:
        df = fetch_data(symbol, config)
        if df is not None:
            df = calculate_indicators(df, config)
            signal_data, status_summary, reason = evaluate_signals(symbol, df, config, ihsg_data=ihsg_data)
            
            # Always track status for reporting, filter out invalid/NaN data
            if status_summary is not None:
                all_stocks_status.append(status_summary)
            else:
                print(f"[{symbol}] {reason}")
                continue

            if signal_data:
                sig_type = signal_data['type']
                if check_cooldown(symbol, sig_type, state, config):
                    print(f"[{symbol}] Alert '{sig_type}' blocked (Cooldown)")
                    continue
                
                # --- V9 PRO: Multi-layer enrichment ---
                s = signal_data['data']
                
                # Health Check
                hc = health_check(df, config)
                
                # Weekly multi-timeframe validation
                weekly = fetch_weekly_trend(symbol)
                weekly_bullish = weekly.get('weekly_bullish') if weekly else None
                
                # V9 PRO: Position Sizing based on Conviction Score
                lot, pos_value, risk_pct_tier = calculate_position_size(s['close'], s['stop_loss'], signal_data['score'], config)
                s['risk_pct'] = risk_pct_tier
                
                # Regime-based size reduction
                if regime == 'CHOPPY':
                    reduce_pct = config.get('regime', {}).get('choppy_reduce_pct', 30)
                    lot = int(lot * (1 - reduce_pct / 100))
                    lot = (lot // 100) * 100
                    pos_value = lot * s['close']
                
                # Sector exposure check
                sector_warnings = check_sector_exposure(symbol, signals_sent_today, config)
                
                # Auto-Trade Execution
                if sig_type == "AUTO_TRADE_BUY" and not sector_warnings and hc['liquidity'] != 'LOW':
                    print(f"[{symbol}] Executing AUTO-TRADE BUY...")
                    success, res = broker.execute_buy(symbol, s['close'], lot, reason=f"Conviction {signal_data['score']:.1f}")
                    if success:
                        logger.log_trade(symbol, "BUY", s['close'], lot, conviction=signal_data['score'], reason="Auto-Trade Signal")
                    else:
                        print(f"[{symbol}] Execution Failed: {res}")
                
                # Backtest stats
                bt_stats = run_backtest_stats(symbol, df, config)
                
                # Build extra context
                extra = {
                    'lot': lot,
                    'position_value': pos_value,
                    'health': hc,
                    'regime': regime,
                    'regime_label': regime_label,
                    'weekly_bullish': weekly_bullish,
                    'backtest_stats': bt_stats,
                    'sector_warnings': sector_warnings
                }
                
                msg = format_alert(signal_data, extra=extra)
                
                photo_path = None
                if signal_data['confidence'] == 'HIGH':
                    try:
                        photo_path = generate_chart(symbol, df, config)
                    except Exception as e:
                        print(f"[{symbol}] Chart error: {e}")
                
                await send_telegram(msg, photo_path=photo_path)
                signals_sent_today.append(symbol)
                
                # Log to forward test CSV
                log_forward_test(symbol, signal_data, lot, pos_value, hc, regime)
                
                state[symbol] = {
                    'signal': sig_type,
                    'time': datetime.now(TIMEZONE).isoformat()
                }
                print(f"[{symbol}] \u26a1 {sig_type} (Score: {signal_data['score']:.0f}/10 | Lot: {lot:,})")
            else:
                print(f"[{symbol}] {reason}")
            
    # Always send status report
    now = datetime.now(TIMEZONE)
    if config['signals']['send_status_report_if_no_alerts']:
        if len(all_stocks_status) > 0:
            print(f"\n>> Session {now.hour}:00 WIB. Sending Market Status Report...")
            report = format_status_report(all_stocks_status, ihsg_data=ihsg_data)
            await send_telegram(report)
            
    # Log portfolio snapshot
    logger.log_portfolio(broker.get_balance(), len(broker.get_open_positions()))
            
    save_state(state)
    print("=== Scan Complete ===")

if __name__ == "__main__":
    asyncio.run(main())
