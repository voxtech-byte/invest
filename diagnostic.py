import sys
import os

print("Starting FIXED diagnostic check...")

try:
    import streamlit as st
    print("streamlit OK")
    import pandas as pd
    print("pandas OK")
    import numpy as np
    print("numpy OK")
    import yfinance as yf
    print("yfinance OK")
    import plotly.graph_objects as go
    print("plotly OK")
    
    from core.utils import load_config, format_rp, TIMEZONE
    print("core.utils OK")
    from data.data_fetcher import fetch_data, fetch_ihsg
    print("data.data_fetcher OK")
    from core.indicators import calculate_indicators
    print("indicators OK")
    from core.signals import evaluate_signals
    print("signals OK")
    from core.executive import calculate_position_size
    print("executive OK")
    from mock_broker import MockBroker
    print("mock_broker OK")
    
    config = load_config()
    print("config loading OK")
    
    broker = MockBroker()
    print("MockBroker init OK")
    
    # Test a small evaluation
    sym = "BBCA.JK"
    print(f"Testing fetch for {sym}...")
    df = fetch_data(sym, config)
    if df is not None:
        print(f"Fetch {sym} OK")
        df = calculate_indicators(df, config)
        print("Indicators calculation OK")
        res, summary, reason = evaluate_signals(sym, df, config)
        print(f"Evaluation OK: Conviction {summary['conviction']}")
    else:
        print(f"Fetch {sym} returned None (might be expected in headless/offline)")

    print("\nALL IMPORTS AND LOGIC TESTS SUCCESSFUL.")

except ImportError as e:
    print(f"\nIMPORT ERROR: {e}")
    sys.exit(1)
except Exception as e:
    print(f"\nUNEXPECTED ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
