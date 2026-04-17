import yfinance as yf
import pandas as pd
import requests
from typing import Any, Dict
from logger import get_logger

logger = get_logger(__name__)

def _fetch_yfinance(symbol: str, config: dict[str, Any], period: str = "1y") -> pd.DataFrame | None:
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

def _fetch_alphavantage(symbol: str, config: dict[str, Any]) -> pd.DataFrame | None:
    api_keys = config.get('api_keys', {})
    key = api_keys.get('alpha_vantage')
    if not key or key == "YOUR_KEY":
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

def _fetch_fcsapi(symbol: str, config: dict[str, Any]) -> pd.DataFrame | None:
    api_keys = config.get('api_keys', {})
    key = api_keys.get('fcs_api')
    if not key or key == "YOUR_KEY":
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

def fetch_data(symbol: str, config: dict[str, Any]) -> pd.DataFrame | None:
    df = _fetch_yfinance(symbol, config)
    source = "yfinance"
    if df is None or df.empty:
        df = _fetch_alphavantage(symbol, config)
        source = "Alpha Vantage"
    if df is None or df.empty:
        df = _fetch_fcsapi(symbol, config)
        source = "FCS API"
    if df is None or df.empty:
        return None
    logger.info(f"[{symbol}] Data successfully fetched via {source}")
    try:
        lookback = config['signals']['price_peak_lookback_days']
        df['Peak_Price'] = df['High'].rolling(window=lookback, min_periods=1).max()
    except:
        pass
    return df

def fetch_ihsg(config: dict[str, Any]) -> dict[str, Any] | None:
    try:
        symbol = config.get('macro', {}).get('index_symbol', '^JKSE')
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="5d")
        if df.empty: return None
        last_close = df['Close'].iloc[-1]
        prev_close = df['Close'].iloc[-2]
        chg = last_close - prev_close
        pct = (chg / prev_close) * 100
        return {
            "symbol": symbol,
            "last_close": last_close,
            "change": chg,
            "percent": pct,
            "df": df
        }
    except Exception as e:
        logger.error(f"IHSG fetch error: {e}")
        return None
