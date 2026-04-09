import os
import json
import asyncio
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

TIMEZONE = pytz.timezone('Asia/Jakarta')
STATE_FILE = "last_signals.json"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

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
            
        return df
    except Exception as e:
        print(f"[{symbol}] Fetch error: {e}")
        return None

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
    
    # Bollinger Bands
    df.ta.bbands(length=ind_cfg['bb_period'], std=ind_cfg['bb_std'], append=True)
    
    # Volume Average
    df['Vol_Avg'] = df['Volume'].rolling(window=ind_cfg['volume_avg_period']).mean()
    
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
# V5 MULTI-CONFIRMATION SCORING ENGINE
# ============================================================

def evaluate_signals(symbol, df, config):
    last_row = df.iloc[-1]
    prev_row = df.iloc[-2] if len(df) > 1 else last_row
    
    ind_cfg = config['indicators']
    sig_cfg = config['signals']
    ma50_col = f"SMA_{ind_cfg['ma_short']}"
    ma200_col = f"SMA_{ind_cfg['ma_long']}"
    rsi_col = f"RSI_{ind_cfg['rsi_length']}"
    macd_col = f"MACD_{ind_cfg['macd_fast']}_{ind_cfg['macd_slow']}_{ind_cfg['macd_signal']}"
    macd_sig_col = f"MACDs_{ind_cfg['macd_fast']}_{ind_cfg['macd_slow']}_{ind_cfg['macd_signal']}"
    macd_hist_col = f"MACDh_{ind_cfg['macd_fast']}_{ind_cfg['macd_slow']}_{ind_cfg['macd_signal']}"
    bb_lower_col = f"BBL_{ind_cfg['bb_period']}_{ind_cfg['bb_std']}"
    bb_upper_col = f"BBU_{ind_cfg['bb_period']}_{ind_cfg['bb_std']}"
    
    try:
        close = last_row['Close']
        prev_close = prev_row['Close']
        volume = last_row['Volume']
        vol_avg = last_row['Vol_Avg']
        rsi = last_row[rsi_col]
        ma50 = last_row[ma50_col]
        ma200 = last_row[ma200_col]
        pct_1d = last_row['Pct_Change_1D']
        pct_5d = last_row['Pct_Change_5D']
        drop_peak = last_row['Drop_From_Peak_Pct']
        support = last_row['Support_Level']
        resistance = last_row['Resistance_Level']
    except KeyError:
        return None, "Indicators incomplete."
        
    # Safe access for optional indicators
    macd_val = last_row.get(macd_col)
    macd_sig = last_row.get(macd_sig_col)
    macd_hist = last_row.get(macd_hist_col)
    bb_lower = last_row.get(bb_lower_col)
    bb_upper = last_row.get(bb_upper_col)
    
    if pd.isna(rsi) or pd.isna(ma50) or pd.isna(ma200) or pd.isna(vol_avg) or vol_avg == 0:
        return None, "Data NaN"

    vol_ratio = volume / vol_avg
    is_downtrend_flag = is_downtrend(df, config)
    candle_pattern = detect_candles(df)
    
    # ========== SCORING: BUY side ==========
    buy_score = 0
    buy_layers = {}
    
    # Layer 1: RSI Oversold
    if rsi < ind_cfg['rsi_oversold']:
        buy_score += 1
        buy_layers['RSI'] = f"Oversold ({rsi:.0f})"
    elif rsi < 40:
        buy_score += 0.5
        buy_layers['RSI'] = f"Low Zone ({rsi:.0f})"
    
    # Layer 2: MA50 Support Test
    if close > ma200 and (abs(close - ma50) / ma50) <= ind_cfg['price_dip_touch_ma50']:
        buy_score += 1
        buy_layers['MA50'] = "Support Test"
    
    # Layer 3: MA200 Uptrend
    if close > ma200:
        buy_score += 1
        buy_layers['MA200'] = "Uptrend Confirmed"
    
    # Layer 4: Volume Confirmation
    if vol_ratio >= ind_cfg['volume_spike_strong']:
        buy_score += 1
        buy_layers['Volume'] = f"Spike ({vol_ratio:.1f}x)"
    elif vol_ratio >= ind_cfg['volume_spike_mild']:
        buy_score += 0.5
        buy_layers['Volume'] = f"Above Avg ({vol_ratio:.1f}x)"
    
    # Layer 5: MACD Bullish
    if macd_hist is not None and not pd.isna(macd_hist):
        prev_hist = prev_row.get(macd_hist_col)
        if macd_hist > 0:
            buy_score += 1
            buy_layers['MACD'] = "Bullish Momentum"
        elif prev_hist is not None and not pd.isna(prev_hist) and macd_hist > prev_hist:
            buy_score += 0.5
            buy_layers['MACD'] = "Momentum Improving"
    
    # Layer 6: Bollinger Bands — Near Lower Band
    if bb_lower is not None and not pd.isna(bb_lower):
        if close <= bb_lower:
            buy_score += 1
            buy_layers['BB'] = "Below Lower Band"
        elif (close - bb_lower) / close <= 0.02:
            buy_score += 0.5
            buy_layers['BB'] = "Near Lower Band"
    
    # Layer 7: Near Support Level
    if (abs(close - support) / close) <= 0.03:
        buy_score += 1
        buy_layers['S/R'] = f"Near Support ({support:,.0f})"
    
    # Layer 8: Candlestick Pattern
    if candle_pattern and any(p in candle_pattern for p in ["Hammer", "Engulfing"]):
        buy_score += 1
        buy_layers['Candle'] = candle_pattern
    elif candle_pattern:
        buy_score += 0.5
        buy_layers['Candle'] = candle_pattern

    # ========== SCORING: SELL side ==========
    sell_score = 0
    sell_layers = {}
    
    # Layer 1: RSI Overbought
    if rsi > ind_cfg['rsi_overbought']:
        sell_score += 1
        sell_layers['RSI'] = f"Overbought ({rsi:.0f})"
    elif rsi > 60:
        sell_score += 0.5
        sell_layers['RSI'] = f"High Zone ({rsi:.0f})"
    
    # Layer 2: MA200 Breakdown
    if close < ma200:
        sell_score += 1
        sell_layers['MA200'] = "Below MA200"
    if close < ma200 and prev_close > ma200:
        sell_score += 1  # Extra point for fresh breakdown
        sell_layers['MA200'] = "Fresh Breakdown!"
    
    # Layer 3: Volume on Sell
    if vol_ratio >= ind_cfg['volume_spike_mild'] and pct_1d < 0:
        sell_score += 1
        sell_layers['Volume'] = f"Distribution ({vol_ratio:.1f}x)"
    
    # Layer 4: MACD Bearish
    if macd_hist is not None and not pd.isna(macd_hist):
        if macd_hist < 0:
            sell_score += 1
            sell_layers['MACD'] = "Bearish Momentum"
    
    # Layer 5: Bollinger Bands — Near Upper Band
    if bb_upper is not None and not pd.isna(bb_upper):
        if close >= bb_upper:
            sell_score += 1
            sell_layers['BB'] = "Above Upper Band"
    
    # Layer 6: Near Resistance Level
    if (abs(close - resistance) / close) <= 0.03:
        sell_score += 1
        sell_layers['S/R'] = f"Near Resistance ({resistance:,.0f})"
    
    # Determine dominant direction & signal
    signal = None
    confidence = None
    desc = None
    layers = {}
    score = 0
    direction = "NEUTRAL"
    
    min_watchlist = sig_cfg['min_conviction_watchlist']
    min_alert = sig_cfg['min_conviction_alert']
    
    if buy_score >= min_watchlist and buy_score > sell_score and not is_downtrend_flag:
        direction = "BUY"
        score = buy_score
        layers = buy_layers
        
        if score >= min_alert:
            signal = "STRONG_BUY"
            confidence = "HIGH"
            desc = "Multiple confirmations align for potential entry."
        else:
            signal = "WATCHLIST_BUY"
            confidence = "MEDIUM"
            desc = "Moderate buy signals. Monitor for additional confirmation."
            
    elif sell_score >= min_watchlist and sell_score > buy_score:
        direction = "SELL"
        score = sell_score
        layers = sell_layers
        
        if score >= min_alert:
            signal = "STRONG_SELL"
            confidence = "HIGH"
            desc = "Multiple bearish confirmations. Take profit / cut loss recommended."
        else:
            signal = "WATCHLIST_SELL"
            confidence = "MEDIUM"
            desc = "Moderate sell signals. Consider risk management."

    # Status Compilation
    status_summary = {
        'symbol': symbol,
        'close': close,
        'rsi': rsi,
        'ma200': ma200,
        'ma50': ma50,
        'vol': volume,
        'vol_ratio': vol_ratio,
        'pct_1d': pct_1d,
        'pattern': candle_pattern,
        'macd_hist': macd_hist if macd_hist is not None and not pd.isna(macd_hist) else 0,
        'bb_lower': bb_lower if bb_lower is not None and not pd.isna(bb_lower) else 0,
        'bb_upper': bb_upper if bb_upper is not None and not pd.isna(bb_upper) else 0,
        'support': support,
        'resistance': resistance,
        'buy_score': buy_score,
        'sell_score': sell_score,
        'trend': 'BULLISH' if close > ma200 else 'BEARISH'
    }

    if signal:
        result = {
            'type': signal,
            'confidence': confidence,
            'desc': desc,
            'direction': direction,
            'score': score,
            'layers': layers,
            'data': status_summary
        }
        return result, "SIGNAL_DETECTED"
    
    return None, "HOLD"

# ============================================================
# CHART GENERATOR (V5 — with BB + MACD panels)
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
    bb_mid_col = f"BBM_{ind_cfg['bb_period']}_{ind_cfg['bb_std']}"
    
    apds = []
    
    # MA Lines
    if ma_s_col in df_plot.columns:
        apds.append(mpf.make_addplot(df_plot[ma_s_col], color='dodgerblue', width=1.0))
    if ma_l_col in df_plot.columns:
        apds.append(mpf.make_addplot(df_plot[ma_l_col], color='red', width=1.2))
    
    # Bollinger Bands overlay
    if bb_upper_col in df_plot.columns and bb_lower_col in df_plot.columns:
        apds.append(mpf.make_addplot(df_plot[bb_upper_col], color='gray', width=0.5, linestyle='dashed'))
        apds.append(mpf.make_addplot(df_plot[bb_lower_col], color='gray', width=0.5, linestyle='dashed'))
    
    # RSI Panel (panel 1)
    if rsi_col in df_plot.columns:
        apds.append(mpf.make_addplot(df_plot[rsi_col], panel=1, color='purple', width=0.8, secondary_y=False))
    
    # MACD Histogram (panel 2)
    if macd_hist_col in df_plot.columns:
        colors = ['green' if v >= 0 else 'red' for v in df_plot[macd_hist_col].fillna(0)]
        apds.append(mpf.make_addplot(df_plot[macd_hist_col], panel=2, type='bar', color=colors, secondary_y=False))

    file_path = f"{symbol.split('.')[0]}_chart.png"
    
    s = mpf.make_mpf_style(base_mpf_style='charles', gridstyle='', facecolor='#f5f5f5')
    
    mpf.plot(df_plot, type='candle', style=s, 
             addplot=apds if apds else None,
             title=f"\n{symbol} — Technical Analysis (V5)",
             volume=True, 
             savefig=file_path,
             figratio=(14, 10),
             tight_layout=True)
             
    return file_path

# ============================================================
# FORMATTERS
# ============================================================

def format_alert(signal_data):
    s = signal_data['data']
    sig = signal_data['type']
    conf = signal_data['confidence']
    desc = signal_data['desc']
    direction = signal_data['direction']
    score = signal_data['score']
    layers = signal_data['layers']
    
    format_rp = lambda n: f"Rp {n:,.0f}".replace(',', '.')
    format_vol = lambda n: f"{n/1_000_000:.1f}M" if n >= 1e6 else f"{n/1_000:.1f}K"
    
    sym_name = s['symbol'].split('.')[0]
    
    if direction == "BUY":
        if conf == "HIGH":
            icon = "🚨"
            alert_title = f"{icon} STRONG BUY SIGNAL"
        else:
            icon = "👀"
            alert_title = f"{icon} WATCHLIST — BUY SIGNAL"
    else:
        if conf == "HIGH":
            icon = "🔴"
            alert_title = f"{icon} STRONG SELL SIGNAL"
        else:
            icon = "⚠️"
            alert_title = f"{icon} WATCHLIST — SELL SIGNAL"
        
    msg = f"*{alert_title}*\n\n"
    msg += f"🏢 Symbol: *{sym_name}*\n"
    
    pct_sign = "↑" if s['pct_1d'] > 0 else "↓"
    msg += f"💵 Price: {format_rp(s['close'])} ({pct_sign} {abs(s['pct_1d']):.1f}%)\n"
    msg += f"📊 Volume: {format_vol(s['vol'])} ({s['vol_ratio']*100:.0f}% of Avg)\n"
    msg += f"📈 RSI: {s['rsi']:.1f}\n"
    msg += f"📏 MA200: {format_rp(s['ma200'])}\n\n"
    
    # Conviction Score
    msg += f"🎯 Conviction Score: *{score:.0f}/8 ({conf})*\n"
    
    # Layer detail
    all_layers = ['RSI', 'MA50', 'MA200', 'Volume', 'MACD', 'BB', 'S/R', 'Candle']
    layer_str = ""
    for l in all_layers:
        if l in layers:
            layer_str += f"✓ {l} "
        else:
            layer_str += f"✗ {l} "
    msg += f"{layer_str}\n\n"
    
    # Detail per layer
    for key, val in layers.items():
        msg += f"  • {key}: {val}\n"
    
    msg += f"\n💡 Insights: {desc}\n"
    
    return msg

def format_status_report(all_stocks_status):
    bullish_stocks = [s for s in all_stocks_status if s['trend'] == 'BULLISH']
    bearish_stocks = [s for s in all_stocks_status if s['trend'] == 'BEARISH']
    
    format_rp = lambda n: f"Rp {n:,.0f}".replace(',', '.')
    
    msg = f"📊 *MARKET STATUS REPORT — {datetime.now(TIMEZONE).strftime('%d %b %Y, %H:%M WIB')}*\n"
    msg += "=" * 40 + "\n\n"
    
    # BULLISH
    msg += f"📈 *BULLISH ZONE (Price > MA200):*\n"
    if not bullish_stocks:
        msg += "— No stocks in bullish zone —\n"
    for i, s in enumerate(bullish_stocks, 1):
        sym = s['symbol'].split('.')[0]
        rsi_status = "ACCUMULATION" if s['rsi'] < 40 else "STABLE"
        macd_txt = "↑" if s.get('macd_hist', 0) > 0 else "↓"
        pattern_txt = f" | {s['pattern']}" if s.get('pattern') else ""
        msg += f"{i}. {sym} | {format_rp(s['close'])} | RSI: {s['rsi']:.0f} | MACD: {macd_txt} | {rsi_status}{pattern_txt}\n"
            
    msg += f"\n📉 *BEARISH ZONE (Price < MA200):*\n"
    if not bearish_stocks:
        msg += "— No stocks in bearish zone —\n"
    for i, s in enumerate(bearish_stocks, 1):
        sym = s['symbol'].split('.')[0]
        macd_txt = "↑" if s.get('macd_hist', 0) > 0 else "↓"
        pattern_txt = f" | {s['pattern']}" if s.get('pattern') else ""
        msg += f"{i}. {sym} | {format_rp(s['close'])} | RSI: {s['rsi']:.0f} | MACD: {macd_txt} | BEARISH{pattern_txt}\n"
            
    msg += f"\n⚙️ *SUMMARY:*\n"
    msg += f"✓ Universe: {len(all_stocks_status)} Stocks\n"
    msg += f"✓ Bullish: {len(bullish_stocks)} | Bearish: {len(bearish_stocks)}\n\n"
    
    # Top Conviction Stocks
    all_sorted = sorted(all_stocks_status, key=lambda x: max(x.get('buy_score', 0), x.get('sell_score', 0)), reverse=True)
    top_3 = [s for s in all_sorted if max(s.get('buy_score', 0), s.get('sell_score', 0)) >= 2][:3]
    if top_3:
        msg += "🔍 *TOP CONVICTION:*\n"
        for s in top_3:
            sym = s['symbol'].split('.')[0]
            bs = s.get('buy_score', 0)
            ss = s.get('sell_score', 0)
            if bs >= ss:
                msg += f"  • {sym}: Buy Score {bs:.0f}/8\n"
            else:
                msg += f"  • {sym}: Sell Score {ss:.0f}/8\n"
        msg += "\n"
    
    msg += "📌 *CONCLUSION:*\n"
    msg += "• Monitoring remains active for next session.\n"
    
    return msg

# ============================================================
# TELEGRAM & MAIN
# ============================================================

async def send_telegram(message, photo_path=None):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram Token missing. Log:\n", message)
        return
        
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        if photo_path and os.path.exists(photo_path):
            # Telegram caption max 1024 chars — if too long, send separately
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

async def main():
    print(f"=== Stock Notifier V5 (Multi-Confirmation) ({datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M')}) ===")
    config = load_config()
    state = get_last_state()
    
    signals_sent_today = []
    all_stocks_status = []
    
    for symbol in config['stocks']:
        df = fetch_data(symbol, config)
        if df is not None:
            df = calculate_indicators(df, config)
            signal_data, reason = evaluate_signals(symbol, df, config)
            candle_pattern = detect_candles(df)
            
            # Always add to status report
            last_row = df.iloc[-1]
            ma200_col = f"SMA_{config['indicators']['ma_long']}"
            macd_hist_col = f"MACDh_{config['indicators']['macd_fast']}_{config['indicators']['macd_slow']}_{config['indicators']['macd_signal']}"
            
            macd_h = last_row.get(macd_hist_col)
            
            all_stocks_status.append({
                'symbol': symbol,
                'close': last_row['Close'],
                'rsi': last_row[f"RSI_{config['indicators']['rsi_length']}"],
                'ma200': last_row[ma200_col],
                'pct_1d': last_row['Pct_Change_1D'],
                'pattern': candle_pattern,
                'macd_hist': macd_h if macd_h is not None and not pd.isna(macd_h) else 0,
                'buy_score': signal_data['score'] if signal_data and signal_data['direction'] == 'BUY' else 0,
                'sell_score': signal_data['score'] if signal_data and signal_data['direction'] == 'SELL' else 0,
                'trend': 'BULLISH' if last_row['Close'] > last_row[ma200_col] else 'BEARISH'
            })

            if signal_data:
                sig_type = signal_data['type']
                if check_cooldown(symbol, sig_type, state, config):
                    print(f"[{symbol}] Alert '{sig_type}' blocked (Cooldown < 6h)")
                    continue
                    
                msg = format_alert(signal_data)
                
                # Generate chart only for HIGH conviction (STRONG signals)
                photo_path = None
                if signal_data['confidence'] == 'HIGH':
                    try:
                        photo_path = generate_chart(symbol, df, config)
                    except Exception as e:
                        print(f"[{symbol}] Chart error: {e}")
                
                await send_telegram(msg, photo_path=photo_path)
                signals_sent_today.append(symbol)
                
                state[symbol] = {
                    'signal': sig_type,
                    'time': datetime.now(TIMEZONE).isoformat()
                }
                print(f"[{symbol}] ⚡ {sig_type} (Score: {signal_data['score']:.0f}/8)")
            else:
                print(f"[{symbol}] {reason}")
            
    # Always send status report
    now = datetime.now(TIMEZONE)
    if config['signals']['send_status_report_if_no_alerts']:
        if len(all_stocks_status) > 0:
            print(f"\n>> Session {now.hour}:00 WIB. Sending Market Status Report...")
            report = format_status_report(all_stocks_status)
            await send_telegram(report)
            
    save_state(state)
    print("=== Scan Complete ===")

if __name__ == "__main__":
    asyncio.run(main())
