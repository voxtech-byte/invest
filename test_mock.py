import argparse
import asyncio
from datetime import datetime
import pytz
import json
import pandas as pd
import os

from main import format_alert, format_status_report, send_telegram, load_config, generate_chart

TIMEZONE = pytz.timezone('Asia/Jakarta')

def create_mock_df():
    dates = pd.date_range(end=datetime.now(), periods=30)
    data = {
        'Open': [100 + i for i in range(30)],
        'High': [102 + i for i in range(30)],
        'Low': [98 + i for i in range(30)],
        'Close': [101 + i for i in range(30)],
        'Volume': [1000000 for _ in range(30)],
        'SMA_50': [100 for _ in range(30)],
        'SMA_200': [90 for _ in range(30)],
        'RSI_14': [50 for _ in range(30)],
        'MACDh_12_26_9': [0.5 for _ in range(30)],
        'BBL_20_2.0': [95 for _ in range(30)],
        'BBU_20_2.0': [105 for _ in range(30)],
    }
    df = pd.DataFrame(data, index=dates)
    return df

def simulate_strong_buy():
    print("--- Simulating STRONG BUY (Score 6/8) ---")
    data = {
        'type': 'STRONG_BUY',
        'confidence': 'HIGH',
        'desc': 'Multiple confirmations align for potential entry.',
        'direction': 'BUY',
        'score': 6,
        'layers': {
            'RSI': 'Oversold (28)',
            'MA50': 'Support Test',
            'MA200': 'Uptrend Confirmed',
            'Volume': 'Spike (2.1x)',
            'MACD': 'Bullish Momentum',
            'BB': 'Near Lower Band',
        },
        'data': {
            'symbol': 'BMRI.JK',
            'close': 7250, 'rsi': 28.0, 'ma200': 7100, 'ma50': 7000,
            'vol': 8500000, 'vol_ratio': 2.1, 'pct_1d': 2.5,
            'pattern': 'Hammer', 'macd_hist': 15.5,
            'bb_lower': 7050, 'bb_upper': 7500,
            'support': 7000, 'resistance': 7600,
            'buy_score': 6, 'sell_score': 0, 'trend': 'BULLISH'
        }
    }
    return format_alert(data), data

def simulate_watchlist():
    print("--- Simulating WATCHLIST BUY (Score 3/8) ---")
    data = {
        'type': 'WATCHLIST_BUY',
        'confidence': 'MEDIUM',
        'desc': 'Moderate buy signals. Monitor for additional confirmation.',
        'direction': 'BUY',
        'score': 3,
        'layers': {
            'RSI': 'Low Zone (35)',
            'MA200': 'Uptrend Confirmed',
            'Volume': 'Above Avg (1.3x)',
        },
        'data': {
            'symbol': 'TLKM.JK',
            'close': 3950, 'rsi': 35.0, 'ma200': 3900, 'ma50': 4000,
            'vol': 4200000, 'vol_ratio': 1.3, 'pct_1d': 0.8,
            'pattern': '', 'macd_hist': -5.2,
            'bb_lower': 3800, 'bb_upper': 4100,
            'support': 3750, 'resistance': 4200,
            'buy_score': 3, 'sell_score': 1, 'trend': 'BULLISH'
        }
    }
    return format_alert(data), data

def simulate_report():
    print("--- Simulating MARKET STATUS REPORT ---")
    all_stocks_status = [
        {'symbol': 'BBCA.JK', 'close': 10450, 'rsi': 45, 'ma200': 10100, 'trend': 'BULLISH', 'pct_1d': 0.5, 'pattern': '', 'macd_hist': 12.0, 'buy_score': 2, 'sell_score': 0},
        {'symbol': 'BMRI.JK', 'close': 7200, 'rsi': 28, 'ma200': 7100, 'trend': 'BULLISH', 'pct_1d': 1.2, 'pattern': 'Hammer', 'macd_hist': 8.5, 'buy_score': 5, 'sell_score': 0},
        {'symbol': 'BBNI.JK', 'close': 3850, 'rsi': 22, 'ma200': 3950, 'trend': 'BEARISH', 'pct_1d': -1.5, 'pattern': 'Doji', 'macd_hist': -10.2, 'buy_score': 0, 'sell_score': 4},
        {'symbol': 'TLKM.JK', 'close': 3900, 'rsi': 42, 'ma200': 4000, 'trend': 'BEARISH', 'pct_1d': -0.3, 'pattern': '', 'macd_hist': -2.1, 'buy_score': 0, 'sell_score': 2},
    ]
    return format_status_report(all_stocks_status), None

async def run_test():
    parser = argparse.ArgumentParser(description="V5 Multi-Confirmation Mock Test")
    parser.add_argument('--type', choices=['strong_buy', 'watchlist', 'report'], default='strong_buy', help="Type of test")
    parser.add_argument('--send-telegram', action='store_true', help="Send to Telegram")
    args = parser.parse_args()

    message = ""
    photo_path = None
    
    if args.type == 'strong_buy':
        message, sig_data = simulate_strong_buy()
        config = load_config()
        df = create_mock_df()
        try:
            photo_path = generate_chart('BMRI.JK', df, config)
        except Exception as e:
            print(f"Chart error: {e}")
    elif args.type == 'watchlist':
        message, sig_data = simulate_watchlist()
    elif args.type == 'report':
        message, _ = simulate_report()

    print("\n[PREVIEW]")
    print(message)
    if photo_path:
        print(f"[IMAGE]: {photo_path}")
    print("-" * 30)

    if args.send_telegram:
        print("Sending to Telegram...")
        await send_telegram(message, photo_path=photo_path)
    else:
        if photo_path and os.path.exists(photo_path):
            os.remove(photo_path)
        print("Use --send-telegram to send this to your bot.")

if __name__ == "__main__":
    asyncio.run(run_test())
