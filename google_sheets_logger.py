import os
import json
from datetime import datetime
import pytz
import gspread
from google.oauth2.service_account import Credentials

# Fallback basic logger to CSV if Google Sheets is not configured or missing credentials
CSV_FALLBACK_FILE = "trade_history.csv"

class GoogleSheetsLogger:
    def __init__(self, sheet_id=None, credentials_file="service_account.json"):
        self.sheet_id = sheet_id
        self.credentials_file = credentials_file
        self.is_configured = False
        self.client = None
        self.spreadsheet = None
        
        if os.path.exists(self.credentials_file) and self.sheet_id:
            try:
                scopes = [
                    "https://www.googleapis.com/auth/spreadsheets",
                    "https://www.googleapis.com/auth/drive"
                ]
                credentials = Credentials.from_service_account_file(self.credentials_file, scopes=scopes)
                self.client = gspread.authorize(credentials)
                self.spreadsheet = self.client.open_by_key(self.sheet_id)
                self.is_configured = True
                self._prepare_sheets()
                print("✅ Google Sheets connected successfully.")
            except Exception as e:
                print(f"❌ Google Sheets config error: {e}. Falling back to CSV.")
        else:
            print("⚠️ Google Sheets not fully configured (missing .json or sheet_id). Falling back to CSV.")
            self._init_csv()

    def _prepare_sheets(self):
        """Ensure core sheets exist with headers"""
        # 1. Trades Sheet
        try:
            trade_sheet = self.spreadsheet.worksheet("Trades")
        except gspread.exceptions.WorksheetNotFound:
            trade_sheet = self.spreadsheet.add_worksheet(title="Trades", rows="1000", cols="10")
            trade_sheet.append_row(["Date", "Symbol", "Action", "Price", "Qty", "Conviction", "Reason", "Pnl", "Total Value"])
            
        # 2. Portfolio Sheet
        try:
            port_sheet = self.spreadsheet.worksheet("Portfolio")
        except gspread.exceptions.WorksheetNotFound:
            port_sheet = self.spreadsheet.add_worksheet(title="Portfolio", rows="1000", cols="5")
            port_sheet.append_row(["Date", "Cash Balance", "Open Positions", "Total Pnl", "Last Update"])

    def _init_csv(self):
        if not os.path.exists(CSV_FALLBACK_FILE):
            with open(CSV_FALLBACK_FILE, 'w') as f:
                f.write("Date,Symbol,Action,Price,Qty,Conviction,Reason,Pnl\n")

    def log_trade(self, symbol, action, price, qty, conviction=0.0, reason="", pnl=0.0):
        """Append a trade row to the sheet or CSV"""
        date_str = datetime.now(pytz.timezone('Asia/Jakarta')).strftime("%Y-%m-%d %H:%M:%S")
        total_value = price * qty
        
        if self.is_configured:
            try:
                sheet = self.spreadsheet.worksheet("Trades")
                sheet.append_row([date_str, symbol, action, float(price), int(qty), float(conviction), reason, float(pnl), float(total_value)])
            except Exception as e:
                print(f"Error logging to GSheets: {e}")
        
        # Always log to CSV as backup
        with open(CSV_FALLBACK_FILE, 'a') as f:
            f.write(f"{date_str},{symbol},{action},{price},{qty},{conviction},{reason},{pnl}\n")
        
        print(f"Logged {action} {symbol} to {'Google Sheets + CSV' if self.is_configured else 'CSV'}")

    def log_portfolio(self, equity, open_positions_count, total_unrealized_pnl=0.0):
        """Save daily portfolio snapshot"""
        date_str = datetime.now(pytz.timezone('Asia/Jakarta')).strftime("%Y-%m-%d %H:%M:%S")
        
        if self.is_configured:
            try:
                sheet = self.spreadsheet.worksheet("Portfolio")
                sheet.append_row([date_str, float(equity), int(open_positions_count), float(total_unrealized_pnl), "Updated"])
                print("✅ Portfolio data logged to Google Sheets.")
            except Exception as e:
                print(f"❌ Error logging portfolio to GSheets: {e}")
        
        print(f"[PORTFOLIO] Equity: {equity}, Open Positions: {open_positions_count}")
