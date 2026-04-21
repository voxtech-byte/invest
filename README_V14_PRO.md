# Sovereign Quant Terminal V14 Pro — Documentation 🏛️📈

Welcome to the official technical documentation for **Sovereign V14 Pro**. This system is an institutional-grade, modular quantitative trading command center designed for the Indonesia Stock Exchange (IDX).

---

## 🏗️ 1. Architecture Overview
The terminal is built on a **Modular Micro-Engine Architecture** to ensure stability, scalability, and easy logic swaps.

- **`main.py`**: The central orchestrator (Sweep Engine). Handles the 2-pass scan, automation, and cloud syncing.
- **`core/`**: The "Brain" of the system.
  - `signals.py`: The weighted conviction scoring engine.
  - `indicators.py`: High-performance technical factor calculation (SMA, ATR, CMF, RSI, VWAP).
  - `wyckoff.py`: Phase detection and supply/demand relationship parser.
  - `monte_carlo.py`: Geometric Brownian Motion (GBM) stress-tester.
  - `sector_rotation.py`: Market breadth and momentum parser.
  - `executive.py`: Risk management circuit breakers & position sizing.
- **`data/`**: The Persistence Layer.
  - `database.py`: Supabase (Cloud) + JSON (Local Fallback) manager.
  - `data_fetcher.py`: Standardized API for yfinance/IDX data.
- **`integrations/`**: The Communication Layer.
  - `alerts.py`: Rich Telegram formatting & dispatch.
  - `google_sheets_logger.py`: Financial logging to Google Sheets.
- **`app.py`**: The User Interface. Streamlit-based asymmetric command center.

---

## 🧠 2. Core Intelligent Engines

### 2.1 Wyckoff Phase Detection
The system uses a rule-based relationship parser to identify the current institutional cycle:
- **ACCUMULATION**: Institutions are building positions (Support binds).
- **MARKUP**: Price is trending higher with volume consensus (Best entry).
- **DISTRIBUTION**: Institutions are offloading (Sell warning).
- **MARKDOWN**: Liquidation trend (Avoid).
- **SPRING/UPTHRUST**: Detection of professional "shakeouts" or "bull traps" which act as conviction modifiers.

### 2.2 Monte Carlo Stress Test
The system runs 1,000 iterations of a price simulation using the last 60-120 days of volatility:
- **Probability of Profit**: % likelihood that price stays above entry after 10 days.
- **VaR 95**: The "Value at Risk" reflecting the 5th percentile worst-case scenario.
- **Risk Rating**: Automatically calculated (LOW/MODERATE/HIGH). HIGH risk status triggers an automatic **-0.5 Conviction Penalty**.

### 2.3 Sector Rotation Analysis
Every sweep cycle begins with a **Pre-Scan** of the entire universe to calculate sector health:
- **HOT Rating**: Awarded if the sector has positive 20-day momentum and >50% breadth (member participation).
- **Conviction Bonus**: Stocks in HOT sectors receive an automatic **+0.5 Conviction Bonus** to capture capital flow tailwinds.

---

## ⚡ 3. Signal & Execution Logic

### 3.1 Weighted Conviction Scoring
Conviction is a 0.0 to 10.0 score based on 5 parameters:
1. **Smart Money (35%)**: Volume Ratio & CMF (Chaikin Money Flow).
2. **Trend (25%)**: Price vs SMA200 & ADX strength.
3. **Internal Phase (20%)**: RSI location & minor Wyckoff alignment.
4. **Volatility (15%)**: ATR ranges & Bollinger expansion.
5. **Macro (5%)**: IHSG alignment.

### 3.2 Entry Execution Gates
Before the bot triggers a **BUY**, it must pass 4 strict gates:
- **Threshold**: Score must be `> 6.5` (Auto-Buy) or `> 4.5` (Alert).
- **Market Hours**: Must be within IDX trading sessions (checked via `Asia/Jakarta` timezone).
- **Liquidity**: Avg daily trading value must exceed **Rp 5 Billion**.
- **Portfolio Heat**: Aggregate risk-at-stake must not exceed **6.0%** of total equity.
- **Reentry Cooldown**: A 3-day block is applied to any stock that hit a Stop Loss recently.

### 3.3 Exit Strategy (Multiple Triggers)
The system is "Exit-Aggressive" to protect capital:
- **Stop Loss**: ATR-based dynamic floor.
- **Partial TP (TP1)**: Sells 50% at Target 1 and trails the rest.
- **Momentum Distribution**: RSI > 75 + Volume Spike > 2.0x (Distribution).
- **VWAP Rejection**: Close below VWAP for 2+ days while in negative P&L.
- **SMA50 Breach**: Trend failure indicator after 3 days holding.
- **Stale Exit**: Forces exit if no profit is made after 14 days.

---

## 📡 4. Monitoring & Reporting

### 4.1 Telegram Alerts
Every significant event (BUY/SELL/TP1/SCAN) is sent to Telegram with:
- Rich ASCII headers.
- Visual conviction bars.
- Monte Carlo risk metrics.
- IHSG volatility regime context.

### 4.2 Dashboard Hub
Run `streamlit run app.py` to access:
- **Live Order Flow**: Automated chart rendering and real-time logs.
- **Institutional Data Hub**: Advanced CSV export for all quantitative factors.
- **Correlation Matrix**: Institutional-grade heatmap of your current portfolio risk.

---

## 🛠️ 5. Deployment & Maintenance

### Setup Steps:
1. **Env Vars**: Fill `.env` with API keys (Telegram, Supabase, Google Sheets).
2. **Supabase**: Run `supabase_init.sql` in your Supabase SQL Editor.
3. **Automation**: The `.github/workflows/stock-notifier.yml` is configured to run at market open and close automatically.

---

## 🏛️ Credits
**Sovereign V14 Pro** | *Designed for voxtech-byte/invest*
*Performance focused. Probabilistically centered. Institutional logic.*
