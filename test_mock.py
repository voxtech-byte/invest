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
        'PVT': [1000 for _ in range(30)],
    }
    df = pd.DataFrame(data, index=dates)
    return df

def simulate_v7_acc():
    print("--- Simulating V7 [INSTITUTIONAL ACCUMULATION] ---")
    data = {
        'type': 'STRONG_BUY', 'confidence': 'HIGH',
        'desc': 'Multiple confirmations align. Smart money footprint detected.',
        'direction': 'BUY', 'score': 9.2,
        'layers': {
            'RSI': 'Oversold (28)', 'MA200': 'Uptrend',
            'BEE-FLOW': 'High Accum (9/10)',
            'Phase': 'MARKUP', 'Volatility': 'SQUEEZE'
        },
        'data': {
            'symbol': 'ASII.JK', 'close': 6175, 'rsi': 28.0,
            'ma200': 5886, 'ma50': 6100, 'vol': 8500000, 'vol_ratio': 2.1,
            'pct_1d': 1.8, 'pattern': 'Hammer',
            'vol_context': 'Strong Accumulation',
            'wyckoff_phase': 'MARKUP (Strong Trend)',
            'bee_score': 9, 'bee_label': 'HIGH ACCUMULATION (BIG BEE)',
            'is_squeeze': True,
            'macd_hist': 15.5, 'bb_lower': 6050, 'bb_upper': 6500,
            'support': 6000, 'resistance': 6800, 'atr': 85,
            'entry_low': 6100, 'entry_high': 6180,
            'stop_loss': 5900, 'target_1': 6450, 'target_2': 6800,
            'rrr_1': 1.0, 'rrr_2': 2.3, 'risk_pct': 2.0,
            'buy_score': 9.2, 'sell_score': 0, 'trend': 'BULLISH'
        }
    }
    return format_alert(data), data

def simulate_v7_dist():
    print("--- Simulating V7 [DISTRIBUTION WARNING] ---")
    data = {
        'type': 'WATCHLIST_SELL', 'confidence': 'MEDIUM',
        'desc': 'Bandar mulai jualan barang di area resisten.',
        'direction': 'SELL', 'score': 3.5,
        'layers': {
            'RSI': 'Overbought (75)',
            'BEE-FLOW': 'Distribution (2/10)'
        },
        'data': {
            'symbol': 'BBCA.JK', 'close': 10450, 'rsi': 75.0,
            'ma200': 9800, 'ma50': 10100, 'vol': 45000000, 'vol_ratio': 1.8,
            'pct_1d': -0.5, 'pattern': 'Shooting Star',
            'vol_context': 'Institutional Distribution',
            'wyckoff_phase': 'DISTRIBUTION (Institutions Selling)',
            'bee_score': 2, 'bee_label': 'DISTRIBUTION (EXITING)',
            'is_squeeze': False,
            'macd_hist': -1.2, 'bb_lower': 9900, 'bb_upper': 10600,
            'support': 10000, 'resistance': 10550, 'atr': 150,
            'entry_low': 0, 'entry_high': 0,
            'stop_loss': 10200, 'target_1': 9800, 'target_2': 9500,
            'rrr_1': 0, 'rrr_2': 0, 'risk_pct': 2.0,
            'buy_score': 0, 'sell_score': 3.5, 'trend': 'BULLISH'
        }
    }
    return format_alert(data), data

def simulate_v7_report():
    print("--- Simulating V7.1 CINEMATIC REPORT ---")
    ihsg = {'close': 6850, 'pct_1d': -0.3, 'trend': 'BEARISH'}
    stocks = [
        {'symbol': 'BBCA.JK', 'close': 10450, 'trend': 'BULLISH', 'bee_score': 2, 'bee_label': 'DISTRIBUTION', 'wyckoff_phase': 'DISTRIBUTION', 'macd_hist': 12.0, 'pct_1d': -0.5, 'rsi': 65, 'support': 10000, 'resistance': 10800, 'pattern': 'Doji'},
        {'symbol': 'ASII.JK', 'close': 6175, 'trend': 'BULLISH', 'bee_score': 9, 'bee_label': 'HIGH ACCUMULATION', 'wyckoff_phase': 'MARKUP', 'macd_hist': 15.5, 'pct_1d': 1.8, 'rsi': 52, 'support': 5675, 'resistance': 7475, 'pattern': ''},
        {'symbol': 'PGAS.JK', 'close': 1700, 'trend': 'BULLISH', 'bee_score': 5, 'bee_label': 'MILD ACCUM', 'wyckoff_phase': 'ACCUMULATION', 'macd_hist': 2.1, 'pct_1d': 0.6, 'rsi': 45, 'support': 1600, 'resistance': 1850, 'pattern': 'Hammer'},
        {'symbol': 'BBNI.JK', 'close': 3710, 'trend': 'BEARISH', 'bee_score': 1, 'bee_label': 'DISTRIBUTION', 'wyckoff_phase': 'MARKDOWN', 'macd_hist': -5.0, 'pct_1d': -1.2, 'rsi': 38, 'support': 3500, 'resistance': 4100, 'pattern': ''},
    ]
    return format_status_report(stocks, ihsg_data=ihsg), None

async def run_test():
    parser = argparse.ArgumentParser(description="V7 Cinematic Intelligence Mock Test")
    parser.add_argument('--type', choices=['acc', 'dist', 'report'], default='acc')
    parser.add_argument('--send-telegram', action='store_true')
    args = parser.parse_args()

    message = ""
    photo_path = None
    
    if args.type == 'acc':
        message, sig_data = simulate_v7_acc()
        config = load_config()
        df = create_mock_df()
        try:
            photo_path = generate_chart('ASII.JK', df, config)
        except Exception as e:
            print(f"Chart error: {e}")
    elif args.type == 'dist':
        message, _ = simulate_v7_dist()
    elif args.type == 'report':
        message, _ = simulate_v7_report()

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
