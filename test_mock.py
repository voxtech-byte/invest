import argparse
import asyncio
from datetime import datetime
import pytz

# Import fungsi-fungsi dari main.py
from main import format_message, send_telegram_notification

TIMEZONE = pytz.timezone('Asia/Jakarta')

def simulate_signal():
    print("=== MENSIMULASIKAN SIGNAL (RELAXED MODE) ===")
    
    # Dummy Signal Data mensimulasikan kondisi BUY (Volume Breakout & Golden Cross hybrid)
    signal_data = {
        'symbol': 'GOTO.JK',
        'signal': 'BUY',
        'reason': 'Volume Breakout! Harga naik > 2% diiringi ledakan volume 🚀',
        'confidence': 'MEDIUM',
        'close': 85,
        'pct_change': 6.2,
        'rsi': 55.4,
        'ma20': 78,
        'ma50': 75,
        'ma200': 60,
        'volume': 4500000000,
        'vol_avg': 1200000000,
        'time': datetime.now(TIMEZONE)
    }
    
    print(f"Data tersimulasi untuk {signal_data['symbol']}:")
    for k, v in signal_data.items():
        print(f"  {k}: {v}")
        
    msg = format_message(signal_data)
    print("\n[PREVIEW] Format Pesan Telegram Terbaru:")
    print("-" * 40)
    print(msg)
    print("-" * 40)
    
    return msg

async def run_test():
    parser = argparse.ArgumentParser(description="Test Mock Data Untuk Telegram Bot")
    parser.add_argument('--send-telegram', action='store_true', help="Kirim notifikasi dummy ke telegram menggunakan API")
    args = parser.parse_args()
    
    msg = simulate_signal()
    
    if args.send_telegram:
        print("\n🚀 Menghubungi Telegram API...")
        await send_telegram_notification(msg)
    else:
        print("\n💡 TIP: Gunakan argumen '--send-telegram' untuk mengirim pesan dummy ke Telegram.")
        print("Contoh: python3 test_mock.py --send-telegram")

if __name__ == "__main__":
    asyncio.run(run_test())
