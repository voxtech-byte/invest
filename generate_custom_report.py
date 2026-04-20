import pandas as pd
import os
import yfinance as yf
from data.data_fetcher import fetch_data, fetch_ihsg
from core.indicators import calculate_indicators
from core.signals import evaluate_signals
from core.utils import load_config, generate_chart
import warnings
warnings.filterwarnings('ignore')

stocks = ["ACES.JK", "BUKA.JK", "ENRG.JK", "MORA.JK", "GPRA.JK", "CMPP.JK", "BULL.JK"]
config = load_config()
ihsg_data = fetch_ihsg(config)

results = []
os.makedirs("report_charts", exist_ok=True)

for sym in stocks:
    print(f"Processing {sym}...")
    df = fetch_data(sym, config)
    if df is not None and not df.empty:
        df = calculate_indicators(df, config)
        signal_data, status_summary, reason = evaluate_signals(sym, df, config, ihsg_data=ihsg_data)
        
        # Save chart
        chart_path = f"report_charts/{sym.replace('.JK', '')}_chart.png"
        chart_file = generate_chart(sym, df.tail(120), config)
        if chart_file and os.path.exists(chart_file):
            os.replace(chart_file, chart_path)
            
        last = df.iloc[-1]
        
        if status_summary:
            results.append({
                "Symbol": sym,
                "Price": status_summary.get('close'),
                "Trend": status_summary.get('trend'),
                "Conviction": status_summary.get('conviction'),
                "Wyckoff Phase": status_summary.get('wyckoff_phase'),
                "Volume Spike": last.get('vol_ratio', 0),
                "RSI": last.get('RSI_14', 50),
                "Reason/Filter": "Analyzed successfully"
            })
        else:
            results.append({
                "Symbol": sym,
                "Price": last['Close'],
                "Trend": "Filtered",
                "Conviction": 0,
                "Wyckoff Phase": "N/A",
                "Volume Spike": last.get('vol_ratio', 0),
                "RSI": last.get('RSI_14', 50),
                "Reason/Filter": reason
            })
    else:
        results.append({
            "Symbol": sym,
            "Price": 0,
            "Trend": "Error",
            "Conviction": 0,
            "Wyckoff Phase": "Error",
            "Volume Spike": 0,
            "RSI": 0,
            "Reason/Filter": "Data fetch failed"
        })

df_res = pd.DataFrame(results)
df_res.to_csv("special_report.csv", index=False)
print("Report saved to special_report.csv")
