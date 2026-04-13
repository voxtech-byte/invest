import argparse
import asyncio
from datetime import datetime
import pytz
import json
import pandas as pd
import os

from main import format_alert, format_status_report, send_telegram, load_config, generate_chart, format_rp

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
        'BB_Width': [0.1 for _ in range(30)],
        'VPT': [1000 for _ in range(30)],
    }
    df = pd.DataFrame(data, index=dates)
    return df

def simulate_strong_buy():
    print("--- Simulating STRONG BUY (V6 Intelligence) ---")
    data = {
        'type': 'STRONG_BUY', 'confidence': 'HIGH',
        'desc': 'Multiple confirmations align. Institutional load detected.',
        'direction': 'BUY', 'score': 9.5,
        'layers': {
            'RSI': 'Oversold (28)', 'MA200': 'Uptrend',
            'BEE-FLOW': 'Institutional Accumulation (9/10)',
            'Phase': 'MARKUP (Strong Trend)', 'Volatility': 'SQUEEZE'
        },
        'data': {
            'symbol': 'ASII.JK', 'close': 6175, 'rsi': 28.0,
            'ma200': 5886, 'ma50': 6100, 'vol': 8500000, 'vol_ratio': 2.1,
            'pct_1d': 1.8, 'pattern': 'Hammer',
            'vol_context': 'Strong Accumulation (Price ↑ + Volume ↑↑)',
            'wyckoff_phase': 'MARKUP (Strong Trend)',
            'bee_score': 9, 'bee_label': 'HIGH ACCUMULATION (BIG BEE)',
            'is_squeeze': True,
            'macd_hist': 15.5, 'bb_lower': 6050, 'bb_upper': 6500,
            'support': 6000, 'resistance': 6800, 'atr': 85,
            'entry_low': 6100, 'entry_high': 6180,
            'stop_loss': 5900, 'target_1': 6450, 'target_2': 6800,
            'rrr_1': 1.0, 'rrr_2': 2.3, 'risk_pct': 2.0,
            'buy_score': 9, 'sell_score': 0, 'trend': 'BULLISH'
        }
    }
    return format_alert(data), data

def simulate_watchlist():
    print("--- Simulating WATCHLIST BUY (V6 Intelligence) ---")
    data = {
        'type': 'WATCHLIST_BUY', 'confidence': 'MEDIUM',
        'desc': 'Moderate buy signals. Monitor for additional confirmation.',
        'direction': 'BUY', 'score': 4.5,
        'layers': {
            'RSI': 'Low Zone (35)', 'MA200': 'Uptrend',
            'BEE-FLOW': 'Mild Bee Flow (5/10)'
        },
        'data': {
            'symbol': 'PGAS.JK', 'close': 1700, 'rsi': 35.0,
            'ma200': 1650, 'ma50': 1720, 'vol': 42000000, 'vol_ratio': 1.3,
            'pct_1d': 0.6, 'pattern': '',
            'vol_context': 'Healthy Buying (Price ↑ + Normal Vol)',
            'wyckoff_phase': 'ACCUMULATION (Smart Money Buying)',
            'bee_score': 5, 'bee_label': 'MILD ACCUMULATION',
            'is_squeeze': False,
            'macd_hist': -2.1, 'bb_lower': 1620, 'bb_upper': 1780,
            'support': 1600, 'resistance': 1850, 'atr': 35,
            'entry_low': 1690, 'entry_high': 1710,
            'stop_loss': 1630, 'target_1': 1770, 'target_2': 1805,
            'rrr_1': 1.0, 'rrr_2': 1.5, 'risk_pct': 2.0,
            'buy_score': 4.5, 'sell_score': 1, 'trend': 'BULLISH'
        }
    }
    return format_alert(data), data

def simulate_report():
    print("--- Simulating MARKET INTELLIGENCE REPORT ---")
    ihsg = {'close': 6850, 'pct_1d': -0.3, 'trend': 'BEARISH'}
    stocks = [
        {'symbol': 'BBCA.JK', 'close': 10450, 'trend': 'BULLISH', 'bee_score': 2, 'bee_label': 'NEUTRAL', 'wyckoff_phase': 'CONSOLIDATION', 'macd_hist': 12.0},
        {'symbol': 'ASII.JK', 'close': 6175, 'trend': 'BULLISH', 'bee_score': 9, 'bee_label': 'HIGH ACCUMULATION', 'wyckoff_phase': 'MARKUP', 'macd_hist': 15.5},
        {'symbol': 'BBNI.JK', 'close': 3710, 'trend': 'BEARISH', 'bee_score': 1, 'bee_label': 'DISTRIBUTION', 'wyckoff_phase': 'MARKDOWN', 'macd_hist': -5.0},
    ]
    return format_status_report(stocks, ihsg_data=ihsg), None

async def run_test():
    parser = argparse.ArgumentParser(description="V6 Intelligence Mock Test")
    parser.add_argument('--type', choices=['strong_buy', 'watchlist', 'report'], default='strong_buy')
    parser.add_argument('--send-telegram', action='store_true')
    args = parser.parse_args()

    message = ""
    photo_path = None
    
    if args.type == 'strong_buy':
        message, sig_data = simulate_strong_buy()
        config = load_config()
        df = create_mock_df()
        try:
            photo_path = generate_chart('ASII.JK', df, config)
        except Exception as e:
            print(f"Chart error: {e}")
    elif args.type == 'watchlist':
        message, _ = simulate_watchlist()
    elif args.type == 'report':
        message, _ = simulate_report()

    print("\n[PREVIEW]")
    print(message)
    if photo_path:
        print(f"[IMAGE]: {photo_path}")
    print("-" * 30)

    if args.send_telegram:
        await send_telegram(message, photo_path=photo_path)
    else:
        if photo_path and os.path.exists(photo_path):
            os.remove(photo_path)
        print("Use --send-telegram to send.")

if __name__ == "__main__":
    asyncio.run(run_test())
