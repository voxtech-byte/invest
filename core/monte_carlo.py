import numpy as np
import pandas as pd
from typing import Dict, Any, Tuple
import time
from functools import lru_cache
import hashlib

# In-memory cache for Monte Carlo results
# Key: (data_hash, days, iterations), Value: (result, timestamp)
_mc_cache: Dict[Tuple[str, int, int], Tuple[Dict[str, Any], float]] = {}
_MC_CACHE_TTL = 300  # 5 minutes cache TTL

def _get_data_hash(df: pd.DataFrame) -> str:
    """Generate hash of recent price data for cache key."""
    recent_data = df['Close'].tail(20).values.tobytes()
    return hashlib.md5(recent_data).hexdigest()[:12]

def _get_cached_result(df: pd.DataFrame, days: int, iterations: int) -> Dict[str, Any]:
    """Get cached Monte Carlo result if available and fresh."""
    data_hash = _get_data_hash(df)
    key = (data_hash, days, iterations)
    
    if key in _mc_cache:
        result, timestamp = _mc_cache[key]
        if time.time() - timestamp < _MC_CACHE_TTL:
            return result
    return None

def _cache_result(df: pd.DataFrame, days: int, iterations: int, result: Dict[str, Any]):
    """Cache Monte Carlo result with timestamp."""
    data_hash = _get_data_hash(df)
    key = (data_hash, days, iterations)
    _mc_cache[key] = (result, time.time())
    
    # Cleanup old cache entries (keep only last 50)
    if len(_mc_cache) > 50:
        oldest_key = min(_mc_cache.keys(), key=lambda k: _mc_cache[k][1])
        del _mc_cache[oldest_key]

def run_monte_carlo(df: pd.DataFrame, days: int = 10, iterations: int = 1000) -> Dict[str, Any]:
    """
    Monte Carlo Simulation for Risk Assessment (VaR) with caching.
    Calculates the distribution of potential outcomes over the next N days.
    """
    # Check cache first
    cached = _get_cached_result(df, days, iterations)
    if cached is not None:
        return cached
    
    if len(df) < 50:
        return {"error": "Insufficient data"}
    
    # Calculate log returns
    returns = np.log(df['Close'] / df['Close'].shift(1)).dropna()
    mu = returns.mean()
    sigma = returns.std()
    
    last_price = df['Close'].iloc[-1]
    
    # Simulation matrix: [iterations, days]
    # Geometric Brownian Motion simulation
    shocks = np.random.normal(mu, sigma, (iterations, days))
    price_paths = last_price * np.exp(np.cumsum(shocks, axis=1))
    
    final_prices = price_paths[:, -1]
    
    # ── METRICS ──────────────────────────────────────────────
    
    mean_outcome = np.mean(final_prices)
    var_95 = np.percentile(final_prices, 5) # 5th percentile (95% confidence VaR)
    p25 = np.percentile(final_prices, 25)
    p75 = np.percentile(final_prices, 75)
    p95 = np.percentile(final_prices, 95)
    prob_profit = (np.sum(final_prices > last_price) / iterations) * 100
    
    # Expected Shortfall (CVaR) - average of values below VaR
    cvar_95 = np.mean(final_prices[final_prices <= var_95])
    
    result = {
        "current_price": round(float(last_price), 2),
        "expected_price_avg": round(float(mean_outcome), 2),
        "percentiles": {
            "p5": round(float(var_95), 2),
            "p25": round(float(p25), 2),
            "p75": round(float(p75), 2),
            "p95": round(float(p95), 2),
        },
        "var_95": round(float(var_95), 2),
        "prob_profit": round(float(prob_profit), 1),
        "var_pct": round(((var_95 - last_price) / last_price) * 100, 2),
        "cvar_pct": round(((cvar_95 - last_price) / last_price) * 100, 2),
        "risk_rating": "HIGH" if prob_profit < 40 else "MODERATE" if prob_profit < 55 else "LOW"
    }
    
    # Cache the result
    _cache_result(df, days, iterations, result)
    
    return result
