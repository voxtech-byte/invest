import argparse
import asyncio
from datetime import datetime
import pytz
import json
import pandas as pd
import os

# Import functions from main.py
from main import format_alert, format_status_report, format_mini_report, send_telegram, load_config, generate_chart

TIMEZONE = pytz.timezone('Asia/Jakarta')

def create_mock_df():
    # Mock 30 days data for charts
    dates = pd.date_range(end=datetime.now(), periods=30)
    data = {
        'Open': [100 + i for i in range(30)],
        'High': [102 + i for i in range(30)],
        'Low': [98 + i for i in range(30)],
        'Close': [101 + i for i in range(30)],
        'Volume': [1000000 for _ in range(30)],
        'SMA_50': [100 for _ in range(30)],
        'SMA_200': [90 for _ in range(30)],
        'RSI_14': [50 for _ in range(30)]
    }
    df = pd.DataFrame(data, index=dates)
    return df

def simulate_signal(sig_name, desc, confidence, symbol='BMRI.JK'):
    print(f"--- Simulating {sig_name} (Professional Mode) ---")
    data = {
        'type': sig_name,
        'confidence': confidence,
        'desc': desc,
        'data': {
            'symbol': symbol,
            'close': 7250,
            'rsi': 35.0,
            'ma200': 7100,
            'ma50': 7000,
            'vol': 8500000,
            'vol_ratio': 2.1,
            'pct_1d': 2.5,
            'pattern': 'Hammer Pattern',
            'trend': 'BULLISH (UPTREND)'
        }
    }
    msg = format_alert(data)
    
    # Mocking chart generation
    config = load_config()
    df = create_mock_df()
    photo_path = None
    try:
        photo_path = generate_chart(symbol, df, config)
    except Exception as e:
        print(f"Mock Chart Error: {e}")
        
    return msg, photo_path

def simulate_status_report():
    print("--- Simulating MARKET STATUS REPORT (Professional Mode) ---")
    all_stocks_status = [
        {'symbol': 'BBCA.JK', 'close': 10450, 'rsi': 45, 'ma200': 10100, 'trend': 'BULLISH (UPTREND)', 'pct_1d': 0.5, 'pattern': ''},
        {'symbol': 'BMRI.JK', 'close': 7200, 'rsi': 28, 'ma200': 7100, 'trend': 'BULLISH (UPTREND)', 'pct_1d': 1.2, 'pattern': 'Hammer Pattern'},
        {'symbol': 'BBNI.JK', 'close': 3850, 'rsi': 22, 'ma200': 3950, 'trend': 'BEARISH (DOWNTREND)', 'pct_1d': -1.5, 'pattern': 'Doji Pattern'}
    ]
    return format_status_report(all_stocks_status), None

async def run_test():
    parser = argparse.ArgumentParser(description="V4 Professional Visual Notifier Mock Test")
    parser.add_argument('--type', choices=['breakout', 'dip', 'breakdown', 'report', 'rebound'], default='breakout', help="Type of signal to test")
    parser.add_argument('--send-telegram', action='store_true', help="Send real Telegram notification")
    args = parser.parse_args()

    message = ""
    photo_path = None
    
    if args.type == 'breakout':
        message, photo_path = simulate_signal('VOLUME_BREAKOUT', 'Strong accumulation with price/volume breakout.', 'HIGH')
    elif args.type == 'dip':
        message, photo_path = simulate_signal('BUY_ON_DIP', 'Healthy retracement near MA50 Support.', 'MEDIUM-HIGH')
    elif args.type == 'rebound':
        message, photo_path = simulate_signal('POTENTIAL_REBOUND', 'Support test near MA200 with bullish rejection.', 'HIGH')
    elif args.type == 'report':
        message, photo_path = simulate_status_report()

    print("\n[PREVIEW MESSAGE]")
    print(message)
    if photo_path:
        print(f"[IMAGE GENERATED]: {photo_path}")
    print("-" * 20)

    if args.send_telegram:
        print("Sending to Telegram...")
        await send_telegram(message, photo_path=photo_path)
    else:
        if photo_path and os.path.exists(photo_path):
            os.remove(photo_path) # Cleanup if not sending
        print("💡 Use --send-telegram to send this to your bot.")

if __name__ == "__main__":
    asyncio.run(run_test())
