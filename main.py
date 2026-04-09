import os
import json
import asyncio
from datetime import datetime, timedelta
import pytz
import yfinance as yf
import pandas as pd
import pandas_ta as ta
from telegram import Bot

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
        print(f"Gagal menyimpan state: {e}")

def fetch_data(symbol, config):
    print(f"[{symbol}] Mengambil data...")
    try:
        stock = yf.Ticker(symbol)
        df = stock.history(period="1y", interval="1d")
        if df.empty:
            print(f"[{symbol}] Data kosong!")
            return None
            
        # Get peak price for looking back
        lookback = config['signals']['price_peak_lookback_days']
        if len(df) >= lookback:
            df['Peak_Price'] = df['High'].rolling(window=lookback, min_periods=1).max()
        else:
            df['Peak_Price'] = df['High'].rolling(window=len(df), min_periods=1).max()
            
        return df
    except Exception as e:
        print(f"[{symbol}] Gagal mengambil data: {e}")
        return None

def calculate_indicators(df, config):
    ind_cfg = config['indicators']
    df = df.sort_index()
    
    # RSI
    df.ta.rsi(length=ind_cfg['rsi_length'], append=True)
    df['Pct_Change_1D'] = df['Close'].pct_change() * 100
    df['Pct_Change_5D'] = df['Close'].pct_change(periods=5) * 100
    
    # Drops from Peak
    df['Drop_From_Peak_Pct'] = ((df['Peak_Price'] - df['Close']) / df['Peak_Price']) * 100
    
    # MA
    df.ta.sma(length=ind_cfg['ma_short'], append=True)
    df.ta.sma(length=ind_cfg['ma_long'], append=True)
    
    # Volume Rata-rata
    df['Vol_Avg'] = df['Volume'].rolling(window=ind_cfg['volume_avg_period']).mean()
    
    return df

def is_downtrend(df, config):
    # Check if close < MA200 for N consecutive days
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

def evaluate_signals(symbol, df, config):
    last_row = df.iloc[-1]
    prev_row = df.iloc[-2] if len(df) > 1 else last_row
    
    ind_cfg = config['indicators']
    ma50_col = f"SMA_{ind_cfg['ma_short']}"
    ma200_col = f"SMA_{ind_cfg['ma_long']}"
    rsi_col = f"RSI_{ind_cfg['rsi_length']}"
    
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
    except KeyError:
        return None, "Indikator belum lengkap."
        
    if pd.isna(rsi) or pd.isna(ma50) or pd.isna(ma200) or pd.isna(vol_avg) or vol_avg == 0:
        return None, "Data NaN"

    vol_ratio = volume / vol_avg
    is_downtrend_flag = is_downtrend(df, config)
    
    # RULE 1: Noise Filter
    if abs(pct_1d) < (ind_cfg['price_breakout_min']*100) and vol_ratio < ind_cfg['volume_spike_mild']:
        return None, "NOISE"
        
    signal = None
    confidence = None
    desc = None
    
    # SIGNALS 
    
    # 1. VOLUME BREAKOUT (HIGH)
    if pct_1d >= (ind_cfg['price_breakout_min']*100) and vol_ratio >= ind_cfg['volume_spike_strong'] and close > ma200:
        signal = "VOLUME_BREAKOUT"
        confidence = "HIGH"
        desc = "Institusi/Bandar kemungkinan sedang masuk."
        
    # 5. BREAKDOWN (SELL) (HIGH)
    elif close < ma200 and prev_close > ma200 and vol_ratio > 1.3:
        signal = "BREAKDOWN"
        confidence = "HIGH"
        desc = "Trend reversal, break below MA200."
        
    # 2. BUY ON DIP (MEDIUM-HIGH)
    elif (abs(close - ma50) / ma50) <= ind_cfg['price_dip_touch_ma50'] and rsi > 30 and close > ma200 and vol_ratio >= 0.9:
        if not is_downtrend_flag:
            signal = "BUY_ON_DIP"
            confidence = "MEDIUM-HIGH"
            desc = "Support MA50 ditest, koreksi sehat."
            
    # 3. RSI OVERSOLD (MEDIUM)
    elif rsi < ind_cfg['rsi_oversold'] and close > ma200 and vol_ratio > ind_cfg['volume_spike_mild'] and drop_peak < (ind_cfg['price_drop_max']*100):
        if not is_downtrend_flag:
            signal = "RSI_OVERSOLD"
            confidence = "MEDIUM"
            desc = "Kondisi teknikal oversold di jalur Uptrend."

    # 4. POTENTIAL REBOUND (💎 MURAH & BERPOTENSI)
    # Harga nempel MA200 + Ada tanda perlawanan (pct_1d > 0)
    elif (abs(close - ma200) / ma200) <= 0.03 and pct_1d > 0 and close > ma200:
        signal = "POTENTIAL_REBOUND"
        confidence = "HIGH"
        desc = "Saham di area Support kuat MA200 (Murah) & mulai ada pantulan!"

    # 4. RSI OVERBOUGHT (SELL) (MEDIUM)
    elif rsi > ind_cfg['rsi_overbought'] and pct_5d > (ind_cfg['price_rise_5day_min']*100) and vol_ratio < 1.0:
        signal = "RSI_OVERBOUGHT"
        confidence = "MEDIUM"
        desc = "Rentan koreksi (Overbought), pertimbangkan taking profit."

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
        'trend': 'BULLISH' if close > ma200 else 'BEARISH'
    }

    if signal:
        result = {
            'type': signal,
            'confidence': confidence,
            'desc': desc,
            'data': status_summary
        }
        return result, "SIGNAL_DETECTED"
    
    return None, "HOLD"

def format_alert(signal_data):
    s = signal_data['data']
    sig = signal_data['type']
    conf = signal_data['confidence']
    desc = signal_data['desc']
    
    format_rp = lambda n: f"Rp {n:,.0f}".replace(',', '.')
    format_vol = lambda n: f"{n/1_000_000:.1f}M" if n >= 1e6 else f"{n/1_000:.1f}K"
    
    sym_name = s['symbol'].split('.')[0]
    
    if sig in ["VOLUME_BREAKOUT", "BUY_ON_DIP", "RSI_OVERSOLD", "POTENTIAL_REBOUND"]:
        if sig == "VOLUME_BREAKOUT": icon = "🚨"
        elif sig == "BUY_ON_DIP": icon = "📍"
        elif sig == "RSI_OVERSOLD": icon = "📉"
        else: icon = "💎" # POTENTIAL_REBOUND
        alert_title = f"{icon} BUY SIGNAL - {sig.replace('_', ' ')}"
    else:
        icon = "🔴" if sig == "RSI_OVERBOUGHT" else "🚨"
        alert_title = f"{icon} SELL SIGNAL - {sig.replace('_', ' ')}"
        
    msg = f"*{alert_title}*\n\n"
    msg += f"🏢 Saham: *{sym_name}*\n"
    
    pct_sign = "↑" if s['pct_1d'] > 0 else "↓"
    msg += f"💵 Harga: {format_rp(s['close'])} ({pct_sign} {abs(s['pct_1d']):.1f}%)\n"
    msg += f"📊 Volume: {format_vol(s['vol'])} (↑ {s['vol_ratio']*100:.0f}% vs Avg)\n"
    
    if sig == "BUY_ON_DIP":
        msg += f"📏 MA-50: {format_rp(s['ma50'])}\n"
    msg += f"📏 MA-200: {format_rp(s['ma200'])}\n"
    msg += f"📈 RSI(14): {s['rsi']:.1f}\n\n"
    
    msg += f"🎯 Confidence: *{conf}*\n"
    msg += f"💡 Insight: {desc}\n"
    
    return msg

def format_status_report(all_stocks_status):
    bullish_stocks = [s for s in all_stocks_status if s['trend'] == 'BULLISH']
    bearish_stocks = [s for s in all_stocks_status if s['trend'] == 'BEARISH']
    
    format_rp = lambda n: f"Rp {n:,.0f}".replace(',', '.')
    
    msg = f"📊 *DAILY MARKET SCAN - {datetime.now(TIMEZONE).strftime('%d %b %Y, %H:%M WIB')}*\n"
    msg += "="*40 + "\n\n"
    
    # BULLISH
    msg += f"📈 *BULLISH ZONE (Price > MA200):*\n"
    for i, s in enumerate(bullish_stocks, 1):
        sym = s['symbol'].split('.')[0]
        status = "Near OS" if s['rsi'] < 40 else "HOLD"
        msg += f"{i}. {sym} | {format_rp(s['close'])} | RSI {s['rsi']:.0f} | Status: {status}\n"
        if i >= 6:
            msg += f"... [{len(bullish_stocks)-i} lebih]\n"
            break
            
    msg += "\n📉 *BEARISH ZONE (Price < MA200):*\n"
    for i, s in enumerate(bearish_stocks, 1):
        sym = s['symbol'].split('.')[0]
        status = "Downtrend"
        msg += f"{i}. {sym} | {format_rp(s['close'])} | RSI {s['rsi']:.0f} | Status: CAUTION\n"
        if i >= 4:
            msg += f"... [{len(bearish_stocks)-i} lebih]\n"
            break
            
    msg += "\n⚙️ *ALERTS SUMMARY:*\n"
    msg += f"✓ Total Monitored: {len(all_stocks_status)} saham\n"
    msg += f"✓ Bullish (>MA200): {len(bullish_stocks)} saham\n"
    msg += f"✓ Bearish (<MA200): {len(bearish_stocks)} saham\n\n"
    
    msg += "📌 *INSIGHTS:*\n"
    msg += "• Market condition: NEUTRAL (No high-conviction signals found today)\n"
    msg += "• Sistem akan monitoring ulang di sesi berikutnya.\n"
    
    return msg

def format_mini_report(all_stocks_status):
    now_str = datetime.now(TIMEZONE).strftime('%H:%M WIB')
    
    bullish_count = len([s for s in all_stocks_status if s['trend'] == 'BULLISH'])
    bearish_count = len([s for s in all_stocks_status if s['trend'] == 'BEARISH'])
    
    # Sort for movers
    movers = sorted(all_stocks_status, key=lambda x: x.get('pct_1d', 0) if x.get('pct_1d') is not None else 0, reverse=True)
    top_mover = movers[0] if movers else None
    laggard = movers[-1] if movers else None
    
    msg = f"📡 *Quick Scan - {now_str}*\n"
    msg += f"────────────────\n"
    msg += f"✅ Bullish: {bullish_count} | ❌ Bearish: {bearish_count}\n"
    
    if top_mover:
        msg += f"🔥 Top: {top_mover['symbol'].split('.')[0]} (+{top_mover['pct_1d']:.1f}%)\n"
    if laggard:
        msg += f"❄️ Low: {laggard['symbol'].split('.')[0]} ({laggard['pct_1d']:.1f}%)\n"
        
    msg += f"\n💡 *Status:* Kondisi Stabil (Belum ada sinyal tembus). Next scan di sesi berikutnya."
    return msg

async def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram Token missing. Log:\n", message)
        return
        
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode='Markdown')
        print("Telegram dikirim!")
    except Exception as e:
        print(f"Gagal kirim telegram: {e}")

async def main():
    print(f"=== Stock Notifier (V3 SMART FILTER) ({datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M')}) ===")
    config = load_config()
    state = get_last_state()
    
    signals_sent_today = []
    all_stocks_status = []
    
    for symbol in config['stocks']:
        df = fetch_data(symbol, config)
        if df is None: continue
            
        df = calculate_indicators(df, config)
        
        signal_data, reason = evaluate_signals(symbol, df, config)
        
        if signal_data:
            all_stocks_status.append(signal_data['data'])
            
            sig_type = signal_data['type']
            if check_cooldown(symbol, sig_type, state, config):
                print(f"[{symbol}] Alert '{sig_type}' distop (Cooldown < 6 jam)")
                continue
                
            msg = format_alert(signal_data)
            await send_telegram(msg)
            signals_sent_today.append(symbol)
            
            # Save State
            state[symbol] = {
                'signal': sig_type,
                'time': datetime.now(TIMEZONE).isoformat()
            }
        elif reason == "HOLD":
            # For status report
            last_row = df.iloc[-1]
            ma200_col = f"SMA_{config['indicators']['ma_long']}"
            all_stocks_status.append({
                'symbol': symbol,
                'close': last_row['Close'],
                'rsi': last_row[f"RSI_{config['indicators']['rsi_length']}"],
                'ma200': last_row[ma200_col],
                'trend': 'BULLISH' if last_row['Close'] > last_row[ma200_col] else 'BEARISH'
            })
            print(f"[{symbol}] HOLD / No Signal")
        else:
            print(f"[{symbol}] Filtered: {reason}")
            
            
    # Send report if no signals were fired
    now = datetime.now(TIMEZONE)
    if len(signals_sent_today) == 0 and config['signals']['send_status_report_if_no_alerts']:
        if len(all_stocks_status) > 0:
            if now.hour == 18:
                print(f"\n>> Pukul {now.hour}:00 WIB. Mengirim Report Harian Lengkap...")
                report = format_status_report(all_stocks_status)
            else:
                print(f"\n>> Pukul {now.hour}:00 WIB. Mengirim Mini Report...")
                report = format_mini_report(all_stocks_status)
                
            await send_telegram(report)
            
    save_state(state)
    print("=== Pengecekan Selesai ===")

if __name__ == "__main__":
    asyncio.run(main())
