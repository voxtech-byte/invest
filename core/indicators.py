import pandas as pd
import pandas_ta as ta
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

    return df
