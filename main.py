import os
import yfinance as yf
import pandas as pd
import pandas_ta as ta
from telegram import Bot
import asyncio
import json
from datetime import datetime, timedelta
import pytz

# Konfigurasi Default
STOCKS = ['BBCA.JK', 'GOTO.JK', 'ASII.JK', 'TLKM.JK', 'UNVR.JK']
TIMEZONE = pytz.timezone('Asia/Jakarta')

# Parameter Technical Indicators
RSI_LENGTH = 14
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70
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

def is_duplicate(symbol, signal_type):
    """Mencegah notifikasi duplikat dalam kurun waktu 1 jam."""
    state = get_last_state()
    now = datetime.now(TIMEZONE)
    
    if symbol in state:
        last_signal = state[symbol].get('signal')
        last_time_str = state[symbol].get('time')
        
        if last_signal == signal_type and last_time_str:
            last_time = datetime.fromisoformat(last_time_str)
            # Kalau sinyal sama dan waktunya berdekatan (< 1 jam), drop
            if now - last_time < timedelta(hours=1):
                return True
                
    # Update state jika bukan duplikat
    state[symbol] = {
        'signal': signal_type,
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
    """Hitung RSI, MA50, MA200, dan Rata-rata Volume."""
    # Pastikan data terurut
    df = df.sort_index()
    
    # RSI
    df.ta.rsi(length=RSI_LENGTH, append=True)
    # MA
    df.ta.sma(length=MA_SHORT, append=True)
    df.ta.sma(length=MA_LONG, append=True)
    # Volume Rata-rata 20 hari
    df['Vol_Avg_20'] = df['Volume'].rolling(window=VOL_AVG_DAYS).mean()
    
    return df

def generate_signals(symbol, df):
    """Memeriksa kondisi Technical Indicators untuk menentukan BUY/SELL."""
    # Ambil baris data terakhir
    last_row = df.iloc[-1]
    
    close = last_row['Close']
    volume = last_row['Volume']
    
    # Ambil nama default kolom `pandas_ta`
    try:
        rsi = last_row[f'RSI_{RSI_LENGTH}']
        ma50 = last_row[f'SMA_{MA_SHORT}']
        ma200 = last_row[f'SMA_{MA_LONG}']
    except KeyError:
        print(f"[{symbol}] History data kurang panjang untuk mengkalkulasi MA/RSI.")
        return None

    vol_avg = last_row['Vol_Avg_20']
    
    # Pastikan tak ada NaN
    if pd.isna(rsi) or pd.isna(ma50) or pd.isna(ma200) or pd.isna(vol_avg):
        print(f"[{symbol}] Data indikator belum lengkap (mungkin periode kurang dari {MA_LONG} hari).")
        return None
        
    signal_type = None
    confidence = None
    
    # Cek Kondisi BUY
    # RSI < 30 DAN Harga > MA200 DAN Volume > 150%
    if rsi < RSI_OVERSOLD and close > ma200 and volume > (1.5 * vol_avg):
        signal_type = "BUY"
        confidence = "HIGH"
        
    # Cek Kondisi SELL
    # RSI > 70 DAN (Harga < MA50 OR Volume > 200%)
    elif rsi > RSI_OVERBOUGHT and (close < ma50 or volume > (2.0 * vol_avg)):
        signal_type = "SELL"
        confidence = "MEDIUM"
        
    if not signal_type:
        return None
        
    return {
        'symbol': symbol,
        'signal': signal_type,
        'confidence': confidence,
        'close': close,
        'rsi': rsi,
        'ma50': ma50,
        'ma200': ma200,
        'volume': volume,
        'vol_avg': vol_avg,
        'time': df.index[-1]
    }

def format_message(signal_data):
    """Format pesan Telegram yang mendetail."""
    sym = signal_data['symbol']
    sig = signal_data['signal']
    conf = signal_data['confidence']
    close = signal_data['close']
    rsi = signal_data['rsi']
    ma50 = signal_data['ma50']
    ma200 = signal_data['ma200']
    vol = signal_data['volume']
    vol_avg = signal_data['vol_avg']
    
    # Hitung persentase peningkatan volume
    if vol_avg > 0:
        vol_pct = (vol / vol_avg) * 100
    else:
        vol_pct = 0
        
    emoji = "📈" if sig == "BUY" else "📉"
    rsi_status = "⬇️ (Oversold)" if rsi < RSI_OVERSOLD else ("⬆️ (Overbought)" if rsi > RSI_OVERBOUGHT else "Netral")
    
    now_str = datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')
    
    # Format number helper function
    def format_rupiah(num):
        # Format ke string rupiah standar lokal
        s = f"{num:,.0f}".replace(',', '.')
        return f"Rp {s}"
    
    def format_volume(num):
        if num >= 1_000_000:
            return f"{num/1_000_000:.1f}M"
        elif num >= 1_000:
            return f"{num/1_000:.1f}K"
        return str(int(num))

    msg = f"{emoji} *{sig} SIGNAL - {sym.replace('.JK', '')}*\n"
    msg += f"Harga: {format_rupiah(close)} (Close)\n"
    msg += f"RSI({RSI_LENGTH}): {rsi:.1f} {rsi_status}\n"
    msg += f"MA{MA_SHORT}: {format_rupiah(ma50)} \\| MA{MA_LONG}: {format_rupiah(ma200)}\n"
    msg += f"Volume: {format_volume(vol)} (↑{vol_pct:.0f}% vs avg)\n"
    msg += f"Confidence: *{conf}*\n"
    msg += f"Time: {now_str}"
    
    return msg

async def send_telegram_notification(message):
    """Kirim notifikasi Telegram secara asinkronus."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram configurasi (Token/Chat ID) tidak ditemukan. Notifikasi diskip.")
        print("--- MESSAGE CONTENT ---")
        print(message)
        print("-----------------------")
        return
        
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        # MarkdownV2 requires careful escaping of symbols
        # using parse_mode='Markdown' (v1) here or we can just send as regular Markdown format based on above.
        # But telegram bot api v20 defaults to MarkdownV2 usually, wait, Markdown is still supported.
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode='Markdown')
        print(f"Notifikasi berhasil dikirim!")
    except Exception as e:
        print(f"Gagal mengirim notifikasi Telegram: {e}")

async def main():
    print(f"=== Memulai Stock Notifier ({datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}) ===")
    
    for symbol in STOCKS:
        # 1. Fetch
        df = fetch_data(symbol)
        if df is None:
            continue
            
        # 2. Indicators
        df = calculate_indicators(df)
        
        # 3. Logic Engine
        signal_data = generate_signals(symbol, df)
        
        # 4. Filter & Notify
        if signal_data:
            print(f"[{symbol}] Sinyal terdeteksi: {signal_data['signal']} ({signal_data['confidence']})")
            
            # Cek duplikat
            if is_duplicate(symbol, signal_data['signal']):
                print(f"[{symbol}] Notifikasi duplikat dihiraukan (sudah dikirim < 1 jam terakhir).")
                continue
                
            msg = format_message(signal_data)
            await send_telegram_notification(msg)
        else:
            print(f"[{symbol}] Tidak ada sinyal dominan (HOLD).")
            
    print("=== Selesai ===")

if __name__ == "__main__":
    asyncio.run(main())
