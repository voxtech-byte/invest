import sys
import os

# Test imports for Sovereign Modules
try:
    from core.utils import load_config
    from core.indicators import calculate_indicators
    from core.signals import evaluate_signals
    from core.executive import calculate_position_size
    from core.dark_pool import detect_hidden_flows
    from core.monte_carlo import run_monte_carlo
    from core.black_swan import detect_black_swan_event
    from data.data_fetcher import fetch_data
    from data.database import DatabaseManager
    from integrations.news_aggregator import fetch_indonesia_market_news
    from ui.terminal_style import inject_terminal_theme
    
    print("✅ ALL SOVEREIGN MODULES LOADED SUCCESSFULLY.")
    
    # Test Config
    config = load_config()
    print(f"✅ Config Loaded: {len(config.get('stocks', []))} stocks targeted.")
    
    # Test DB (Local Fallback)
    db = DatabaseManager()
    print(f"✅ Database initialized in {'CLOUD' if db.use_cloud else 'LOCAL'} mode.")
    
except Exception as e:
    print(f"❌ MODULE ERROR: {e}")
    sys.exit(1)
