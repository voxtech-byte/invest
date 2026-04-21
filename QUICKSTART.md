# Sovereign Quant Terminal V15 — Quickstart Guide

Welcome to **Sovereign V15 PRO**, the institutional-grade quantitative trading companion for the Indonesian Stock Exchange (IDX).

---

## 1. Installation

Sovereign provides 1-click setup scripts to automate virtual environment creation and dependency installation.

### macOS / Linux
Open your terminal and run:
```bash
chmod +x setup_mac.sh
./setup_mac.sh
```

### Windows
Double-click `setup_windows.bat` or run it from the command prompt:
```cmd
setup_windows.bat
```

---

## 2. Configuration & API Keys

Sovereign requires a few credentials to operate fully (Cloud Sync, Telegram Alerts).

1. The installer created a blank `.env` file in your directory. Open it in a text editor.
2. Fill in the following:
   - `TELEGRAM_BOT_TOKEN="your-bot-token"` 
   - `TELEGRAM_CHAT_ID="your-chat-id"`
   - `SUPABASE_URL="your-supabase-url"` *(Optional, for cloud sync)*
   - `SUPABASE_KEY="your-supabase-key"` *(Optional, for cloud sync)*
3. If you want to use Google Sheets to log trades, ensure `service_account.json` is placed in the root directory and you have added your Spreadsheet ID to `config.json`.

**Commercial License**
Open `config.json` and scroll to the bottom. Replace `"YOUR_LICENSE_KEY_HERE"` with the UUID provided upon purchase.

---

## 3. Starting the Engine

Once configured, activate your virtual environment (if not already active) and launch the terminal:

### macOS / Linux
```bash
source .venv/bin/activate
streamlit run app.py
```

### Windows
```cmd
call .venv\Scripts\activate.bat
streamlit run app.py
```

---

## 4. First Run Operations

1. **Check System Health**: Look at the Sidebar. Click **Run Health Check**. Ensure all services show a green `✅` checkmark.
2. **Review Config**: Check if any warnings appear below the Health Check. Sovereign has a built-in strict validator that catches misconfigurations.
3. **Paper Mode**: Turn on the `AUTO-PILOT` toggle. Ensure the `📄 PAPER MODE` badge is visible. Let the bot run through a few cycles to populate the Equity Curve and Sector Heatmap.

---

*Need support? Contact VoxTech Client Success.*
