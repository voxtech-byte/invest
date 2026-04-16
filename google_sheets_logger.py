import os
import json
from datetime import datetime
import pytz

# Fallback basic logger to CSV if Google Sheets is not configured or missing credentials
CSV_FALLBACK_FILE = "trade_history.csv"

# Optional: Add google-api-python-client google-auth-httplib2 google-auth-oauthlib to requirements.txt for real integration

class GoogleSheetsLogger:
    def __init__(self, sheet_id=None, credentials_file="service_account.json"):
        self.sheet_id = sheet_id
        self.credentials_file = credentials_file
        self.is_configured = False
        
        # In a real implementation:
        # if os.path.exists(self.credentials_file) and self.sheet_id:
        #    ... setup gspread or googleapiclient ...
        #    self.is_configured = True
            
        if not self.is_configured:
            print("Google Sheets not configured. Falling back to CSV logging.")
            self._init_csv()

    def _init_csv(self):
        if not os.path.exists(CSV_FALLBACK_FILE):
            with open(CSV_FALLBACK_FILE, 'w') as f:
                f.write("Date,Symbol,Action,Price,Qty,Conviction,Reason,Pnl\n")

    def log_trade(self, symbol, action, price, qty, conviction=0.0, reason="", pnl=0.0):
        """Append a trade row to the sheet or CSV"""
        date_str = datetime.now(pytz.timezone('Asia/Jakarta')).strftime("%Y-%m-%d %H:%M:%S")
        
        if self.is_configured:
            # Here you would append row to Google Sheets
            # sheet.append_row([date_str, symbol, action, price, qty, conviction, reason, pnl])
            pass
        else:
            with open(CSV_FALLBACK_FILE, 'a') as f:
                f.write(f"{date_str},{symbol},{action},{price},{qty},{conviction},{reason},{pnl}\n")
        
        print(f"Logged {action} {symbol} to {'Google Sheets' if self.is_configured else 'CSV'}")

    def log_portfolio(self, equity, open_positions_count):
        """Save daily portfolio snapshot"""
        # Logic to save to a specific 'Portfolio Log' tab in Sheets
        print(f"[PORTFOLIO] Equity: {equity}, Open Positions: {open_positions_count}")
