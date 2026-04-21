import pandas as pd
try:
    import pandas_ta as ta
except ImportError:
    import pandas_ta_classic as ta
from typing import Any


def calculate_indicators(df: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    """
    Standard Quantitative Indicator Suite.
    Includes RSI, MAs, MACD, BB, PVT, OBV, CMF, ATR, ADX, and VWAP.
    """
    ind_cfg = config['indicators']
    df = df.sort_index()

    # RSI & Momentum
    df.ta.rsi(length=ind_cfg['rsi_length'], append=True)
    df['Pct_Change_1D'] = df['Close'].pct_change() * 100
    df['Pct_Change_5D'] = df['Close'].pct_change(periods=5) * 100

    # Drop from Peak (Drawdown proxy)
    if 'Peak_Price' not in df.columns:
        lookback = config['signals'].get('price_peak_lookback_days', 90)
        df['Peak_Price'] = df['High'].rolling(window=lookback, min_periods=1).max()
    df['Drop_From_Peak_Pct'] = ((df['Peak_Price'] - df['Close']) / df['Peak_Price']) * 100

    # Moving Averages
    df.ta.sma(length=ind_cfg['ma_short'], append=True)
    df.ta.sma(length=ind_cfg['ma_long'], append=True)

    # MACD
    df.ta.macd(fast=ind_cfg['macd_fast'], slow=ind_cfg['macd_slow'], signal=ind_cfg['macd_signal'], append=True)

    # Bollinger Bands
    df.ta.bbands(length=ind_cfg['bb_period'], std=ind_cfg['bb_std'], append=True)

    # BB Width for Squeeze Detection
    bbu_col = [c for c in df.columns if c.startswith(f"BBU_{ind_cfg['bb_period']}")]
    bbl_col = [c for c in df.columns if c.startswith(f"BBL_{ind_cfg['bb_period']}")]
    bbm_col = [c for c in df.columns if c.startswith(f"BBM_{ind_cfg['bb_period']}")]

    if bbu_col and bbl_col and bbm_col:
        df['BB_Width'] = (df[bbu_col[0]] - df[bbl_col[0]]) / df[bbm_col[0]]
    else:
        df['BB_Width'] = 0.0

    # Volume & Money Flow
    df.ta.pvt(append=True)
    df.ta.obv(append=True)
    df.ta.cmf(length=20, append=True)

    # Volatility & Trend Strength
    df.ta.atr(length=ind_cfg['atr_period'], append=True)
    df.ta.adx(length=14, append=True)

    # Volume Average
    df['Vol_Avg'] = df['Volume'].rolling(window=ind_cfg['volume_avg_period']).mean()

    # Support & Resistance
    sr_days = ind_cfg['sr_lookback_days']
    df['Support_Level'] = df['Low'].rolling(window=sr_days, min_periods=1).min()
    df['Resistance_Level'] = df['High'].rolling(window=sr_days, min_periods=1).max()

    # ── VWAP (Volume Weighted Average Price) ──
    # Using pandas_ta VWAP — requires High, Low, Close, Volume columns
    try:
        df.ta.vwap(append=True)
    except Exception:
        # Manual VWAP calculation as fallback
        typical_price = (df['High'] + df['Low'] + df['Close']) / 3
        cum_vol = df['Volume'].cumsum()
        cum_tp_vol = (typical_price * df['Volume']).cumsum()
        df['VWAP_D'] = cum_tp_vol / cum_vol

    # ══════════════════════════════════════════════════════════════
    # V15 ALPHA INDICATORS
    # ══════════════════════════════════════════════════════════════

    # ── 1. Smart Money Index (SMI) Proxy ──
    # Measures institutional dominance using daily OHLC.
    # High ratio = Close near High & Open near Low = smart money bought at close.
    candle_range = df['High'] - df['Low']
    body = df['Close'] - df['Open']
    df['SMI_Ratio'] = body / candle_range.replace(0, float('nan'))
    df['SMI_Ratio'] = df['SMI_Ratio'].fillna(0.0)
    # Rolling 10-day average for smoothing
    df['SMI_10'] = df['SMI_Ratio'].rolling(window=10, min_periods=3).mean()

    # ── 2. Bid-Ask Spread Proxy (Corwin-Schultz) ──
    # Uses High-Low range ratio across consecutive bars to estimate spread.
    # Higher spread = less liquid = harder institutional exit.
    import numpy as np
    beta = (
        (np.log(df['High'] / df['Low'])) ** 2
    ).rolling(window=2).sum()
    gamma = (
        np.log(
            df['High'].rolling(2).max() / df['Low'].rolling(2).min()
        )
    ) ** 2
    alpha_cs = (
        (np.sqrt(2 * beta) - np.sqrt(beta)) / (3 - 2 * np.sqrt(2))
        - np.sqrt(gamma / (3 - 2 * np.sqrt(2)))
    )
    df['Spread_Proxy'] = (2 * (np.exp(alpha_cs) - 1) / (1 + np.exp(alpha_cs))).clip(lower=0)
    df['Spread_Proxy'] = df['Spread_Proxy'].fillna(0.0)
    df['Spread_Flag'] = df['Spread_Proxy'] > 0.02  # Flag if estimated spread > 2%

    # ── 3. Accumulation Days Counter ──
    # Counts consecutive days where volume > average AND price is flat (<1% change).
    vol_above_avg = df['Volume'] > df['Vol_Avg']
    price_flat = df['Close'].pct_change().abs() < 0.01

    accum_condition = vol_above_avg & price_flat
    # Build a streak counter
    accum_streak = accum_condition.astype(int)
    # Reset streak on False
    groups = (~accum_condition).cumsum()
    df['Accum_Days'] = accum_streak.groupby(groups).cumsum()

    # ── 4. Price Compression Detector (Squeeze) ──
    # BB_Width shrinking for N consecutive days = impending volatility expansion.
    bb_width_decreasing = df['BB_Width'] < df['BB_Width'].shift(1)
    squeeze_groups = (~bb_width_decreasing).cumsum()
    df['Squeeze_Days'] = bb_width_decreasing.astype(int).groupby(squeeze_groups).cumsum()
    df['Is_Squeeze'] = df['Squeeze_Days'] >= 5  # 5+ days of compression

    # ── 5. Relative Strength vs IHSG ──
    # Will be populated in main.py after IHSG data is available.
    # Placeholder column — filled by `enrich_relative_strength()`.
    if 'RS_vs_IHSG' not in df.columns:
        df['RS_vs_IHSG'] = 0.0

    return df


def enrich_relative_strength(df: pd.DataFrame, ihsg_df: pd.DataFrame, lookback: int = 20) -> pd.DataFrame:
    """
    Calculate rolling relative strength of a stock vs IHSG.
    Positive = stock outperforms IHSG. Called after IHSG data is fetched.

    Args:
        df: Stock DataFrame with Close prices.
        ihsg_df: IHSG DataFrame with Close prices.
        lookback: Rolling window for comparison.
    """
    if ihsg_df is None or ihsg_df.empty or len(df) < lookback:
        return df

    try:
        # Align by date index
        stock_ret = df['Close'].pct_change(periods=lookback)
        ihsg_ret = ihsg_df['Close'].pct_change(periods=lookback)

        # Reindex IHSG to stock's dates
        ihsg_aligned = ihsg_ret.reindex(df.index, method='nearest')
        df['RS_vs_IHSG'] = ((stock_ret - ihsg_aligned) * 100).fillna(0.0)
    except Exception:
        df['RS_vs_IHSG'] = 0.0

    return df

