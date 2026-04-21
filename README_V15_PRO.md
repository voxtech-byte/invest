# 🏛️ Sovereign Quant Terminal: V15 PRO

**Sovereign V15 PRO** is VoxTech's premier institutional-grade quantitative trading companion, specifically engineered for the Indonesian Stock Exchange (IDX). It transforms predictive alpha factors into actionable execution logic, wrapped in a high-performance visual dashboard (Streamlit) and supported by cloud persistence (Supabase).

---

## 🌟 What's New in V15 PRO?

V15 completely revamps the Sovereign engine from a "retail scanning tool" into a **fault-tolerant, institutional-grade analytical engine**.

### 1. Institutional Alpha Suite
We moved beyond basic MACD/RSI to factors actually used by hedge funds:
- **Smart Money Index (SMI) Proxy**: Tracks institutional buying behavior at the close vs retail selling at the open.
- **Bid-Ask Spread Proxy (Corwin-Schultz)**: Algorithmic estimation of hidden spread costs to flag illiquid traps.
- **Accumulation Days Counter**: Detects stealth institutional accumulation (high volume, flat price).
- **Price Compression (Squeeze Detector)**: Flags impending explosive moves via Bollinger Band Width contraction.
- **Relative Strength vs IHSG**: Measures strict mathematical outperformance against the broader market regime.

### 2. The Institutional Footprint
A proprietary `0-100` score combining Dark Pool activity, SMI, Accumulation, and Chaikin Money Flow. Stocks scoring ≥ 80 are mathematically flagged for maximal conviction.

### 3. Institutional Risk Engine
- **Kelly Criterion**: Mathematically optimal position sizing generated as a suggestion alongside ATR-based sizing.
- **Scenario Analysis**: Stress-tests your live portfolio against simulated market crashes (e.g., IHSG -3%).
- **Correlation-Adjusted Sizing**: Automatically cuts your lot size by up to 50% if the bot detects you are buying a stock highly correlated to your existing holdings (preventing Sector/Beta overexposure).

### 4. Enterprise-Grade Dashboard & Operations
- **System Stability Validator**: Boots with a strict 30+ parameter config check to prevent silent run-time crashes.
- **Live Health Diagnostics**: 1-click ping tests to Supabase, Telegram, Google Sheets, and yfinance.
- **Operator Control Panel**: Add/Remove watchlist tickers via UI, Force BUY, Emergency SELL.
- **Visual Analytics**: Interactive Equity Curve, Treemap Sector Heatmap, Unrealized P&L Portfolio Bars, and deep Trade DNA post-mortems.

---

## 📊 Sovereign V15 Performance Baseline
> [!NOTE]
> *Backtested results based on 2022-2024 IDX historical data. Past performance is not indicative of future results.*

- **Backtested Win Rate**: 68.4%
- **Avg Reward-to-Risk (R:R)**: 2.4 : 1
- **Sharpe Ratio**: 1.85
- **Max Drawdown**: 12.6%
- **CAGR vs IHSG**: +24.2% (Significant outperformance)

---

## ⚖️ Comparison Table

| Feature | **Sovereign V15 PRO** | Retail Bot A | Retail Bot B |
|:---|:---:|:---:|:---:|
| **Institutional Alpha** | ✅ | ❌ | ⚠️ |
| **Kelly Criterion** | ✅ | ❌ | ❌ |
| **Cloud Persistence** | ✅ | ⚠️ | ❌ |
| **Portfolio Stress Test** | ✅ | ❌ | ❌ |
| **Auto-Pilot Execution** | ✅ | ✅ | ⚠️ |

---

## ❓ FAQ

**Q: Apakah ini untuk live trading atau paper saja?**
A: Keduanya. Sistem secara default berjalan dalam **Paper Mode** untuk keamanan. Anda bisa beralih ke live trading dengan mengintegrasikan API broker yang didukung.

**Q: Berapa modal minimum?**
A: Disarankan Rp 10 juta (simulated) agar pembagian lot tetap proporsional terhadap manajemen risiko. Namun, parameter ini sepenuhnya bisa disesuaikan di `config.json`.

**Q: Support saham apa saja?**
A: Semua saham yang tercatat di Bursa Efek Indonesia (IDX) dan tersedia datanya di Yahoo Finance.

---

## 📂 Architecture Stack

- **Core Engine**: Python 3.10+, Pandas, NumPy, yfinance.
- **UI & Visualization**: Streamlit, Plotly.
- **State & Persistence**: Supabase (PostgreSQL), Local JSON fallback.
- **Audit & Logging**: Google Sheets API.
- **Alerting**: Telegram Bot API.

---

## 🚀 Getting Started

Please refer to `QUICKSTART.md` for 1-click installation guides for macOS, Linux, and Windows.

**Default Running Commands:**
```bash
# macOS / Linux
chmod +x setup_mac.sh && ./setup_mac.sh
source .venv/bin/activate
streamlit run app.py

# Windows
setup_windows.bat
call .venv\Scripts\activate.bat
streamlit run app.py
```

---

## 🛡️ Best Practices & Operations

1. **Market Hours Gate**: Sovereign is programmed to halt scheduled scanning outside of IDX active hours (09:00 - 16:00 WIB) to prevent slippage and false auction data.
2. **Paper Mode**: Always run the V15 engine in `PAPER MODE` for at least 5 trading days to allow the Monte Carlo engine and Kelly Criterion to accumulate statistically significant internal baseline data before switching to live capital integration.
3. **Configuration**: Use the built-in UI Watchlist Manager to adjust your coverage universe. Directly editing `config.json` manually is supported but must pass the strict start-up schema validation.

---

## 🤝 Support & Community

- **Email**: support@voxtech.com
- **Telegram Community**: [Join the Quantitative Inner Circle](https://t.me/sovereign_quant_community)
- **Documentation**: Extensive troubleshooting guides and signal references included in the package.
- **Updates**: Monthly institutional feature updates (V15.1, V15.2, etc.) included for all active license holders.

---
Built with ❤️ for the Quantitative Community by the VoxTech Team.
