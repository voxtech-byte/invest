import os
import asyncio
import time
from datetime import datetime
from logger import get_logger

# ── Sovereign Modules ──────────────────────────────────────
from core.utils import load_config, TIMEZONE, format_rp
from core.indicators import calculate_indicators
from core.signals import evaluate_signals
from core.executive import calculate_position_size, check_safety_gates, check_sector_exposure
from core.dark_pool import detect_hidden_flows
from core.black_swan import detect_black_swan_event
from data.data_fetcher import fetch_data, fetch_ihsg
from data.database import DatabaseManager
from integrations.alerts import format_alert, format_status_report
from google_sheets_logger import GoogleSheetsLogger

logger = get_logger(__name__)

async def main():
    logger.info("🏛️ SOVEREIGN QUANT TERMINAL: ENGINE INITIALIZED")
    config = load_config()
    db = DatabaseManager()
    
    # Initialize Google Sheets Sync
    gs_cfg = config.get('google_sheets', {})
    sheet_logger = GoogleSheetsLogger(
        sheet_id=gs_cfg.get('spreadsheet_id'), 
        credentials_file=gs_cfg.get('credentials_file', 'service_account.json')
    )
    
    # Initialize Broker
    from mock_broker import MockBroker
    broker = MockBroker(initial_equity=config.get('portfolio', {}).get('initial_equity', 50000000))
    
    stocks = config.get('stocks', [])
    ihsg_data = fetch_ihsg(config)
    
    # --- PHASE 0: EXIT MANAGEMENT ---
    logger.info("🔍 Phase 0: Checking Open Positions for Exit signals...")
    open_positions = broker.get_open_positions()
    for sym, pos in open_positions.items():
        df_exit = fetch_data(sym, config)
        if df_exit is not None:
            df_exit = calculate_indicators(df_exit, config)
            # Signal Evaluate for Exit
            signal_exit, _, _ = evaluate_signals(sym, df_exit, config, ihsg_data=ihsg_data)
            if signal_exit['type'] == "AUTO_TRADE_SELL":
                logger.warning(f"🚩 EXIT SIGNAL: {sym}")
                success_sell, _ = broker.execute_sell(sym, df_exit['Close'].iloc[-1], reason="Signal-Based Exit")
                if success_sell:
                    sheet_logger.log_trade(sym, "SELL", df_exit['Close'].iloc[-1], pos['quantity'], reason="GHA Automated Exit")

    # --- PHASE 1: TARGET SCANNING & EXECUTION ---
    all_status = []
    for symbol in stocks:
        logger.info(f"Analyzing {symbol}...")
        df = fetch_data(symbol, config)
        
        if df is not None:
            df = calculate_indicators(df, config)
            
            # Anomaly Checks
            detect_hidden_flows(df, config)
            detect_black_swan_event(df)
            
            # Signal Evaluation
            signal, summary, reason = evaluate_signals(symbol, df, config, ihsg_data=ihsg_data)
            
            if summary:
                all_status.append(summary)
                
                # Execution Logic
                if signal['type'] == "AUTO_TRADE_BUY":
                    is_safe, safety_warnings = check_safety_gates(broker, ihsg_data, config)
                    sector_warn = check_sector_exposure(symbol, broker.get_open_positions(), config)
                    
                    if is_safe and not sector_warn:
                        lot, _, _ = calculate_position_size(summary['close'], summary['close']*0.95, summary['conviction'], config)
                        logger.info(f"🚀 INITIATING AUTO-BUY: {symbol} ({lot} lot)")
                        success_buy, _ = broker.execute_buy(symbol, summary['close'], lot, reason=f"GHA-Auto S:{summary['conviction']:.1f}")
                        if success_buy:
                            sheet_logger.log_trade(symbol, "BUY", summary['close'], lot, conviction=summary['conviction'], reason="Sovereign GHA Auto-Buy")
                    else:
                        logger.info(f"⚠️ SIGNAL IGNORED: {safety_warnings[0] if safety_warnings else 'Sector Limit'}")
                    
        # Cooldown protection
        time.sleep(1)

    # Save results to DB
    db.save_scan_results(all_status)
    logger.info("Sweep complete. Data synced to Sovereign Data Layer and Cloud Sheets.")

if __name__ == "__main__":
    asyncio.run(main())
