import argparse
import asyncio
from datetime import datetime
import pytz

# Import fungsi-fungsi dari main.py
from main import format_message, send_telegram_notification

TIMEZONE = pytz.timezone('Asia/Jakarta')

def simulate_signal():
    print("=== MENSIMULASIKAN SIGNAL ===")
    
    # Dummy Signal Data mensimulasikan kondisi BUY
    # Sesuai requirement: RSI < 30, Harga > MA200, Volume > 150%
    signal_data = {
        'symbol': 'BBCA.JK',
        'signal': 'BUY',
        'confidence': 'HIGH',
        'close': 10450,
        'rsi': 28.1,
        'ma50': 10300,
        'ma200': 10100,
        'volume': 5200000,
        'vol_avg': 1850000, # Avg Vol 1.85M, Vol hari ini 5.2M (↑281% vs avg)
        'time': datetime.now(TIMEZONE)
    }
    
    print(f"Data tersimulasi untuk {signal_data['symbol']}:")
    for k, v in signal_data.items():
        # Hide unneeded output formatting details
        print(f"  {k}: {v}")
        
    msg = format_message(signal_data)
    print("\n[PREVIEW] Format Pesan Telegram:")
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
        print("\n💡 TIP: Gunakan argumen '--send-telegram' untuk mengirim pesan dummy ini ke Telegram.")
        print("Pastikan Anda sudah set `TELEGRAM_BOT_TOKEN` dan `TELEGRAM_CHAT_ID` env variables.")
        print("Contoh: python test_mock.py --send-telegram")

if __name__ == "__main__":
    asyncio.run(run_test())
