import os
import yfinance as yf
import pandas as pd
import pandas_ta as ta
from telegram import Bot
import asyncio
import json
from datetime import datetime, timedelta
import pytz

# Konfigurasi Default - Portfolio Monitoring
STOCKS = [
    # Banking & Finance (4 saham)
    'BBCA.JK',  # BCA - Banking leader
    'BMRI.JK',  # Bank Mandiri - Potensi rebound
    'BRIS.JK',  # Bank Rakyat - Growth + dividen
    'BBNI.JK',  # Bank Negara - Undervalued BUMN
    
    # Tech & E-Commerce (2 saham)
    'GOTO.JK',  # GoTo - Recovery play
    'BUKA.JK',  # Bukalapak - E-commerce turnaround
    
    # Consumer & Pharma (4 saham)
    'UNVR.JK',  # Unilever - FMG leader, dividen
    'INDF.JK',  # Indofood - Essential goods
    'KAEF.JK',  # Kimia Farma - Pharma growth
    'MERK.JK',  # Merck - Pharma stable
    
    # Utilities & Infrastructure (4 saham)
    'TLKM.JK',  # Telkom - Telecom stable
    'PGAS.JK',  # Gas Negara - Dividen tinggi
    'WIKA.JK',  # Wika - Infrastructure (IKN project)
    'PTBA.JK',  # Bukit Asam - Coal, dividen bagus
    
    # Cyclical (2 saham)
    'ASII.JK',  # Astra - Auto/financing recovery
    'UNTR.JK',  # United Tractors - Mining equipment
]
TIMEZONE = pytz.timezone('Asia/Jakarta')

# Parameter Technical Indicators
RSI_LENGTH = 14
MA_FAST = 20
MA_SHORT = 50
MA_LONG = 200
VOL_AVG_DAYS = 20

# Telegram Config
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

STATE_FILE = "last_signals.json"

def get_last_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_state(state):
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f)
    except Exception as e:
        print(f"Gagal menyimpan state: {e}")

def is_duplicate(symbol, signal_reason):
    """Mencegah notifikasi duplikat untuk alasan yang persis sama dalam kurun waktu (< 1 jam)."""
    state = get_last_state()
    now = datetime.now(TIMEZONE)
    
    if symbol in state:
        last_reason = state[symbol].get('reason')
        last_time_str = state[symbol].get('time')
        
        if last_reason == signal_reason and last_time_str:
            last_time = datetime.fromisoformat(last_time_str)
            # Kalau alasan sinyal sama dan waktunya berdekatan (< 1 jam), drop
            if now - last_time < timedelta(hours=1):
                return True
                
    # Update state jika bukan duplikat
    state[symbol] = {
        'reason': signal_reason,
        'time': now.isoformat()
    }
    save_state(state)
    return False

def fetch_data(symbol):
    """Ambil data harga saham 1 tahun terakhir dengan interval daily."""
    print(f"[{symbol}] Mengambil data...")
    try:
        stock = yf.Ticker(symbol)
        df = stock.history(period="1y", interval="1d")
        if df.empty:
            print(f"[{symbol}] Data kosong!")
            return None
        return df
    except Exception as e:
        print(f"[{symbol}] Gagal mengambil data: {e}")
        return None

def calculate_indicators(df):
    """Hitung RSI, MA20, MA50, MA200, Pct Change dan Rata-rata Volume."""
    # Pastikan data terurut
    df = df.sort_index()
    
    # RSI & Momentum
    df.ta.rsi(length=RSI_LENGTH, append=True)
    df['Pct_Change'] = df['Close'].pct_change() * 100
    
    # Moving Averages
    df.ta.sma(length=MA_FAST, append=True)
    df.ta.sma(length=MA_SHORT, append=True)
    df.ta.sma(length=MA_LONG, append=True)
    
    # Volume Rata-rata 20 hari
    df['Vol_Avg_20'] = df['Volume'].rolling(window=VOL_AVG_DAYS).mean()
    
    return df

def generate_signals(symbol, df):
    """Memeriksa kondisi yang Relaxed/Santai: Golden Cross, Trend Dip, Volume Breakout."""
    # Butuh minimal 2 hari berturut-turut untuk mengecek Crossover (Perpotongan GARIS MA)
    if len(df) < 2:
        return None
        
    last_row = df.iloc[-1]
    prev_row = df.iloc[-2]
    
    close = last_row['Close']
    change = last_row['Pct_Change']
    volume = last_row['Volume']
    
    try:
        rsi = last_row[f'RSI_{RSI_LENGTH}']
        
        curr_ma20 = last_row[f'SMA_{MA_FAST}']
        prev_ma20 = prev_row[f'SMA_{MA_FAST}']
        
        curr_ma50 = last_row[f'SMA_{MA_SHORT}']
        prev_ma50 = prev_row[f'SMA_{MA_SHORT}']
        
        ma200 = last_row[f'SMA_{MA_LONG}']
    except KeyError:
        print(f"[{symbol}] History data kurang panjang.")
        return None

    vol_avg = last_row['Vol_Avg_20']
    
    if pd.isna(rsi) or pd.isna(curr_ma50) or pd.isna(vol_avg):
        return None
        
    signal_type = None
    reason = None
    confidence = None
    
    # --- LOGIKA BUY ---
    
    # 1. GOLDEN CROSS (Momentum Uptrend Awal)
    if prev_ma20 < prev_ma50 and curr_ma20 > curr_ma50:
        signal_type = "BUY"
        reason = "Golden Cross (MA20 tembus MA50 ke atas) 🟢"
        confidence = "HIGH"
        
    # 2. VOLUME BREAKOUT (Ada institusi/Big Money borong)
    elif change > 2.0 and volume > (2.0 * vol_avg):
        signal_type = "BUY"
        reason = "Volume Breakout! Harga naik > 2% diiringi ledakan volume 🚀"
        confidence = "MEDIUM"
        
    # 3. BUY ON DIP (Koreksi sementara di atas MA50)
    # Harga turun perlahan, RSI < 45, dan harga sedang menempel di sekitar MA50 (Batas selisih 2%)
    elif rsi < 45 and (abs(close - curr_ma50) / curr_ma50 < 0.02) and close > ma200:
        signal_type = "BUY"
        reason = "Buy on Dip! Mendekati zona Support MA50 🛒"
        confidence = "MEDIUM"
        
    # --- LOGIKA SELL ---
    
    # 4. DEATH CROSS (Momentum Jatuh)
    elif prev_ma20 > prev_ma50 and curr_ma20 < curr_ma50:
        signal_type = "SELL"
        reason = "Death Cross (MA20 terjun tembus MA50 ke bawah) 🩸"
        confidence = "HIGH"
        
    # 5. TAKE PROFIT / CUT LOSS (Overbought ekstrem atau kepanikan volume jual)
    elif rsi > 75 or (change < -3.0 and volume > (1.5 * vol_avg)):
        signal_type = "SELL"
        reason = "Siaga! Saham Super Overbought atau Dibanting ⚠️"
        confidence = "MEDIUM"
        
    if not signal_type:
        return None
        
    return {
        'symbol': symbol,
        'signal': signal_type,
        'reason': reason,
        'confidence': confidence,
        'close': close,
        'pct_change': change,
        'rsi': rsi,
        'ma20': curr_ma20,
        'ma50': curr_ma50,
        'ma200': ma200,
        'volume': volume,
        'vol_avg': vol_avg,
        'time': df.index[-1] # the timestamp
    }

def format_message(data):
    """Format pesan Telegram notifikasi."""
    sym = data['symbol'].replace('.JK', '')
    sig = data['signal']
    reason = data['reason']
    close = data['close']
    pct = data['pct_change']
    vol = data['volume']
    vol_avg = data['vol_avg']
    rsi = data['rsi']
    
    vol_pct = (vol / vol_avg * 100) if vol_avg > 0 else 0
    
    # Helper formatters
    format_rupiah = lambda n: f"Rp {n:,.0f}".replace(',', '.')
    
    def format_volume(num):
        if num >= 1_000_000: return f"{num/1_000_000:.1f}M"
        if num >= 1_000: return f"{num/1_000:.1f}K"
        return str(int(num))

    pct_str = f"📈 +{pct:.1f}%" if pct > 0 else f"📉 {pct:.1f}%"
    
    msg = f"*{sig} ALERT - {sym}* {pct_str}\n"
    msg += f"💡 *Reason:* {reason}\n\n"
    msg += f"💵 Harga: {format_rupiah(close)}\n"
    msg += f"📊 Volume: {format_volume(vol)} (↑{vol_pct:.0f}% vs Avg)\n"
    msg += f"📈 RSI(14): {rsi:.1f}\n"
    msg += f"📏 MA20: {format_rupiah(data['ma20'])} \\| MA50: {format_rupiah(data['ma50'])}\n\n"
    
    now_str = datetime.now(TIMEZONE).strftime('%d %b %Y %H:%M')
    msg += f"⏳ {now_str}"
    
    return msg

async def send_telegram_notification(message):
    """Kirim notifikasi ke Telegram dengan Markdown parse mode v2 (fallback to original logic)."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram Config (Token/Chat ID) hilang. Skipping send.")
        return
        
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode='Markdown')
        print(f"Notifikasi berhasil dikirim!")
    except Exception as e:
        print(f"Gagal mengirim notifikasi: {e}")

async def main():
    print(f"=== Stock Notifier (LITE MODE) ({datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M')}) ===")
    
    for symbol in STOCKS:
        df = fetch_data(symbol)
        if df is None: continue
            
        df = calculate_indicators(df)
        signal_data = generate_signals(symbol, df)
        
        if signal_data:
            print(f"[{symbol}] => {signal_data['signal']} ({signal_data['reason']})")
            
            if is_duplicate(symbol, signal_data['reason']):
                print(f"  -> Skipped (duplikat dalam 1 jam)")
                continue
                
            msg = format_message(signal_data)
            await send_telegram_notification(msg)
        else:
            print(f"[{symbol}] => HOLD")
            
    print("=== Pengecekan Selesai ===")

if __name__ == "__main__":
    asyncio.run(main())
