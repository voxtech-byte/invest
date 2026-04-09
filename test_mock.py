import argparse
import asyncio
from datetime import datetime
import pytz
import json

# Import functions from main.py
from main import format_alert, format_status_report, send_telegram, load_config

TIMEZONE = pytz.timezone('Asia/Jakarta')

def simulate_volume_breakout():
    print("--- Simulating VOLUME_BREAKOUT (HIGH) ---")
    data = {
        'type': 'VOLUME_BREAKOUT',
        'confidence': 'HIGH',
        'desc': 'Institusi/Bandar sedang masuk perlahan',
        'data': {
            'symbol': 'BMRI.JK',
            'close': 7250,
            'rsi': 55.0,
            'ma200': 7100,
            'ma50': 7000,
            'vol': 8500000,
            'vol_ratio': 2.1,
            'pct_1d': 2.1,
            'trend': 'BULLISH'
        }
    }
    return format_alert(data)

def simulate_buy_on_dip():
    print("--- Simulating BUY_ON_DIP (MEDIUM-HIGH) ---")
    data = {
        'type': 'BUY_ON_DIP',
        'confidence': 'MEDIUM-HIGH',
        'desc': 'Support level tested, healthy pullback',
        'data': {
            'symbol': 'ASII.JK',
            'close': 4800,
            'rsi': 35.0,
            'ma200': 4700,
            'ma50': 4810,
            'vol': 3200000,
            'vol_ratio': 1.0,
            'pct_1d': -0.5,
            'trend': 'BULLISH'
        }
    }
    return format_alert(data)

def simulate_breakdown():
    print("--- Simulating BREAKDOWN (HIGH SELL) ---")
    data = {
        'type': 'BREAKDOWN',
        'confidence': 'HIGH',
        'desc': 'Trend reversal, break below MA200',
        'data': {
            'symbol': 'TLKM.JK',
            'close': 3890,
            'rsi': 35.0,
            'ma200': 3910,
            'ma50': 4000,
            'vol': 6500000,
            'vol_ratio': 1.6,
            'pct_1d': -2.5,
            'trend': 'BEARISH'
        }
    }
    return format_alert(data)

def simulate_status_report():
    print("--- Simulating DAILY STATUS REPORT (6 PM) ---")
    all_stocks_status = [
        {'symbol': 'BBCA.JK', 'close': 10450, 'rsi': 45, 'ma200': 10100, 'trend': 'BULLISH', 'pct_1d': 0.5},
        {'symbol': 'BMRI.JK', 'close': 7200, 'rsi': 28, 'ma200': 7100, 'trend': 'BULLISH', 'pct_1d': 1.2},
        {'symbol': 'BRIS.JK', 'close': 4950, 'rsi': 32, 'ma200': 4800, 'trend': 'BULLISH', 'pct_1d': -0.2},
        {'symbol': 'BBNI.JK', 'close': 3850, 'rsi': 22, 'ma200': 3950, 'trend': 'BEARISH', 'pct_1d': -1.5},
        {'symbol': 'PTBA.JK', 'close': 14200, 'rsi': 25, 'ma200': 14800, 'trend': 'BEARISH', 'pct_1d': 0.1}
    ]
    return format_status_report(all_stocks_status)

def simulate_mini_report():
    from main import format_mini_report
    print("--- Simulating MINI REPORT (Quick Scan) ---")
    all_stocks_status = [
        {'symbol': 'BBCA.JK', 'trend': 'BULLISH', 'pct_1d': 0.5},
        {'symbol': 'BMRI.JK', 'trend': 'BULLISH', 'pct_1d': 1.2},
        {'symbol': 'BRIS.JK', 'trend': 'BULLISH', 'pct_1d': -0.2},
        {'symbol': 'BBNI.JK', 'trend': 'BEARISH', 'pct_1d': -1.5},
        {'symbol': 'PTBA.JK', 'trend': 'BEARISH', 'pct_1d': 0.1}
    ]
    return format_mini_report(all_stocks_status)

def simulate_potential_rebound():
    print("--- Simulating POTENTIAL_REBOUND (💎 CHEAP & POTENTIAL) ---")
    data = {
        'type': 'POTENTIAL_REBOUND',
        'confidence': 'HIGH',
        'desc': 'Saham di area Support kuat MA200 (Murah) & mulai ada pantulan!',
        'data': {
            'symbol': 'BBCA.JK',
            'close': 10150,
            'rsi': 42.0,
            'ma200': 10100,
            'ma50': 10300,
            'vol': 5000000,
            'vol_ratio': 1.1,
            'pct_1d': 0.8,
            'trend': 'BULLISH'
        }
    }
    return format_alert(data)

async def run_test():
    parser = argparse.ArgumentParser(description="V3 Stock Notifier Mock Test")
    parser.add_argument('--type', choices=['breakout', 'dip', 'breakdown', 'report', 'rebound', 'mini'], default='breakout', help="Type of signal to test")
    parser.add_argument('--send-telegram', action='store_true', help="Send real Telegram notification")
    args = parser.parse_args()

    message = ""
    if args.type == 'breakout':
        message = simulate_volume_breakout()
    elif args.type == 'dip':
        message = simulate_buy_on_dip()
    elif args.type == 'breakdown':
        message = simulate_breakdown()
    elif args.type == 'report':
        message = simulate_status_report()
    elif args.type == 'mini':
        message = simulate_mini_report()
    elif args.type == 'rebound':
        message = simulate_potential_rebound()

    print("\n[PREVIEW MESSAGE]")
    print(message)
    print("-" * 20)

    if args.send_telegram:
        print("Sending to Telegram...")
        await send_telegram(message)
    else:
        print("💡 Use --send-telegram to send this to your bot.")

if __name__ == "__main__":
    asyncio.run(run_test())
