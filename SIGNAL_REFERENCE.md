# Sovereign V15 PRO — Signal Reference Guide

This document explains the mathematical triggers and logic behind the Sovereign V15 PRO conviction scoring system.

---

## 1. Conviction Score (0 - 10)

The **Conviction Score** is a weighted composite of multiple quantitative factors. A higher score represents a higher probability of success according to the institutional model.

- **0 - 3 (LOW)**: High noise, no clear institutional footprint. Avoid.
- **4 - 6 (NEUTRAL)**: Early stage build-up or consolidation. Add to watchlist.
- **7 - 8 (HIGH)**: Strong institutional footprint confirmed. Prime candidate for entry.
- **9 - 10 (MAX)**: Squeeze detected + Dynamic momentum + RS outperformance. Immediate focus ticker.

---

## 2. Institutional Alpha Indicators

### 🛡️ Smart Money Index (SMI)
- **Logic**: Compares price action during the first 30 minutes of trading (Retail bias) vs. the last 30 minutes (Institutional bias).
- **Bullish**: Price closes near highs after late-session volume spikes.
- **Bearish**: Early morning excitement faded by heavy distribution at the close.

### 🔍 Accumulation Days
- **Logic**: Tracks days where price remains relatively flat while volume is significantly above the 20-day average.
- **Interpretation**: Stealth buying by larger players preparing for a breakout.

### 🚀 Squeeze Detector (Price Compression)
- **Logic**: Based on Bollinger Band Width contraction relative to historical volatility.
- **Interpretation**: Low volatility periods are almost always followed by high volatility. A squeeze + volume build-up = Explosive move incoming.

### 📈 Relative Strength (RS) vs IHSG
- **Logic**: Calculates the Alpha of a stock compared to the ^JKSE benchmark.
- **Bullish**: Stocks gaining 2% while IHSG gains 0.5% (or stocks staying flat while IHSG drops 2%).
- **Interpretation**: Institutional protection. These stocks lead the market on the next rebound.

---

## 3. Exit Triggers

Sovereign doesn't just track entries. It manages exits dynamically:

- **TP1 (Scale Out)**: Triggered at 1.5x - 2.0x ATR profit.
- **Trailing Stop**: Activates after TP1 to lock in at least 50% of peak gains.
- **Momentum Exit**: RSI > 78 + Volume Spikes on a flat candle (Wyckoff Upthrust).
- **Trend Termination**: Close below MA50 on high volume.

---
*For deep-dive backtest data on these signals, refer to the backtest logs in the `logs/` directory.*
