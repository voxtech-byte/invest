import os
import asyncio
import time
from dotenv import load_dotenv
load_dotenv() # Load env vars from .env file

from datetime import datetime
from logger import get_logger

# ── Sovereign Modules ──────────────────────────────────────
from core.utils import load_config, TIMEZONE, format_rp
from core.indicators import calculate_indicators, enrich_relative_strength
from core.signals import evaluate_signals, evaluate_exit_conditions
from core.executive import (
    calculate_position_size, check_safety_gates,
    check_sector_exposure, check_liquidity,
    check_portfolio_heat, check_correlation,
    adjust_size_for_correlation
)
from core.dark_pool import detect_hidden_flows
from core.black_swan import detect_black_swan_event
from data.data_fetcher import fetch_data, fetch_ihsg
from data.database import DatabaseManager
from integrations.alerts import format_alert, format_status_report
from integrations.telegram_queue import send_telegram_queued, flush_telegram_queue, get_telegram_queue
from google_sheets_logger import GoogleSheetsLogger
from core.sector_rotation import analyze_sector_rotation
from core.config_validator import validate_config

logger = get_logger(__name__)

async def main():
    logger.info("🏛️ SOVEREIGN QUANT TERMINAL V15: ENGINE INITIALIZED")
    
    # Initialize Telegram queue for rate-limited messaging
    await get_telegram_queue()
    config = load_config()

    # ── Config Validation ──
    config_issues = validate_config(config)
    if config_issues:
        logger.warning(f"⚠️ Config Validator found {len(config_issues)} issues. Check logs.")
    
    # ── Market Hours Gate ──
    from core.utils import is_market_open
    force_run = os.getenv("FORCE_RUN_OUT_OF_HOURS", "false").lower() == "true"
    
    if not is_market_open() and not force_run:
        logger.warning("🕒 MARKET CLOSED: Skipping sweep cycle to protect liquidity/execution accuracy.")
        logger.info("Use FORCE_RUN_OUT_OF_HOURS=true to override.")
        return

    db = DatabaseManager()

    exec_cfg = config.get('execution', {})

    # Initialize Google Sheets Sync
    gs_cfg = config.get('google_sheets', {})
    sheet_logger = GoogleSheetsLogger(
        sheet_id=gs_cfg.get('spreadsheet_id'),
        credentials_file=gs_cfg.get('credentials_file', 'service_account.json')
    )

    # Initialize Broker
    from mock_broker import MockBroker
    broker = MockBroker(initial_equity=config.get('portfolio', {}).get('initial_equity', 50_000_000))

    # Position Reconciliation: Ensure broker and DB are in sync
    from core.position_sync import run_reconciliation
    sync_result = run_reconciliation(broker, db)
    if sync_result.get('status') == 'ISSUES_FOUND':
        logger.warning(f"📊 Position sync issues auto-resolved: {len(sync_result.get('fixes_applied', []))} fixes")

    stocks = config.get('stocks', [])
    ihsg_data = fetch_ihsg(config)

    # ═══════════════════════════════════════════════════════════
    # PHASE 0: ACTIVE EXIT MANAGEMENT
    # ═══════════════════════════════════════════════════════════
    logger.info("🔍 Phase 0: Active Position Management (Stop Loss / Trailing / Partial TP)...")
    open_positions = dict(broker.get_open_positions())  # Copy to avoid mutation during iteration

    for sym, pos in open_positions.items():
        try:
            df_exit = fetch_data(sym, config)
            if df_exit is None or df_exit.empty:
                logger.warning(f"[{sym}] No data for exit check — skipping")
                continue

            df_exit = calculate_indicators(df_exit, config)
            current_price = df_exit['Close'].iloc[-1]

            # ── Update highest_price for trailing stop ──
            if current_price > pos.get('highest_price', pos.get('avg_price', 0)):
                pos['highest_price'] = current_price
                broker._save_positions()

            # ── Evaluate exit conditions with full position context ──
            exit_type, exit_reason = evaluate_exit_conditions(
                sym, df_exit, config, position=pos, ihsg_data=ihsg_data
            )

            if exit_type == "PARTIAL_TP1":
                # ── PARTIAL PROFIT TAKING: Sell 50% at TP1 ──
                tp1_pct = exec_cfg.get('tp1_scale_out_pct', 50)
                sell_qty = int(pos['quantity'] * (tp1_pct / 100))
                sell_qty = (sell_qty // 100) * 100  # Round to lot

                if sell_qty >= 100:
                    logger.info(f"🎯 TP1 HIT: {sym} — Selling {tp1_pct}% ({sell_qty} shares)")
                    success_sell, res = broker.execute_sell(
                        sym, current_price, lot=sell_qty,
                        reason=f"Partial TP1: {exit_reason}"
                    )
                    if success_sell:
                        sheet_logger.log_trade(
                            sym, "SELL", current_price, sell_qty,
                            reason=f"GHA Partial TP1 ({exit_reason})"
                        )
                        # Mark TP1 as hit — trailing stop now active at break-even
                        remaining = broker.get_open_positions().get(sym)
                        if remaining:
                            remaining['tp1_hit'] = True
                            broker._save_positions()
                        logger.info(f"[{sym}] TP1 sold. Remaining position trailing at break-even.")
                        
                        # Telegram Alert
                        alert_msg = format_alert({
                            "type": "PARTIAL_TP1",
                            "data": remaining if remaining else pos,
                            "exit_reason": exit_reason
                        }, extra={"lot": sell_qty})
                        await send_telegram_queued(alert_msg)
                else:
                    logger.info(f"[{sym}] TP1 hit but position too small for partial sell ({pos['quantity']} shares)")

            elif exit_type == "AUTO_TRADE_SELL":
                # ── FULL EXIT ──
                logger.warning(f"🚩 EXIT SIGNAL: {sym} — {exit_reason}")
                success_sell, res = broker.execute_sell(
                    sym, current_price,
                    reason=f"Signal-Based Exit: {exit_reason}"
                )
                if success_sell:
                    sheet_logger.log_trade(
                        sym, "SELL", current_price, pos['quantity'],
                        reason=f"GHA Auto-Exit ({exit_reason})"
                    )
                    db.remove_position(sym)
                    
                    # Telegram Alert
                    alert_msg = format_alert({
                        "type": "AUTO_TRADE_SELL",
                        "data": pos,
                        "exit_reason": exit_reason
                    }, extra={"lot": pos['quantity']})
                    await send_telegram_queued(alert_msg)

        except Exception as e:
            logger.error(f"[{sym}] Exit evaluation error: {e}")
            continue

    # ═══════════════════════════════════════════════════════════
    # PHASE 1: DATA GATHERING & SECTOR ANALYSIS
    # ═══════════════════════════════════════════════════════════
    logger.info("📡 Phase 1: Data gathering & Sector analysis...")
    all_dfs = {}
    for symbol in stocks:
        try:
            df = fetch_data(symbol, config)
            if df is not None and len(df) >= 60:
                all_dfs[symbol] = calculate_indicators(df, config)
        except Exception as e:
            logger.error(f"[{symbol}] Data fetch error: {e}")

    sector_rotation = analyze_sector_rotation(all_dfs, config)

    # ── V15: Enrich Relative Strength vs IHSG ──
    try:
        import yfinance as yf
        ihsg_symbol = config.get('macro', {}).get('index_symbol', '^JKSE')
        ihsg_raw_df = yf.Ticker(ihsg_symbol).history(period="1y")
        if ihsg_raw_df is not None and not ihsg_raw_df.empty:
            for symbol in all_dfs:
                all_dfs[symbol] = enrich_relative_strength(all_dfs[symbol], ihsg_raw_df)
            logger.info(f"📊 V15: Relative Strength vs IHSG enriched for {len(all_dfs)} stocks")
    except Exception as e:
        logger.warning(f"RS vs IHSG enrichment skipped: {e}")
    
    # ═══════════════════════════════════════════════════════════
    # PHASE 2: TARGET SCANNING & EXECUTION
    # ═══════════════════════════════════════════════════════════
    logger.info("📡 Phase 2: Scanning watchlist for entry signals...")
    all_status = []
    for symbol, df in all_dfs.items():
        try:
            logger.info(f"Analyzing {symbol}...")
            last_row = df.iloc[-1]
            current_pos = broker.get_open_positions().get(symbol)

            # ── Liquidity Filter ──
            is_liquid, liq_reason = check_liquidity(last_row, config)
            if not is_liquid:
                logger.info(f"[{symbol}] Skipped: {liq_reason}")
                continue

            # Anomaly Checks
            detect_hidden_flows(df, config)
            detect_black_swan_event(df)

            # Signal Evaluation (current_pos sudah di-fetch di line 189)
            signal, summary, reason = evaluate_signals(
                symbol, df, config,
                ihsg_data=ihsg_data,
                open_position=current_pos,
                sector_rotation=sector_rotation
            )

            if summary:
                all_status.append(summary)

                # ── BUY Execution Logic ──
                if signal['type'] == "AUTO_TRADE_BUY" and current_pos is None:
                    is_safe, safety_warnings = check_safety_gates(broker, ihsg_data, config)
                    sector_warn = check_sector_exposure(symbol, broker.get_open_positions(), config)

                    if is_safe and not sector_warn:
                        lot, pos_value, risk_tier = calculate_position_size(
                            summary['close'],
                            summary['stop_loss'],
                            summary['conviction'],
                            config,
                            ihsg_data=ihsg_data
                        )
                        if lot > 0:
                            # ── Portfolio Heat Check ──
                            risk_amount = lot * abs(summary['close'] - summary['stop_loss'])
                            heat_ok, heat_pct, heat_msg = check_portfolio_heat(broker, risk_amount, config)
                            if not heat_ok:
                                logger.info(f"🌡️ {symbol} BLOCKED: {heat_msg}")
                                continue

                            # ── REENTRY COOLDOWN CHECK (3 Days) ──
                            from datetime import timedelta
                            cooldown_days = 3
                            last_sell = next((t for t in reversed(broker.get_trade_history()) 
                                            if t['symbol'] == symbol and t['action'] == 'SELL'), None)
                            if last_sell:
                                try:
                                    last_exit_date = datetime.fromisoformat(last_sell['date'])
                                    if datetime.now(TIMEZONE) - last_exit_date < timedelta(days=cooldown_days):
                                        logger.info(f"⏳ {symbol} SKIPPED: Reentry cooldown ({cooldown_days} days)")
                                        continue
                                except Exception as e:
                                    logger.warning(f"Cooldown parse error for {symbol}: {e}")

                            # ── Correlation Check ──
                            corr_warnings = check_correlation(
                                symbol, df, broker.get_open_positions(), config,
                                fetch_data_fn=fetch_data
                            )
                            if corr_warnings:
                                logger.info(f"🔗 {symbol} CORRELATION WARNING: {corr_warnings[0]}")
                                # Don't block, but log warning

                            # ── V15: Correlation-Adjusted Sizing ──
                            lot = adjust_size_for_correlation(
                                symbol, lot, df, broker.get_open_positions(),
                                config, fetch_data_fn=fetch_data
                            )
                            if lot <= 0:
                                logger.info(f"[{symbol}] Lot reduced to 0 by correlation adjustment")
                                continue

                            logger.info(f"🚀 AUTO-BUY: {symbol} ({lot} shares, Risk: {risk_tier}%, Heat: {heat_pct:.1f}%)")
                            success_buy, res = broker.execute_buy(
                                symbol, summary['close'], lot,
                                reason=f"GHA-Auto S:{summary['conviction']:.1f} W:{summary.get('weekly_trend', 'N/A')} FP:{summary.get('inst_footprint', 0)}"
                            )
                            if success_buy:
                                sheet_logger.log_trade(
                                    symbol, "BUY", summary['close'], lot,
                                    conviction=summary['conviction'],
                                    reason=f"Sovereign GHA Auto-Buy (Wyckoff: {summary['wyckoff_phase']})"
                                )
                                db.save_position(symbol, broker.get_open_positions().get(symbol, {}))
                                
                                # Telegram Alert
                                alert_msg = format_alert(signal, extra={
                                    "lot": lot,
                                    "heat_pct": heat_pct,
                                    "regime": ihsg_data.get('volatility_regime', 'NORMAL') if ihsg_data else 'NORMAL'
                                })
                                await send_telegram_queued(alert_msg)
                        else:
                            logger.info(f"[{symbol}] Signal valid but lot=0 after sizing")
                    else:
                        warn_msg = safety_warnings[0] if safety_warnings else (sector_warn[0] if sector_warn else 'Unknown')
                        logger.info(f"⚠️ {symbol} SIGNAL IGNORED: {warn_msg}")

        except Exception as e:
            logger.error(f"[{symbol}] Scan error: {e}")
            continue

        # Cooldown protection
        time.sleep(1)

    # Save results to DB
    db.save_scan_results(all_status)
    logger.info(f"✅ Sweep complete. {len(all_status)} stocks analyzed. Data synced.")
    
    # Send Status Report
    report_msg = format_status_report(all_status, ihsg_data, broker)
    if sector_rotation:
        report_msg += "\n*Hot Sectors (20d Momentum):*\n"
        for sr in sector_rotation[:3]:
            report_msg += f"🔥 `{sr['sector']}`: {sr['avg_momentum_20d']:+.1f}% (Breadth {sr['breadth_pct']:.0f}%)\n"
            
    await send_telegram_queued(report_msg)
    
    # Save Equity Snapshot
    total_pos_value = sum(p['quantity'] * p['avg_price'] for p in broker.get_open_positions().values())
    total_equity = broker.get_balance() + total_pos_value
    db.save_equity_snapshot(
        balance=broker.get_balance(),
        open_positions_count=len(broker.get_open_positions()),
        daily_pnl=broker.get_daily_realized_pnl(),
        total_equity=total_equity
    )
    
    # Flush Telegram queue to ensure all messages are sent
    await flush_telegram_queue()

if __name__ == "__main__":
    asyncio.run(main())
