import yfinance as yf
import pandas as pd
import requests
import json
import os
import time
from typing import Any, Dict, Optional, Union
from logger import get_logger
from core.corporate_actions import apply_corporate_actions_filter

logger = get_logger(__name__)


# ══════════════════════════════════════════════════════════════
# DATA FETCHERS (Multi-Source with Fallback)
# ══════════════════════════════════════════════════════════════

def _fetch_yfinance(symbol: str, config: dict[str, Any], period: str = "1y") -> Optional[pd.DataFrame]:
    try:
        stock = yf.Ticker(symbol)
        df = stock.history(period=period, interval="1d")
        if df.empty:
            return None
        df = df[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
        try:
            info = stock.info
            df.attrs['pe_ratio'] = info.get('trailingPE')
            df.attrs['pbv'] = info.get('priceToBook')
            df.attrs['market_cap'] = info.get('marketCap')
        except:
            pass
        return df
    except Exception as e:
        logger.debug(f"[{symbol}] yfinance error: {e}")
        return None

def _fetch_alphavantage(symbol: str, config: dict[str, Any]) -> Optional[pd.DataFrame]:
    api_keys = config.get('api_keys', {})
    key = api_keys.get('alpha_vantage')
    if not key or key == "YOUR_KEY" or "YOUR_" in key:
        return None
    try:
        url = f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol={symbol}&apikey={key}&outputsize=compact"
        response = requests.get(url, timeout=10)
        data = response.json()
        time_series = data.get("Time Series (Daily)")
        if not time_series:
            return None
        df = pd.DataFrame.from_dict(time_series, orient='index')
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()
        df = df.rename(columns={
            "1. open": "Open", "2. high": "High", "3. low": "Low",
            "4. close": "Close", "5. volume": "Volume"
        })
        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        return df.tail(250)
    except Exception as e:
        logger.debug(f"[{symbol}] Alpha Vantage error: {e}")
        return None

def _fetch_fcsapi(symbol: str, config: dict[str, Any]) -> Optional[pd.DataFrame]:
    api_keys = config.get('api_keys', {})
    key = api_keys.get('fcs_api')
    if not key or key == "YOUR_KEY" or "YOUR_" in key:
        return None
    try:
        url = f"https://fcsapi.com/api-v3/stock/history?symbol={symbol}&period=1d&access_key={key}"
        response = requests.get(url, timeout=10)
        data = response.json()
        if not data.get('status'):
            return None
        history = data.get('response', [])
        if not history: return None
        df = pd.DataFrame(history)
        df = df.rename(columns={'o': 'Open', 'h': 'High', 'l': 'Low', 'c': 'Close', 'v': 'Volume', 't': 'Date'})
        df['Date'] = pd.to_datetime(df['Date'], unit='s')
        df.set_index('Date', inplace=True)
        df = df.sort_index()
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        return df
    except Exception as e:
        logger.debug(f"[{symbol}] FCS API error: {e}")
        return None


# ══════════════════════════════════════════════════════════════
# MAIN FETCH WITH SUSPEND/DELIST DETECTION
# ══════════════════════════════════════════════════════════════

def _is_suspended(df: pd.DataFrame, symbol: str) -> bool:
    """
    Detect if a stock is suspended or delisted.
    Indicators: zero volume for last N days, or flatline closing prices.
    """
    if df is None or df.empty:
        return True

    # Check last 5 trading days
    recent = df.tail(5)
    if len(recent) < 3:
        return True

    # All volumes are zero → likely suspended
    if (recent['Volume'] == 0).all():
        logger.warning(f"[{symbol}] Likely SUSPENDED: Zero volume for {len(recent)} consecutive days")
        return True

    # Flat closing price for 5+ days → possibly halted
    if recent['Close'].nunique() == 1 and len(recent) >= 5:
        logger.warning(f"[{symbol}] Likely HALTED: Flat close price for {len(recent)} days")
        return True

    return False


def fetch_data(symbol: str, config: dict[str, Any]) -> Optional[pd.DataFrame]:
    """
    Multi-source data fetcher with suspend/delist detection and retry.
    """
    df = _fetch_yfinance(symbol, config)
    source = "yfinance"

    if df is None or df.empty:
        df = _fetch_alphavantage(symbol, config)
        source = "Alpha Vantage"
    if df is None or df.empty:
        df = _fetch_fcsapi(symbol, config)
        source = "FCS API"
    if df is None or df.empty:
        logger.warning(f"[{symbol}] No data from any source — skipping")
        return None

    # Suspend/delist check
    if _is_suspended(df, symbol):
        return None
    
    # Corporate actions detection and adjustment (splits, etc.)
    df = apply_corporate_actions_filter(df, symbol, config)

    logger.info(f"[{symbol}] Data successfully fetched via {source} ({len(df)} rows)")
    try:
        lookback = config['signals']['price_peak_lookback_days']
        df['Peak_Price'] = df['High'].rolling(window=lookback, min_periods=1).max()
    except:
        pass
    return df


# ══════════════════════════════════════════════════════════════
# IHSG FETCH WITH FILE-BACKED PERSISTENT CACHE
# ══════════════════════════════════════════════════════════════

IHSG_CACHE_FILE = "ihsg_cache.json"
IHSG_CACHE_TTL = 300  # 5 minutes

# In-memory cache for same-process reuse
_IHSG_MEMORY_CACHE = {"data": None, "timestamp": 0}


def fetch_ihsg(config: dict[str, Any]) -> Optional[dict[str, Any]]:
    """
    Fetch IHSG data with dual-layer caching:
    1. In-memory (for same process, e.g. Streamlit rerun)
    2. File-backed (for cross-process, e.g. GHA ephemeral runners)
    """
    global _IHSG_MEMORY_CACHE
    now = time.time()

    # ── Layer 1: In-memory cache ──
    if _IHSG_MEMORY_CACHE["data"] and (now - _IHSG_MEMORY_CACHE["timestamp"] < IHSG_CACHE_TTL):
        logger.debug("IHSG: served from memory cache")
        return _IHSG_MEMORY_CACHE["data"]

    # ── Layer 2: File-backed cache ──
    if os.path.exists(IHSG_CACHE_FILE):
        try:
            with open(IHSG_CACHE_FILE, 'r') as f:
                cached = json.load(f)
            cache_age = now - cached.get("timestamp", 0)
            if cache_age < IHSG_CACHE_TTL:
                ihsg_data = cached["data"]
                _IHSG_MEMORY_CACHE = {"data": ihsg_data, "timestamp": cached["timestamp"]}
                logger.debug(f"IHSG: served from file cache (age: {cache_age:.0f}s)")
                return ihsg_data
        except Exception as e:
            logger.debug(f"IHSG cache file read error: {e}")

    # ── Layer 3: Fresh fetch from yfinance ──
    try:
        symbol = config.get('macro', {}).get('index_symbol', '^JKSE')
        regime_cfg = config.get('regime', {})
        atr_short = regime_cfg.get('ihsg_atr_short', 20)
        atr_long = regime_cfg.get('ihsg_atr_long', 60)

        ticker = yf.Ticker(symbol)
        # Fetch 3 months for rolling ATR regime classification
        df = ticker.history(period="3mo")
        if df.empty:
            return None

        last_close = df['Close'].iloc[-1]
        prev_close = df['Close'].iloc[-2]
        chg = last_close - prev_close
        pct = (chg / prev_close) * 100

        # Determine trend label
        trend = "BULLISH" if pct > 0.3 else ("BEARISH" if pct < -0.3 else "NEUTRAL")

        # ── Volatility Regime Classification (Rolling ATR comparison) ──
        volatility_regime = "NORMAL"
        try:
            tr = pd.concat([
                df['High'] - df['Low'],
                (df['High'] - df['Close'].shift(1)).abs(),
                (df['Low'] - df['Close'].shift(1)).abs()
            ], axis=1).max(axis=1)

            atr_short_val = tr.rolling(atr_short).mean().iloc[-1]
            atr_long_val = tr.rolling(atr_long).mean().iloc[-1] if len(df) >= atr_long else tr.rolling(len(df)).mean().iloc[-1]

            if atr_short_val > 0 and atr_long_val > 0:
                ratio = atr_short_val / atr_long_val
                if ratio > 1.3:
                    volatility_regime = "HIGH"
                elif ratio < 0.8:
                    volatility_regime = "LOW"
                else:
                    volatility_regime = "NORMAL"
        except Exception:
            pass

        ihsg_data = {
            "symbol": symbol,
            "last_close": float(last_close),
            "change": float(chg),
            "percent": float(pct),
            "pct_1d": float(pct),
            "trend": trend,
            "volatility_regime": volatility_regime,
        }

        # Persist to both caches
        _IHSG_MEMORY_CACHE = {"data": ihsg_data, "timestamp": now}
        try:
            with open(IHSG_CACHE_FILE, 'w') as f:
                json.dump({"data": ihsg_data, "timestamp": now}, f, indent=2)
        except Exception as e:
            logger.debug(f"IHSG cache file write error: {e}")

        logger.info(f"IHSG: Fresh — {last_close:,.0f} ({pct:+.2f}%) [{trend}] Vol={volatility_regime}")
        return ihsg_data

    except Exception as e:
        logger.error(f"IHSG fetch error: {e}")
        return None

