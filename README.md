# Sovereign Quantitative Terminal (V14 Pro) 🏛️📈

Sovereign is an institutional-grade, automated quantitative trading engine and dashboard built for high-conviction trading in the **Indonesia Stock Exchange (IDX)**. It is the evolution of the Quant Alpha series, moving from simple notifications to a modular, asymmetric command center.

> [!IMPORTANT]
> **Complete Technical Documentation**: For a deep dive into the architecture, engines, and setup, see [README_V14_PRO.md](file:///Users/muhammadnizaralfaris/Documents/saham/README_V14_PRO.md).


## 🏛️ Project Architecture
The system has been transformed into a professional **Modular Architecture**:
- `core/`: Advanced quantitative logic (Signals, Risk, Anomaly Detection).
- `data/`: High-performance data layer with Supabase Cloud + Local JSON fallback.
- `integrations/`: Cloud sync (Google Sheets) and Market Intelligence (News Aggregator).
- `ui/`: Industrial-grade asymmetric dashboard using Streamlit.

## 🛡️ Asymmetric Edge Modules
Sovereign provides metrics typically reserved for institutional desks:
- **Monte Carlo Stress Test**: Simulates 1,000 future price paths to calculate *Probability of Profit* and *Value at Risk (VaR)*.
- **Dark Pool Detection**: Identifies hidden institutional accumulation/distribution using volume anomaly algorithms.
- **Black Swan Alarm**: Volatility-based circuit breaker to detect extreme market tail-risks.
- **Political Risk Gauge**: Real-time sentiment analysis of Indonesian financial news to measure macro "noise."

## 🚀 Setup & Security (Public GitHub Ready)
This repository is configured for **Public Security**. Sensitive keys are handled via environment variables and are excluded from version control.

### 1. Configure Secrets (.env)
Create a `.env` file in the root directory (already in `.gitignore`) and add:
```bash
TELEGRAM_BOT_TOKEN="your_token"
TELEGRAM_CHAT_ID="your_id"
ALPHA_VANTAGE_KEY="your_key"
FCS_API_KEY="your_key"
SPREADSHEET_ID="your_google_sheet_id"
# Optional:
SUPABASE_URL="your_supabase_url"
SUPABASE_KEY="your_supabase_anon_key"
```

### 2. GitHub Actions (Automation)
If deploying to GitHub Actions, add the exact same keys above to your **GitHub Repository Secrets** (`Settings -> Secrets and variables -> Actions`).

### 3. Google Sheets Integration
- Ensure `service_account.json` is present in the root (ignored by Git).
- The system will automatically log all trades to your "Trades" and "Portfolio" sheets.

## 🖥️ Running the Terminal
To launch the Sovereign Dashboard locally:
```bash
streamlit run app.py
```

## ⚙️ Configuration
Adjust trading rules, universe, and conviction weights in `config.json`.
- **Auto-Pilot**: Enable in the UI to perform continuous market sweeps.
- **Execution Gates**: Safety checks for IHSG regime and sector exposure.

***

## ⚠️ Disclaimer
Sovereign is a rule-based quantitative tool. All signals are **probabilistic**. Past performance does not guarantee future results. Maintain strict risk discipline and never trade capital you cannot afford to lose.
